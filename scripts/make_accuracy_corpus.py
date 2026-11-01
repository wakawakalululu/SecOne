#!/usr/bin/env python
"""Build the v4 accuracy corpus from v3 plus programmatically encoded cases.

Every new case is constructed by encoding a known flag, so the ground truth
cannot drift from the material. The script refuses to write output if a new
answer appears verbatim in its own material.

Usage:
  .\\.python\\python.exe scripts\\make_accuracy_corpus.py
"""

from __future__ import annotations

import base64
import gzip
import json
import quopri
import re
import sys
import textwrap
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "benchmarks" / "ctf_accuracy_v3.json"
V4 = ROOT / "benchmarks" / "ctf_accuracy_v4.json"
FLAG_RE = re.compile(r"flag\{[^{}\r\n]{1,200}\}", re.IGNORECASE)


def caesar(text: str, shift: int) -> str:
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + shift) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + shift) % 26 + 65))
        else:
            out.append(ch)
    return "".join(out)


def affine(text: str) -> str:
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out.append(chr((5 * (ord(ch) - 97) + 8) % 26 + 97))
        else:
            out.append(ch)
    return "".join(out)


def rot13(text: str) -> str:
    return caesar(text, 13)


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def b64url_nopad(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def b32(text: str) -> str:
    return base64.b32encode(text.encode()).decode()


def b32_nopad(text: str) -> str:
    return b32(text).rstrip("=")


def hex_colons(text: str) -> str:
    return ":".join(f"{byte:02X}" for byte in text.encode())


def hex_pairs_upper(text: str) -> str:
    return " ".join(f"{byte:02X}" for byte in text.encode())


def b85(text: str) -> str:
    return base64.b85encode(text.encode()).decode()


def a85(text: str) -> str:
    return base64.a85encode(text.encode()).decode()


def utf16le_hex(text: str) -> str:
    return text.encode("utf-16-le").hex()


def gzip_b64(text: str) -> str:
    # zlib 写入 gzip 头部的 OS 字节（第 10 字节）随宿主平台变化
    # （本仓库 Windows 环境为 0x0a，Linux 为 0x03），固定为已提交语料中的
    # 取值，保证生成器输出与 benchmarks/ctf_accuracy_v4.json 跨平台一致。
    raw = gzip.compress(text.encode(), mtime=0)
    normalized = raw[:9] + b"\x0a" + raw[10:]
    return base64.b64encode(normalized).decode()


def zlib_hex(text: str) -> str:
    return zlib.compress(text.encode()).hex()


def html_entities(text: str) -> str:
    return "".join(f"&#{ord(ch)};" for ch in text)


def unicode_escapes(text: str) -> str:
    return "".join(f"\\u{ord(ch):04x}" for ch in text)


def qp_fully(text: str) -> str:
    return quopri.encodestring(text.encode(), quotetabs=True).decode().replace("\n", "\n")


def qp_every_byte(text: str) -> str:
    return "".join(f"={byte:02X}" for byte in text.encode())


def b64_wrapped(text: str) -> str:
    return "\n".join(textwrap.wrap(b64(text), 60))


def js_concat(text: str) -> str:
    parts = [text[i : i + 5] for i in range(0, len(text), 5)]
    return "+".join(json.dumps(part) for part in parts)


def py_charcodes(text: str) -> str:
    return "[" + ", ".join(str(byte) for byte in text.encode()) + "]"


def xor_hex(text: str, key: int) -> str:
    return bytes(byte ^ key for byte in text.encode()).hex()


def jwt_like(text: str) -> str:
    header = b64url_nopad(json.dumps({"alg": "none", "typ": "JWT"}))
    payload = b64url_nopad(json.dumps({"sub": "ctf", "flag": text}))
    signature = b64url_nopad("secone-bench")
    return f"{header}.{payload}.{signature}"


# (id, category, flag, material body, hint)
NEW_CASES: list[tuple[str, str, str, str, str]] = [
    (
        "b64url-nopad-01",
        "base64url",
        "flag{b64url_n0_p4dd1ng_2026}",
        b64url_nopad("flag{b64url_n0_p4dd1ng_2026}"),
        "材料是去掉了 = 填充的 Base64URL 编码，解码后得到答案。",
    ),
    (
        "b64url-nopad-02",
        "base64url",
        "flag{b64url_ur1_s4fe_2026}",
        b64url_nopad("flag{b64url_ur1_s4fe_2026}"),
        "材料是 Base64URL（-_ 字母表）编码，解码后得到答案。",
    ),
    (
        "b32-nopad-01",
        "base32_nopad",
        "flag{b32_no_p4d_2026}",
        b32_nopad("flag{b32_no_p4d_2026}"),
        "材料是去掉填充的 Base32 编码，解码后得到答案。",
    ),
    (
        "b32-nopad-02",
        "base32_nopad",
        "flag{b32_std_pad_2026}",
        b32("flag{b32_std_pad_2026}"),
        "材料是带 = 填充的标准 Base32 编码，解码后得到答案。",
    ),
    (
        "hex-colon-01",
        "hex_upper_colon",
        "flag{hex_upper_colons_2026}",
        hex_colons("flag{hex_upper_colons_2026}"),
        "材料是大写十六进制、字节间用冒号分隔，去掉冒号转 ASCII 后得到答案。",
    ),
    (
        "hex-colon-02",
        "hex_upper_colon",
        "flag{hex_upper_pairs_2026}",
        hex_pairs_upper("flag{hex_upper_pairs_2026}"),
        "材料是大写十六进制、字节间用空格分隔，转 ASCII 后得到答案。",
    ),
    (
        "base85-01",
        "base85",
        "flag{base85_t3xt_2026}",
        b85("flag{base85_t3xt_2026}"),
        "材料是 Base85（RFC 1924 字母表）编码，解码后得到答案。",
    ),
    (
        "base85-02",
        "base85",
        "flag{ascii85_str34m_2026}",
        a85("flag{ascii85_str34m_2026}"),
        "材料是 Ascii85 编码，解码后得到答案。",
    ),
    (
        "utf16le-01",
        "utf16le_hex",
        "flag{utf16le_bytes_2026}",
        utf16le_hex("flag{utf16le_bytes_2026}"),
        "材料是 UTF-16LE 字节串的十六进制，按 2 字节小端还原后得到答案。",
    ),
    (
        "utf16le-02",
        "utf16le_hex",
        "flag{utf16le_l1ttle_2026}",
        " ".join(
            utf16le_hex("flag{utf16le_l1ttle_2026}")[i : i + 4]
            for i in range(0, len(utf16le_hex("flag{utf16le_l1ttle_2026}")), 4)
        ),
        "材料是 UTF-16LE 十六进制、每 4 位一组，还原后得到答案。",
    ),
    (
        "gzip-b64-01",
        "gzip_base64",
        "flag{gz1p_wr4pp3d_2026}",
        gzip_b64("flag{gz1p_wr4pp3d_2026}"),
        "材料是 gzip 压缩后再做 Base64，解 Base64 再解压得到答案。",
    ),
    (
        "gzip-b64-02",
        "gzip_base64",
        "flag{gzip_blob_b64_2026}",
        "\n".join(textwrap.wrap(gzip_b64("flag{gzip_blob_b64_2026}"), 60)),
        "材料是 gzip 压缩后再做 Base64（每 60 字符换行），解压后得到答案。",
    ),
    (
        "zlib-hex-01",
        "zlib_hex",
        "flag{zlib_compressed_2026}",
        zlib_hex("flag{zlib_compressed_2026}"),
        "材料是 zlib 压缩后的十六进制，先转字节再解压得到答案。",
    ),
    (
        "zlib-hex-02",
        "zlib_hex",
        "flag{zlib_then_hex_2026}",
        zlib_hex("flag{zlib_then_hex_2026}"),
        "材料是 zlib deflate 流的十六进制，先转字节再解压得到答案。",
    ),
    (
        "html-entities-01",
        "html_entities",
        "flag{html_ent1t1es_2026}",
        html_entities("flag{html_ent1t1es_2026}"),
        "材料是 HTML 十进制字符实体，还原实体后得到答案。",
    ),
    (
        "html-entities-02",
        "html_entities",
        "flag{html_decimal_2026}",
        html_entities("flag{html_decimal_2026}"),
        "材料是 HTML 实体编码（&#NN;），解码后得到答案。",
    ),
    (
        "unicode-escape-01",
        "unicode_escape",
        "flag{unicode_esc4pe_2026}",
        unicode_escapes("flag{unicode_esc4pe_2026}"),
        "材料是 \\uXXXX 形式的 Unicode 转义，还原后得到答案。",
    ),
    (
        "unicode-escape-02",
        "unicode_escape",
        "flag{unicode_u_form_2026}",
        unicode_escapes("flag{unicode_u_form_2026}"),
        "材料是 JSON 风格的 Unicode 转义序列，还原后得到答案。",
    ),
    (
        "qp-01",
        "quoted_printable",
        "flag{qp_fully_enc_2026}",
        qp_every_byte("flag{qp_fully_enc_2026}"),
        "材料是 Quoted-Printable 全字节编码（=XX 形式），解码后得到答案。",
    ),
    (
        "qp-02",
        "quoted_printable",
        "flag{quoted_printable_2026}",
        qp_every_byte("flag{quoted_printable_2026}"),
        "材料是 Quoted-Printable 编码，解码后得到答案。",
    ),
    (
        "b64-wrapped-01",
        "base64_wrapped",
        "flag{b64_wr4pped_lines_2026}",
        b64_wrapped("flag{b64_wr4pped_lines_2026}"),
        "材料是每 60 字符换行的 Base64，去掉换行后解码得到答案。",
    ),
    (
        "b64-wrapped-02",
        "base64_wrapped",
        "flag{b64_line_breaks_2026}",
        b64_wrapped("flag{b64_line_breaks_2026}"),
        "材料是 PEM 风格的折行 Base64，拼接后解码得到答案。",
    ),
    (
        "b64-rot13-02",
        "base64_then_rot13",
        "flag{b64_then_r0t13b_2026}",
        rot13(b64("flag{b64_then_r0t13b_2026}")),
        "材料先做 Base64 再对整段做 ROT13，先反 ROT13 再解码得到答案。",
    ),
    (
        "b64-rot13-03",
        "base64_then_rot13",
        "flag{rot13_of_b64_text_2026}",
        rot13(b64("flag{rot13_of_b64_text_2026}")),
        "材料是 ROT13 处理过的 Base64 串，还原两级变换后得到答案。",
    ),
    (
        "b32-reversed-01",
        "base32_then_reversed",
        "flag{b32_then_r3versed_2026}",
        b32("flag{b32_then_r3versed_2026}")[::-1],
        "材料是 Base32 结果整体倒序，先反转再 Base32 解码得到答案。",
    ),
    (
        "b32-reversed-02",
        "base32_then_reversed",
        "flag{reverse_b32_payload_2026}",
        b32("flag{reverse_b32_payload_2026}")[::-1],
        "材料为倒序的 Base32 编码，还原得到答案。",
    ),
    (
        "js-concat-01",
        "js_string_concat",
        "flag{js_string_c0ncat_2026}",
        "const answer = " + js_concat("flag{js_string_c0ncat_2026}") + ";",
        "材料是 JavaScript 字符串拼接，拼接各段后得到答案。",
    ),
    (
        "js-concat-02",
        "js_string_concat",
        "flag{js_parts_joined_2026}",
        "console.log([" + ", ".join(json.dumps(p) for p in textwrap.wrap("flag{js_parts_joined_2026}", 4)) + "].join(''));",
        "材料是 JavaScript 数组拼接，按顺序连接后得到答案。",
    ),
    (
        "py-charcodes-01",
        "char_code_list",
        "flag{py_charcodes_2026}",
        "answer = " + py_charcodes("flag{py_charcodes_2026}"),
        "材料是 Python 整数列表，每个整数是一个 ASCII 码，转换后得到答案。",
    ),
    (
        "py-charcodes-02",
        "char_code_list",
        "flag{char_code_list_2026}",
        "codes = " + py_charcodes("flag{char_code_list_2026}") + "\nanswer = ''.join(chr(c) for c in codes)",
        "材料是 Python 整数列表和拼接代码，按 ASCII 码还原得到答案。",
    ),
    (
        "caesar7-01",
        "caesar_7",
        "flag{caesar_plus_seven_2026}",
        caesar("flag{caesar_plus_seven_2026}", 7),
        "材料经过凯撒 +7 位移，向前回移 7 位得到答案。",
    ),
    (
        "caesar7-02",
        "caesar_7",
        "flag{shift_by_seven_2026}",
        caesar("flag{shift_by_seven_2026}", 7),
        "材料是字母表位移 7 位后的文本，还原后得到答案。",
    ),
    (
        "affine-01",
        "affine_cipher",
        "flag{affine_5_8_2026}",
        affine("flag{affine_5_8_2026}"),
        "材料经过仿射变换 y=(5x+8) mod 26（仅小写字母），逆变换后得到答案。",
    ),
    (
        "affine-02",
        "affine_cipher",
        "flag{affine_mapping_2026}",
        affine("flag{affine_mapping_2026}"),
        "材料是仿射密码密文（a=5, b=8），解出后得到答案。",
    ),
    (
        "xor-13-01",
        "xor_0x13",
        "flag{xor_key_0x13_2026}",
        xor_hex("flag{xor_key_0x13_2026}", 0x13),
        "材料是单字节 XOR 密文（hex），明文为可打印 ASCII 且以 flag{ 开头。",
    ),
    (
        "xor-13-02",
        "xor_0x13",
        "flag{xor_0x13_mask_2026}",
        xor_hex("flag{xor_0x13_mask_2026}", 0x13),
        "材料是单字节 XOR 密文（hex），密钥未知但明文以 flag{ 开头。",
    ),
]


def build() -> dict:
    source = json.loads(V3.read_text(encoding="utf-8"))
    cases = list(source["cases"])
    existing = {case["id"] for case in cases}

    added: list[dict] = []
    for case_id, category, flag, body, hint in NEW_CASES:
        if case_id in existing:
            raise SystemExit(f"重复用例 id：{case_id}")
        if not FLAG_RE.fullmatch(flag):
            raise SystemExit(f"标准答案不合法：{flag!r}")
        material = f"题干提示：{hint}\n{body}"
        if flag in material:
            raise SystemExit(f"答案以字面形式出现在材料中：{case_id}")
        added.append(
            {
                "id": case_id,
                "category": category,
                "material": material,
                "flag": flag,
                "hint": hint,
                "flag_literal_in_material": False,
            }
        )

    return {
        "version": 4,
        "name": "SecOne CTF 准确性样本 v4",
        "note": (
            "内部基准：v3 的 24 条加 36 条程序化编码样本，共 60 条精确标准答案。"
            "新增样本由 scripts/make_accuracy_corpus.py 从答案反向编码生成，"
            "每条都断言答案不以字面形式出现在材料中。样本量仍不足以给出正式准确率。"
        ),
        "cases": cases + added,
    }


def main() -> int:
    corpus = build()
    V4.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    categories = {case["category"] for case in corpus["cases"]}
    print(f"wrote {V4} · {len(corpus['cases'])} cases · {len(categories)} categories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
