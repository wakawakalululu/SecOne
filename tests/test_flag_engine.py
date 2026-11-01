from __future__ import annotations

import base64
import codecs

from secone.core.flag_engine import FlagEngine
from secone.domain import FlagStatus


def make_engine(depth: int = 3) -> FlagEngine:
    return FlagEngine(
        patterns=[r"(?i)\bflag\{[^{}\r\n]{1,200}\}", r"(?i)\bctf\{[^{}\r\n]{1,200}\}"],
        decode_depth=depth,
    )


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
