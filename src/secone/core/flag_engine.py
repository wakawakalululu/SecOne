from __future__ import annotations

import base64
import binascii
import codecs
import gzip
import hashlib
import html
import quopri
import re
import zlib
from dataclasses import dataclass, field
from urllib.parse import unquote

from ..domain import FlagCandidate, FlagStatus
from .fileio import is_probably_text, printable_strings

_BASE64_RE = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/])")
_HEX_RE = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}){8,}(?![0-9a-fA-F])")
_HEX_SPACED_RE = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2,4}[\s:]){7,}[0-9a-fA-F]{2,4}")
_BASE32_RE = re.compile(r"(?<![A-Z2-7])[A-Z2-7]{16,}={0,6}(?![A-Z2-7])")
_GENERIC_FLAG_RE = re.compile(
    r"(?i)(?:[a-z0-9_]{2,32}\{[^{}\r\n]{1,200}\}|[a-z0-9_]{2,32}\([^()\r\n]{1,200}\))"
)
_CONTEXT_CHARS = 72
_MAX_TEXT_SCAN = 1_500_000
_XOR_TABLES = [bytes(byte ^ key for byte in range(256)) for key in range(256)]
_PLACEHOLDER_VALUES = {
    "...",
    "…",
    "?",
    "??",
    "???",
    "x",
    "xx",
    "xxx",
    "xxxx",
    "test",
    "example",
    "sample",
    "redacted",
    "todo",
    "here",
    "value",
    "string",
    "answer",
    "your_flag",
    "yourflag",
    "your_flag_here",
    "yourflaghere",
    "flag",
    "flag_here",
    "fake_flag",
    "dummy_flag",
    "placeholder",
}
_PLACEHOLDER_RE = re.compile(
    r"(?is)^[A-Za-z0-9_]{1,32}[\{\(](?P<inner>.*)[\}\)]$"
)
_PLACEHOLDER_WORDS = {
    "flag",
    "ctf",
    "your",
    "my",
    "the",
    "a",
    "an",
    "this",
    "is",
    "here",
    "goes",
    "value",
    "answer",
    "token",
    "secret",
    "test",
    "example",
    "sample",
    "fake",
    "dummy",
    "placeholder",
    "redacted",
    "todo",
    "fixme",
    "xxx",
    "insert",
    "put",
    "some",
}
_PLACEHOLDER_STRONG = {
    "your",
    "here",
    "goes",
    "test",
    "example",
    "sample",
    "fake",
    "dummy",
    "placeholder",
    "redacted",
    "todo",
    "fixme",
    "xxx",
    "insert",
    "put",
    "some",
}
_XOR_SCAN_LIMIT = 512 * 1024
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_AFFINE_KEYS = (1, 3, 5, 7, 9, 11, 15, 17, 19, 21, 23, 25)
_BASE58_RE = re.compile(
    r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{20,}(?![1-9A-HJ-NP-Za-km-z])"
)
_BASE85_RUN_RE = re.compile(r"(?<![!-~])[!-~]{20,}(?![!-~])")
_BINARY_RUN_RE = re.compile(r"(?<![01])[01]{32,}(?![01])")
_BINARY_SPACED_RE = re.compile(r"(?<![01])[01]{8}(?:[\s:]+[01]{8}){7,}(?![01])")
_DECIMAL_RUN_RE = re.compile(r"(?<!\d)(?:\d{2,3}[\s,]+){7,}\d{2,3}(?!\d)")
_OCTAL_RUN_RE = re.compile(r"(?<!\d)(?:[01]?[0-7]{2}[\s]+){7,}[01]?[0-7]{2}(?!\d)")
_CODE_LIST_RE = re.compile(r"\[((?:\s*\d{1,3}\s*,){7,}\s*\d{1,3}\s*)\]")
_HTML_ENTITY_RE = re.compile(r"&(?:#\d{1,7}|#x[0-9a-fA-F]{1,6});")
_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_QP_RUN_RE = re.compile(r"(?:=[0-9A-Fa-f]{2}){8,}")
_JS_CONCAT_PAIR_RE = re.compile(
    r"(?s)(['\"])((?:\\.|(?!\1).)*)\1\s*\+\s*(['\"])((?:\\.|(?!\3).)*)\3"
)
_JS_ARRAY_JOIN_RE = re.compile(
    r"(?s)\[((?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^\[\]])*?)\]"
    r"\s*\.\s*join\s*\(\s*(['\"])([^'\"]*)\2\s*\)"
)
_JS_STRING_RE = re.compile(r"\"((?:\\.|[^\"\\])*)\"|'((?:\\.|[^'\\])*)'")
_ATBASH_TABLE = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA",
)


