from __future__ import annotations

import base64
import codecs
import gzip
import zlib

from secone.core.flag_engine import FlagEngine
from secone.domain import FlagStatus


def make_engine(depth: int = 3) -> FlagEngine:
    return FlagEngine(
        patterns=[r"(?i)\bflag\{[^{}\r\n]{1,200}\}", r"(?i)\bctf\{[^{}\r\n]{1,200}\}"],
        decode_depth=depth,
    )


def _caesar_encrypt(text: str, shift: int) -> str:
    out = []
    for char in text:
        if "a" <= char <= "z":
            out.append(chr(ord("a") + (ord(char) - ord("a") + shift) % 26))
        elif "A" <= char <= "Z":
            out.append(chr(ord("A") + (ord(char) - ord("A") + shift) % 26))
        else:
            out.append(char)
    return "".join(out)


def _atbash(text: str) -> str:
    out = []
    for char in text:
        if "a" <= char <= "z":
            out.append(chr(ord("z") - (ord(char) - ord("a"))))
        elif "A" <= char <= "Z":
            out.append(chr(ord("Z") - (ord(char) - ord("A"))))
        else:
            out.append(char)
    return "".join(out)


def _affine_encrypt(text: str, key_a: int, key_b: int) -> str:
    out = []
    for char in text:
        if "a" <= char <= "z":
            out.append(chr(ord("a") + (key_a * (ord(char) - ord("a")) + key_b) % 26))
        elif "A" <= char <= "Z":
            out.append(chr(ord("A") + (key_a * (ord(char) - ord("A")) + key_b) % 26))
        else:
            out.append(char)
    return "".join(out)


