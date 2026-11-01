from __future__ import annotations

import base64
import binascii
import re
from urllib.parse import unquote

from ...domain import Severity
from ..fileio import is_probably_text
from .base import AnalysisContext, AnalysisPlugin

_B64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{20,}={0,2}(?![A-Za-z0-9+/])")
_HEX = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}){12,}(?![0-9a-fA-F])")
_HEX_SPACED = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}[\s:]){10,}[0-9a-fA-F]{2}")
_URL = re.compile(r"(?:%[0-9A-Fa-f]{2}){3,}")
_RSA_N = re.compile(r"(?i)\bn\s*=\s*(0x[0-9a-f]+|\d{20,})")
_RSA_E = re.compile(r"(?i)\be\s*=\s*(0x[0-9a-f]+|\d{1,10})")
_PEM = re.compile(r"-----BEGIN ([A-Z ]+)-----")


class CryptoPlugin(AnalysisPlugin):
    name = "crypto"
    label = "Crypto 分析"
    description = "识别常见编码、古典密码、RSA 参数与 XOR 线索。"

    def run(self, context: AnalysisContext, mode: str) -> None:
        files = context.files(exclude_kinds={"empty"})
        total = max(len(files), 1)
        for index, artifact in enumerate(files):
            if artifact.kind in {"zip", "7z", "rar", "gzip", "tar", "bzip2", "xz"}:
                continue
            context.report_progress(
                30 + int(18 * index / total),
                f"Crypto 分析：{artifact.path.rsplit('/', 1)[-1]}",
            )
            text = context.text_for(artifact)
            if text:
                context.analyze_text(text, artifact)
                self._scan_text_encodings(context, artifact, text)
            data = context.bytes_for(artifact, limit=3 * 1024 * 1024)
            if artifact.kind in {"elf", "pe", "binary"} or not text:
                context.analyze_bytes(data, artifact)
                self._scan_binary_encodings(context, artifact, data)
            elif text and _PEM.search(text):
                self._scan_rsa(context, artifact, text)

    def _scan_text_encodings(self, context: AnalysisContext, artifact, text: str) -> None:
        name = artifact.path.rsplit("/", 1)[-1]
        detected: list[tuple[str, str, str]] = []

        for match in list(_B64.finditer(text))[:4]:
            decoded = self._decode_b64(match.group(0))
            if decoded:
                detected.append(
                    ("Base64", match.group(0)[:48], " ".join(decoded[:160].split()))
                )
        for regex in (_HEX, _HEX_SPACED):
            for match in list(regex.finditer(text))[:3]:
                token = re.sub(r"[\s:]", "", match.group(0))
                try:
                    decoded = bytes.fromhex(token).decode("utf-8", "replace")
                except ValueError:
                    continue
                if decoded and is_probably_text(decoded.encode("utf-8", "ignore")):
                    detected.append(("Hex", token[:48], " ".join(decoded[:160].split())))
        for match in list(_URL.finditer(text))[:3]:
            decoded = unquote(match.group(0))
            detected.append(("URL 编码", match.group(0)[:48], decoded[:160]))

        for kind, token, preview in detected[:8]:
            context.add_finding(
                title=f"检测到 {kind} 编码内容",
                category="crypto",
                severity=Severity.INFO,
                description=f"{name} 中包含可解码的 {kind} 数据。",
                evidence=f"{token} → {preview}",
                artifact=artifact,
                rule_id=f"crypto.{kind.lower().replace(' ', '_')}",
            )

        self._caesar_bruteforce(context, artifact, text)

        n_match = _RSA_N.search(text)
        e_match = _RSA_E.search(text)
        if n_match:
            n_text = n_match.group(1)
            e_text = e_match.group(1) if e_match else "65537"
            try:
                modulus = int(n_text, 0)
                exponent = int(e_text, 0)
                detail = f"n 约 {modulus.bit_length()} bit，e={exponent}"
            except ValueError:
                detail = f"n={n_text[:48]}，e={e_text}"
            context.add_finding(
                title="识别到 RSA 参数",
                category="crypto",
                severity=Severity.INFO,
                description="材料中出现 RSA 模数与指数参数，可继续检查共模、低指数或小模数问题。",
                evidence=detail,
                artifact=artifact,
                rule_id="crypto.rsa.parameters",
            )

        for match in _PEM.finditer(text):
            context.add_finding(
                title=f"识别到 PEM {match.group(1).strip()}",
                category="crypto",
                severity=Severity.INFO,
                description="检测到 PEM 结构，可进一步解析密钥参数与证书信息。",
                evidence=match.group(0),
                artifact=artifact,
                line=text[: match.start()].count("\n") + 1,
                rule_id="crypto.pem",
            )

    def _caesar_bruteforce(self, context: AnalysisContext, artifact, text: str) -> None:
        if "{" not in text or len(text) > 800_000:
            return
        for shift in range(1, 26):
            decoded = "".join(
                chr((ord(char) - 65 - shift) % 26 + 65)
                if "A" <= char <= "Z"
                else chr((ord(char) - 97 - shift) % 26 + 97)
                if "a" <= char <= "z"
                else char
                for char in text
            )
            matches = context.flag_engine.scan_candidate(
                decoded,
                artifact.path,
                method=f"凯撒位移 {shift}",
                confidence=0.68,
                evidence_prefix=f"对全文进行 ROT{shift} 变换后匹配",
            )
            if matches:
                context.add_finding(
                    title=f"凯撒位移 {shift} 命中 Flag 格式",
                    category="crypto",
                    severity=Severity.MEDIUM,
                    description="该位移结果中出现 Flag 格式字符串，仍需结合题目上下文验证。",
                    evidence=matches[0].value,
                    artifact=artifact,
                    rule_id="crypto.caesar.bruteforce",
                )
                break

    def _scan_binary_encodings(
        self, context: AnalysisContext, artifact, data: bytes
    ) -> None:
        if not data:
            return
        strings = context.strings_for(artifact, limit=600)
        joined = "\n".join(text for _, text in strings[:200])
        if _B64.search(joined):
            context.add_finding(
                title="二进制中检测到疑似 Base64 数据",
                category="crypto",
                severity=Severity.INFO,
                description="已对二进制可打印字符串执行编码与 Flag 扫描。",
                evidence=self._first_preview(_B64.search(joined)),
                artifact=artifact,
                rule_id="crypto.binary.base64",
            )

    @staticmethod
    def _decode_b64(token: str) -> str:
        compact = re.sub(r"\s+", "", token)
        try:
            raw = base64.b64decode(compact + "=" * (-len(compact) % 4), validate=True)
            text = raw.decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return ""
        if is_probably_text(text.encode("utf-8", "ignore")):
            return text
        return ""

    @staticmethod
    def _first_preview(match) -> str:
        return match.group(0)[:96] if match else ""