def _atbash_text(text: str) -> str:
    return text.translate(_ATBASH_TABLE)


def _caesar_text(text: str, shift: int) -> str:
    lower = "abcdefghijklmnopqrstuvwxyz"
    upper = lower.upper()
    back = shift % 26
    table = str.maketrans(
        lower + upper,
        lower[-back:] + lower[:-back] + upper[-back:] + upper[:-back],
    )
    return text.translate(table)


def _affine_decipher_text(text: str, key_a: int, key_b: int) -> str:
    inverse = pow(key_a, -1, 26)
    mapping: dict[str, str] = {}
    for index in range(26):
        plain = chr(ord("a") + (inverse * (index - key_b)) % 26)
        mapping[chr(ord("a") + index)] = plain
        mapping[chr(ord("A") + index)] = plain.upper()
    return text.translate(str.maketrans(mapping))


def _strict_ascii_text(raw: bytes) -> str:
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    if not text:
        return ""
    for char in text:
        code = ord(char)
        if code > 126 or (code < 32 and char not in "\t\r\n"):
            return ""
    return text


def _packed_variants(raw: bytes) -> list[tuple[bytes, str]]:
    variants: list[tuple[bytes, str]] = []
    if raw[:2] == b"\x1f\x8b":
        try:
            variants.append((gzip.decompress(raw), "gzip 解压"))
        except (OSError, EOFError, zlib.error):
            pass
    elif len(raw) >= 2 and raw[0] == 0x78 and (raw[0] * 256 + raw[1]) % 31 == 0:
        try:
            variants.append((zlib.decompress(raw), "zlib 解压"))
        except zlib.error:
            pass
    return variants


def _try_base58(token: str) -> str:
    compact = token.strip()
    if not compact or len(compact) > 4096:
        return ""
    number = 0
    for char in compact:
        index = _BASE58_ALPHABET.find(char)
        if index < 0:
            return ""
        number = number * 58 + index
    zeros = len(compact) - len(compact.lstrip("1"))
    body = b""
    if number:
        body = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return _strict_ascii_text(b"\x00" * zeros + body)


def _try_base85(token: str) -> list[str]:
    outputs: list[str] = []
    for decoder in (base64.b85decode, base64.a85decode):
        try:
            raw = decoder(token)
        except (ValueError, binascii.Error):
            continue
        text = _strict_ascii_text(raw)
        if text and text not in outputs:
            outputs.append(text)
    return outputs


def _fold_js_concat(text: str) -> str:
    current = text
    for _ in range(64):
        folded = _JS_CONCAT_PAIR_RE.sub(
            lambda match: '"' + match.group(2) + match.group(4) + '"', current
        )
        if folded == current:
            break
        current = folded
    return current