def _base58_encode(data: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(data, "big")
    encoded = ""
    while number:
        number, rem = divmod(number, 58)
        encoded = alphabet[rem] + encoded
    for byte in data:
        if byte:
            break
        encoded = "1" + encoded
    return encoded


def test_direct_flag_is_found() -> None:
    engine = make_engine()
    flags = engine.scan_direct("prefix flag{d1rect_h1t} suffix", "notes.txt")
    assert [flag.value for flag in flags] == ["flag{d1rect_h1t}"]
    assert flags[0].status == FlagStatus.FOUND
    assert flags[0].confidence == 1.0
    assert flags[0].offset is not None


def test_placeholder_flags_are_rejected() -> None:
    engine = make_engine()
    text = "提交格式 flag{...} / flag{xxxx} / flag{your_flag_here} / flag{<value>}"
    flags = engine.scan_direct(text, "notes.txt")
    assert flags == []


def test_placeholder_does_not_hide_real_flag() -> None:
    engine = make_engine()
    text = "格式 flag{...}，真实答案 flag{r3al_4nsw3r}"
    flags = engine.scan_direct(text, "notes.txt")
    assert [flag.value for flag in flags] == ["flag{r3al_4nsw3r}"]


def test_base64_hex_rot13_and_xor_are_recovered() -> None:
    expected = {
        "base64": "flag{b64_p4yl0ad}",
        "hex": "flag{h3x_p4yl0ad}",
        "rot": "flag{r0t_p4yl0ad}",
    }
    text = "\n".join(
        [
            base64.b64encode(expected["base64"].encode()).decode(),
            expected["hex"].encode().hex(),
            codecs.encode(expected["rot"], "rot_13"),
        ]
    )
    engine = make_engine()
    engine.analyze_text(text, "encoded.txt")
    values = {flag.value for flag in engine.all_candidates()}
    assert set(expected.values()) <= values

    xor_flag = b"flag{x0r_p4yl0ad}"
    engine = make_engine()
    engine.analyze_bytes(bytes(byte ^ 0x37 for byte in xor_flag), "blob.bin")
    assert any(flag.value == xor_flag.decode() for flag in engine.all_candidates())


def test_duplicate_flag_from_two_sources_is_merged() -> None:
    engine = make_engine()
    engine.scan_direct("flag{same_value}", "one.txt")
    engine.scan_direct("flag{same_value}", "two.txt")
    assert len(engine.all_candidates()) == 1


def test_candidate_status_upgrades_to_found() -> None:
    engine = make_engine()
    engine.scan_candidate("flag{upgr4d3}", "decoded.txt", "Base64 解码", 0.7)
    engine.scan_direct("flag{upgr4d3}", "notes.txt")
    flags = engine.all_candidates()
    assert len(flags) == 1
    assert flags[0].status == FlagStatus.FOUND


def test_ai_candidates_require_exact_material_evidence() -> None:
    engine = make_engine()
    material = "材料中真实存在 flag{grounded_v4lue}"
    response = "我认为答案是 flag{grounded_v4lue}，另一个是 flag{hallucinated}。"
    added, rejected = engine.add_ai_candidates(response, material)
    assert [flag.value for flag in added] == ["flag{grounded_v4lue}"]
    assert rejected == ["flag{hallucinated}"]
    assert added[0].status == FlagStatus.CANDIDATE
    assert added[0].ai_generated is True


def test_whole_text_reversal_is_recovered() -> None:
    engine = make_engine()
    engine.analyze_text("suffix " + "flag{revers3d_p4yl0ad}"[::-1] + " prefix", "reversed.txt")
    flags = engine.all_candidates()
    assert [flag.value for flag in flags] == ["flag{revers3d_p4yl0ad}"]
    assert flags[0].status == FlagStatus.CANDIDATE


def test_hex_encoded_xor_ciphertext_is_recovered() -> None:
    engine = make_engine()
    ciphertext = bytes(byte ^ 0x42 for byte in b"flag{h3x_x0r_p4yl0ad}")
    engine.analyze_bytes(ciphertext.hex().encode(), "payload.hex")
    flags = engine.all_candidates()
    assert [flag.value for flag in flags] == ["flag{h3x_x0r_p4yl0ad}"]


def test_plain_hex_without_flag_produces_no_candidate() -> None:
    engine = make_engine()
    engine.analyze_text(bytes(b"hello world, nothing hidden here").hex(), "plain.hex")
    assert engine.all_candidates() == []


def test_atbash_caesar_and_affine_are_recovered() -> None:
    cases = {
        "atbash": _atbash("flag{atbash_mirr0r}"),
        "caesar3": _caesar_encrypt("flag{caesar_thr33}", 3),
        "caesar7": _caesar_encrypt("flag{caesar_sev7n}", 7),
        "affine": _affine_encrypt("flag{affine_5_8}", 5, 8),
    }
    expected = {
        "flag{atbash_mirr0r}",
        "flag{caesar_thr33}",
        "flag{caesar_sev7n}",
        "flag{affine_5_8}",
    }
    engine = make_engine()
    engine.analyze_text("\n".join(cases.values()), "classical.txt")
    values = {flag.value for flag in engine.all_candidates()}
    assert expected <= values
    methods = " ".join(flag.method for flag in engine.all_candidates())
    assert "Atbash" in methods
    assert "凯撒" in methods
    assert "仿射" in methods


def test_base58_and_base85_are_recovered() -> None:
    payload = "flag{b58_b85_dec0ded}".encode()
    engine = make_engine()
    engine.analyze_text(
        "\n".join(
            [
                _base58_encode(payload),
                base64.b85encode(payload).decode(),
                base64.a85encode(payload).decode(),
            ]
        ),
        "encodings.txt",
    )
    values = {flag.value for flag in engine.all_candidates()}
    assert values == {"flag{b58_b85_dec0ded}"}


def test_numeric_text_forms_are_recovered() -> None:
    payload = "flag{num3r1c_f0rms}".encode()
    representations = {
        "十进制": " ".join(str(byte) for byte in payload),
        "八进制": " ".join(f"{byte:o}" for byte in payload),
        "字符码列表": "[" + ", ".join(str(byte) for byte in payload) + "]",
        "二进制": "".join(format(byte, "08b") for byte in payload),
    }
    for label, text in representations.items():
        engine = make_engine()
        engine.analyze_text(text, "numeric.txt")
        flags = engine.all_candidates()
        assert [flag.value for flag in flags] == ["flag{num3r1c_f0rms}"], label
        assert label in flags[0].method, label


def test_html_unicode_and_quoted_printable_are_recovered() -> None:
    payload = "flag{esc4p3_f0rms}".encode()
    representations = {
        "HTML 实体": "".join(f"&#{byte};" for byte in payload),
        "Unicode 转义": "".join(f"\\u{byte:04x}" for byte in payload),
        "Quoted-Printable": "".join(f"={byte:02X}" for byte in payload),
    }
    for label, text in representations.items():
        engine = make_engine()
        engine.analyze_text(text, "escapes.txt")
        flags = engine.all_candidates()
        assert [flag.value for flag in flags] == ["flag{esc4p3_f0rms}"], label
        assert label in flags[0].method, label


def test_js_concat_and_array_join_are_recovered() -> None:
    engine = make_engine()
    engine.analyze_text(
        "\n".join(
            [
                'const answer = "flag{" + "js_c0ncat" + "_f0rm}";',
                'console.log(["flag", "{js_", "j0ined}"].join(""));',
            ]
        ),
        "script.js",
    )
    values = {flag.value for flag in engine.all_candidates()}
    assert values == {"flag{js_c0ncat_f0rm}", "flag{js_j0ined}"}


def test_js_concat_raw_artifact_is_not_a_candidate() -> None:
    engine = make_engine()
    engine.analyze_text('const answer = "flag{" + "js_c0ncat" + "}";', "script.js")
    values = [flag.value for flag in engine.all_candidates()]
    assert values == ["flag{js_c0ncat}"]


def test_packed_and_wide_char_payloads_are_recovered() -> None:
    payload = "flag{p4ck3d_f0rms}".encode()
    wide_bytes = "flag{p4ck3d_f0rms}".encode("utf-16-le")
    spaced_hex = " ".join(
        wide_bytes[index : index + 2].hex() for index in range(0, len(wide_bytes), 2)
    )
    representations = [
        ("gzip", base64.b64encode(gzip.compress(payload)).decode()),
        ("zlib", zlib.compress(payload).hex()),
        ("UTF-16LE", "flag{p4ck3d_f0rms}".encode("utf-16-le").hex()),
        ("UTF-16LE", spaced_hex),
    ]
    for label, text in representations:
        engine = make_engine()
        engine.analyze_text(text, "packed.txt")
        flags = engine.all_candidates()
        assert [flag.value for flag in flags] == ["flag{p4ck3d_f0rms}"], label
        assert label in flags[0].method, label


def test_base58_garbage_from_plain_words_is_filtered() -> None:
    engine = make_engine()
    engine.analyze_text("ckdbfkdbskjbbkjbsdhbksjdbdbskjd", "notes.txt")
    assert engine.all_candidates() == []


def test_flag_inside_log_wrapper_is_recovered() -> None:
    engine = make_engine()
    engine.analyze_text('console.log("flag{wr4pp3d_l0g}");', "script.js")
    values = [flag.value for flag in engine.all_candidates()]
    assert values == ["flag{wr4pp3d_l0g}"]