def _join_js_array(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        parts: list[str] = []
        for double, single in _JS_STRING_RE.findall(match.group(1)):
            part = double if double else single
            parts.append(part.replace('\\"', '"').replace("\\'", "'"))
        return '"' + match.group(3).join(parts) + '"'

    return _JS_ARRAY_JOIN_RE.sub(_replace, text)


_CONCAT_ARTIFACT_RE = re.compile(r"[\"']\s*\+|\+\s*[\"']")


@dataclass
class _Entry:
    candidate: FlagCandidate
    order: int


@dataclass
class FlagEngine:
    patterns: list[str]
    decode_depth: int = 3
    max_results: int = 80
    candidates: dict[tuple[str, str], _Entry] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    _order: int = 0
    _visited: set[str] = field(default_factory=set)
    _nodes: int = 0
    _max_nodes: int = 800
    _xor_sources: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._compiled: list[re.Pattern[str]] = []
        self._loose_compiled: list[re.Pattern[str]] = []
        for pattern in self.patterns:
            try:
                self._compiled.append(re.compile(pattern))
            except re.error as exc:
                self.warnings.append(f"忽略无效 Flag 规则：{pattern}（{exc}）")
                continue
            loose = pattern.replace(r"\b", "")
            if loose == pattern:
                continue
            try:
                self._loose_compiled.append(re.compile(loose))
            except re.error:
                continue

    def scan_direct(
        self,
        text: str,
        source: str,
        base_offset: int = 0,
        method: str = "直接匹配",
        evidence_prefix: str = "",
    ) -> list[FlagCandidate]:
        found: list[FlagCandidate] = []
        if not text:
            return found
        for regex in self._compiled:
            for match in regex.finditer(text):
                value = match.group(0).strip()
                if not value or _CONCAT_ARTIFACT_RE.search(value):
                    continue
                start = max(match.start() - _CONTEXT_CHARS, 0)
                end = min(match.end() + _CONTEXT_CHARS, len(text))
                evidence = " ".join(text[start:end].split())
                if evidence_prefix:
                    evidence = f"{evidence_prefix} | {evidence}"
                candidate = self._add(
                    FlagCandidate(
                        value=value,
                        status=FlagStatus.FOUND,
                        confidence=1.0,
                        source=source,
                        offset=base_offset + match.start(),
                        method=method,
                        evidence=evidence,
                    )
                )
                if candidate:
                    found.append(candidate)
        return found

    def analyze_text(
        self,
        text: str,
        source: str,
        depth: int | None = None,
        base_offset: int = 0,
    ) -> list[FlagCandidate]:
        if not text:
            return []
        max_depth = self.decode_depth if depth is None else depth
        direct = self.scan_direct(text, source, base_offset=base_offset)
        if max_depth <= 0:
            return direct
        self._walk_text(text, source, max_depth)
        return direct

    def analyze_bytes(
        self,
        data: bytes,
        source: str,
        depth: int | None = None,
        include_text: bool = True,
    ) -> list[FlagCandidate]:
        candidates: list[FlagCandidate] = []
        if not data:
            return candidates
        if is_probably_text(data[:8192]):
            if include_text:
                from .fileio import decode_bytes

                text = decode_bytes(data)
                candidates.extend(self.analyze_text(text, source, depth=depth))
        else:
            for offset, string in printable_strings(data, min_length=4, limit=800):
                candidates.extend(
                    self.scan_direct(
                        string,
                        source,
                        base_offset=offset,
                        method="二进制字符串提取",
                    )
                )
                if len(string) >= 16:
                    self._walk_text(string, source, depth or self.decode_depth, base_offset=offset)
        candidates.extend(self._xor_scan(data, source))
        return candidates

    def scan_candidate(
        self,
        text: str,
        source: str,
        method: str,
        confidence: float = 0.8,
        base_offset: int = 0,
        evidence_prefix: str = "",
    ) -> list[FlagCandidate]:
        added: list[FlagCandidate] = []
        for regex in self._compiled:
            for match in regex.finditer(text):
                value = match.group(0).strip()
                if not value or _CONCAT_ARTIFACT_RE.search(value):
                    continue
                start = max(match.start() - _CONTEXT_CHARS, 0)
                end = min(match.end() + _CONTEXT_CHARS, len(text))
                evidence = " ".join(text[start:end].split())
                if evidence_prefix:
                    evidence = f"{evidence_prefix} | {evidence}"
                candidate = self._add(
                    FlagCandidate(
                        value=value,
                        status=FlagStatus.CANDIDATE,
                        confidence=confidence,
                        source=source,
                        offset=base_offset + match.start(),
                        method=method,
                        evidence=evidence,
                    )
                )
                if candidate:
                    added.append(candidate)
        return added

    def add_ai_candidates(
        self,
        response: str,
        material: str,
        source: str = "AI 分析",
    ) -> tuple[list[FlagCandidate], list[str]]:
        added: list[FlagCandidate] = []
        rejected: list[str] = []
        for match in _GENERIC_FLAG_RE.finditer(response or ""):
            value = match.group(0).strip()
            if not self._looks_like_known_flag(value):
                continue
            if value not in material:
                rejected.append(value)
                continue
            candidate = self._add(
                FlagCandidate(
                    value=value,
                    status=FlagStatus.CANDIDATE,
                    confidence=0.55,
                    source=source,
                    method="AI 线索定位（已回查材料原文）",
                    evidence="模型在材料中定位到该字符串，SecOne 已回查原文。",
                    ai_generated=True,
                )
            )
            if candidate:
                added.append(candidate)
        return added, rejected

    def _looks_like_known_flag(self, value: str) -> bool:
        return any(regex.fullmatch(value) for regex in self._compiled)

    def _walk_text(
        self,
        text: str,
        source: str,
        max_depth: int,
        base_offset: int = 0,
    ) -> None:
        worklist: list[tuple[str, str, int, int]] = [(text, "", 0, base_offset)]
        while worklist and len(self.candidates) < self.max_results:
            current, chain, depth, offset = worklist.pop(0)
            if depth >= max_depth or self._nodes >= self._max_nodes:
                continue
            digest = hashlib.sha1(current.encode("utf-8", "ignore")).hexdigest()
            if digest in self._visited:
                continue
            self._visited.add(digest)
            self._nodes += 1
            for decoded, method, child_offset in self._decode_once(current):
                if not decoded or decoded == current:
                    continue
                if len(decoded) > _MAX_TEXT_SCAN:
                    continue
                child_chain = f"{chain} → {method}" if chain else method
                for match in _GENERIC_FLAG_RE.finditer(decoded):
                    value = match.group(0).strip()
                    if not value or _CONCAT_ARTIFACT_RE.search(value):
                        continue
                    if not self._looks_like_known_flag(value):
                        continue
                    start = max(match.start() - _CONTEXT_CHARS, 0)
                    end = min(match.end() + _CONTEXT_CHARS, len(decoded))
                    context = " ".join(decoded[start:end].split())
                    confidence = max(0.55, 0.88 - 0.07 * depth)
                    self._add(
                        FlagCandidate(
                            value=value,
                            status=FlagStatus.CANDIDATE,
                            confidence=confidence,
                            source=source,
                            offset=offset + child_offset + match.start(),
                            method=f"{child_chain} → 匹配",
                            evidence=context,
                        )
                    )
                    if len(self.candidates) >= self.max_results:
                        return
                for regex in self._compiled:
                    for match in regex.finditer(decoded):
                        value = match.group(0).strip()
                        if not value or _CONCAT_ARTIFACT_RE.search(value):
                            continue
                        start = max(match.start() - _CONTEXT_CHARS, 0)
                        end = min(match.end() + _CONTEXT_CHARS, len(decoded))
                        context = " ".join(decoded[start:end].split())
                        confidence = max(0.55, 0.88 - 0.07 * depth)
                        self._add(
                            FlagCandidate(
                                value=value,
                                status=FlagStatus.CANDIDATE,
                                confidence=confidence,
                                source=source,
                                offset=offset + child_offset + match.start(),
                                method=f"{child_chain} → 匹配",
                                evidence=context,
                            )
                        )
                        if len(self.candidates) >= self.max_results:
                            return
                if depth + 1 < max_depth and len(decoded) <= 200_000:
                    worklist.append((decoded, child_chain, depth + 1, offset + child_offset))

    def _flag_hit(self, text: str) -> bool:
        return any(regex.search(text) for regex in self._compiled)

    def _decode_once(self, text: str) -> list[tuple[str, str, int]]:
        results: list[tuple[str, str, int]] = []
        stripped = text.strip()
        if not stripped:
            return results

        if 8 <= len(stripped) <= 20_000:
            reversed_text = stripped[::-1]
            if reversed_text != stripped:
                results.append((reversed_text, "整段倒序", 0))

        if "%" in stripped:
            decoded = unquote(stripped)
            if decoded != stripped and is_probably_text(decoded.encode("utf-8", "ignore")):
                results.append((decoded, "URL 解码", 0))

        if any(char.isalpha() for char in stripped):
            decoded = codecs.encode(stripped, "rot_13")
            if decoded != stripped:
                results.append((decoded, "ROT13", 0))
            decoded = _atbash_text(stripped)
            if decoded != stripped:
                results.append((decoded, "Atbash 镜像还原", 0))
            if any(33 <= ord(char) <= 126 for char in stripped):
                decoded = "".join(
                    chr(33 + (ord(char) - 33 + 47) % 94)
                    if 33 <= ord(char) <= 126
                    else char
                    for char in stripped
                )
                if decoded != stripped:
                    results.append((decoded, "ROT47", 0))

        for match in list(_BASE64_RE.finditer(text))[:6]:
            token = match.group(0)
            decoded = self._try_base64(token)
            if decoded:
                results.append((decoded, "Base64 解码", match.start()))
            compact = re.sub(r"\s+", "", token)
            if len(compact) >= 12:
                padding = "=" * (-len(compact) % 4)
                try:
                    raw = base64.b64decode(compact + padding, validate=True)
                except (binascii.Error, ValueError):
                    raw = b""
                for packed, label in _packed_variants(raw):
                    packed_text = _strict_ascii_text(packed)
                    if packed_text:
                        results.append(
                            (packed_text, f"Base64 → {label}", match.start())
                        )

        for match in list(_HEX_RE.finditer(text))[:6]:
            token = match.group(0)
            try:
                raw = bytes.fromhex(token)
            except ValueError:
                continue
            if not raw:
                continue
            decoded = raw.decode("utf-8", "replace")
            if is_probably_text(decoded.encode("utf-8", "ignore")):
                results.append((decoded, "Hex 解码", match.start()))
            results.extend(self._hex_extras(raw, match.start(), decoded))
            if len(raw) <= 8192:
                for text_variant, key in self._xor_text_variants(raw):
                    results.append(
                        (
                            text_variant,
                            f"Hex 字节单字节 XOR 解码（0x{key:02X}）",
                            match.start(),
                        )
                    )

        for match in list(_HEX_SPACED_RE.finditer(text))[:4]:
            token = re.sub(r"[\s:]", "", match.group(0))
            try:
                raw = bytes.fromhex(token)
            except ValueError:
                continue
            decoded = raw.decode("utf-8", "replace")
            if decoded and is_probably_text(decoded.encode("utf-8", "ignore")):
                results.append((decoded, "Hex 解码", match.start()))
            results.extend(self._hex_extras(raw, match.start(), decoded))

        for match in list(_BASE32_RE.finditer(stripped))[:4]:
            token = match.group(0)
            decoded = self._try_base32(token)
            if decoded:
                results.append((decoded, "Base32 解码", match.start() if match else 0))

        for match in list(_BASE58_RE.finditer(text))[:6]:
            decoded = _try_base58(match.group(0))
            if decoded:
                results.append((decoded, "Base58 解码", match.start()))

        for match in list(_BASE85_RUN_RE.finditer(text))[:6]:
            for decoded in _try_base85(match.group(0)):
                results.append((decoded, "Base85 解码", match.start()))

        if ("{" in stripped or "(" in stripped) and len(stripped) <= 8192:
            for shift in range(1, 26):
                shifted = _caesar_text(stripped, shift)
                if self._flag_hit(shifted):
                    results.append((shifted, f"凯撒位移还原（-{shift}）", 0))
            if len(stripped) <= 4096:
                for key_a in _AFFINE_KEYS:
                    for key_b in range(26):
                        if key_a == 1 and key_b == 0:
                            continue
                        plain = _affine_decipher_text(stripped, key_a, key_b)
                        if self._flag_hit(plain):
                            results.append(
                                (plain, f"仿射还原（a={key_a}, b={key_b}）", 0)
                            )

        if _HTML_ENTITY_RE.search(stripped):
            decoded = html.unescape(stripped)
            if decoded != stripped and is_probably_text(decoded.encode("utf-8", "ignore")):
                results.append((decoded, "HTML 实体解码", 0))

        if len(_UNICODE_ESCAPE_RE.findall(stripped)) >= 4:
            decoded = _UNICODE_ESCAPE_RE.sub(
                lambda match: chr(int(match.group(1), 16)), stripped
            )
            if decoded != stripped and is_probably_text(decoded.encode("utf-8", "ignore")):
                results.append((decoded, "Unicode 转义解码", 0))

        for match in list(_QP_RUN_RE.finditer(stripped))[:4]:
            try:
                raw = quopri.decodestring(match.group(0).encode("ascii"))
            except (ValueError, UnicodeEncodeError):
                continue
            decoded = _strict_ascii_text(raw)
            if decoded:
                results.append((decoded, "Quoted-Printable 解码", match.start()))

        if len(stripped) <= 8192:
            folded = _fold_js_concat(stripped) if "+" in stripped else stripped
            if folded != stripped:
                results.append((folded, "JS 字符串拼接还原", 0))
            if ".join" in stripped.lower():
                joined = _join_js_array(stripped)
                if joined != stripped and joined != folded:
                    results.append((joined, "JS 数组 join 还原", 0))

        results.extend(self._numeric_text_decoders(stripped))
        return results

    def _hex_extras(self, raw: bytes, offset: int, utf8_text: str) -> list[tuple[str, str, int]]:
        extras: list[tuple[str, str, int]] = []
        if len(raw) % 2 == 0:
            try:
                utf16 = raw.decode("utf-16-le")
            except UnicodeDecodeError:
                utf16 = ""
            if (
                utf16
                and utf16 != utf8_text
                and _strict_ascii_text(utf16.encode("utf-8", "ignore"))
            ):
                extras.append((utf16, "Hex → UTF-16LE 解码", offset))
        for packed, label in _packed_variants(raw):
            packed_text = _strict_ascii_text(packed)
            if packed_text:
                extras.append((packed_text, f"Hex → {label}", offset))
        return extras

    def _numeric_text_decoders(self, stripped: str) -> list[tuple[str, str, int]]:
        results: list[tuple[str, str, int]] = []

        for match in list(_CODE_LIST_RE.finditer(stripped))[:4]:
            tokens = re.split(r"\s*,\s*", match.group(1).strip())
            if all(token.isdigit() and 32 <= int(token) <= 126 for token in tokens):
                decoded = "".join(chr(int(token)) for token in tokens)
                if _strict_ascii_text(decoded.encode("utf-8")):
                    results.append((decoded, "字符码列表解码", match.start()))

        for match in list(_DECIMAL_RUN_RE.finditer(stripped))[:4]:
            tokens = re.split(r"[\s,]+", match.group(0).strip())
            if all(token.isdigit() and 32 <= int(token) <= 126 for token in tokens):
                decoded = "".join(chr(int(token)) for token in tokens)
                if _strict_ascii_text(decoded.encode("utf-8")):
                    results.append((decoded, "十进制 ASCII 解码", match.start()))

        for match in list(_OCTAL_RUN_RE.finditer(stripped))[:4]:
            tokens = match.group(0).split()
            try:
                values = [int(token, 8) for token in tokens]
            except ValueError:
                continue
            if all(32 <= value <= 126 for value in values):
                decoded = "".join(chr(value) for value in values)
                if _strict_ascii_text(decoded.encode("utf-8")):
                    results.append((decoded, "八进制 ASCII 解码", match.start()))

        for regex, label in (
            (_BINARY_RUN_RE, "二进制 ASCII 解码"),
            (_BINARY_SPACED_RE, "二进制 ASCII 解码"),
        ):
            for match in list(regex.finditer(stripped))[:2]:
                bits = re.sub(r"[\s:]+", "", match.group(0))
                if len(bits) % 8:
                    continue
                raw = bytes(int(bits[index : index + 8], 2) for index in range(0, len(bits), 8))
                decoded = _strict_ascii_text(raw)
                if decoded:
                    results.append((decoded, label, match.start()))
        return results

    def _xor_text_variants(self, raw: bytes, limit: int = 2) -> list[tuple[str, int]]:
        found: list[tuple[str, int]] = []
        for key in range(1, 256):
            text = raw.translate(_XOR_TABLES[key]).decode("latin-1")
            if "{" not in text and "(" not in text:
                continue
            for regex in [*self._compiled, *self._loose_compiled]:
                match = regex.search(text)
                if match and self._xor_context_is_readable(text, match.start(), match.end()):
                    found.append((text, key))
                    break
            if len(found) >= limit:
                break
        return found

    def _try_base64(self, token: str) -> str:
        compact = re.sub(r"\s+", "", token)
        if len(compact) < 12:
            return ""
        padding = "=" * (-len(compact) % 4)
        try:
            raw = base64.b64decode(compact + padding, validate=True)
        except (binascii.Error, ValueError):
            return ""
        if not raw:
            return ""
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ""
        if not is_probably_text(text.encode("utf-8", "ignore")):
            return ""
        return text

    def _try_base32(self, token: str) -> str:
        compact = re.sub(r"\s+", "", token)
        padding = "=" * (-len(compact) % 8)
        try:
            raw = base64.b32decode(compact + padding, casefold=True)
            text = raw.decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return ""
        if is_probably_text(text.encode("utf-8", "ignore")):
            return text
        return ""

    def _xor_scan(self, data: bytes, source: str) -> list[FlagCandidate]:
        if source in self._xor_sources:
            return []
        self._xor_sources.add(source)
        raw = data[:_XOR_SCAN_LIMIT]
        if not raw:
            return []
        found: list[FlagCandidate] = []
        for key in range(1, 256):
            decoded = raw.translate(_XOR_TABLES[key])
            text = decoded.decode("latin-1")
            if "{" not in text and "(" not in text:
                continue
            for regex in [*self._compiled, *self._loose_compiled]:
                for match in regex.finditer(text):
                    value = match.group(0).strip()
                    if not value or self._is_placeholder(value):
                        continue
                    if not self._xor_context_is_readable(text, match.start(), match.end()):
                        continue
                    candidate = self._add(
                        FlagCandidate(
                            value=value,
                            status=FlagStatus.CANDIDATE,
                            confidence=0.72,
                            source=source,
                            offset=match.start(),
                            method=f"单字节 XOR 解码（0x{key:02X}）",
                            evidence=(
                                "XOR 解码后的可打印上下文中匹配到 Flag 格式："
                                f"{self._xor_context(text, match.start(), match.end())}"
                            ),
                        )
                    )
                    if candidate:
                        found.append(candidate)
            if len(self.candidates) >= self.max_results:
                break
        return found

    @staticmethod
    def _xor_context(text: str, start: int, end: int, width: int = 32) -> str:
        left = max(start - width, 0)
        right = min(end + width, len(text))
        return " ".join(text[left:right].split())

    @staticmethod
    def _xor_context_is_readable(text: str, start: int, end: int, width: int = 32) -> bool:
        left = max(start - width, 0)
        right = min(end + width, len(text))
        window = text[left:right]
        if not window:
            return False
        readable = sum(
            1
            for char in window
            if 32 <= ord(char) <= 126 or char in "\t\r\n"
        )
        return readable / len(window) >= 0.85

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        match = _PLACEHOLDER_RE.match(value.strip())
        if not match:
            return False
        inner = match.group("inner").strip()
        if not inner:
            return True
        lowered = inner.lower()
        if lowered in _PLACEHOLDER_VALUES:
            return True
        if re.fullmatch(r"[.\s\-_?*…·]+", inner):
            return True
        if inner.startswith(("...", "…", "???")):
            return True
        if re.fullmatch(r"[<\[].{0,60}[>\]]", inner):
            return True
        words = [word for word in re.split(r"[^a-z0-9]+", lowered) if word]
        if words and all(word in _PLACEHOLDER_WORDS for word in words):
            if any(word in _PLACEHOLDER_STRONG for word in words):
                return True
        return False

    def _add(self, candidate: FlagCandidate) -> FlagCandidate | None:
        if self._is_placeholder(candidate.value):
            return None
        key = candidate.value
        existing = self.candidates.get(key)
        if existing:
            rank = {
                FlagStatus.CANDIDATE: 1,
                FlagStatus.FOUND: 2,
                FlagStatus.VERIFIED: 3,
            }
            if rank.get(candidate.status, 0) > rank.get(existing.candidate.status, 0):
                candidate.confidence = max(candidate.confidence, existing.candidate.confidence)
                candidate.verified = candidate.status == FlagStatus.VERIFIED
                self.candidates[key] = _Entry(candidate, existing.order)
                return candidate
            existing.candidate.confidence = max(
                existing.candidate.confidence, candidate.confidence
            )
            return None
        if len(self.candidates) >= self.max_results:
            self.warnings.append("Flag 候选超过数量上限，后续结果已截断。")
            return None
        self._order += 1
        self.candidates[key] = _Entry(candidate, self._order)
        return candidate

    def all_candidates(self) -> list[FlagCandidate]:
        items = sorted(
            (entry.candidate for entry in self.candidates.values()),
            key=lambda item: (
                {FlagStatus.VERIFIED: 0, FlagStatus.FOUND: 1, FlagStatus.CANDIDATE: 2}.get(
                    item.status, 3
                ),
                -item.confidence,
                item.value,
            ),
        )
        return items
