from __future__ import annotations

import base64
import codecs
import io
import zipfile
from pathlib import Path
from urllib.parse import quote

from secone.config import AppConfig
from secone.core.flag_engine import FlagEngine
from secone.core.ingest import IngestEngine
from secone.core.workspace import TaskWorkspace
from secone.domain import FlagStatus

PATTERNS = [r"(?i)\bflag\{[^{}\r\n]{1,200}\}", r"(?i)\bctf\{[^{}\r\n]{1,200}\}"]


def make_engine() -> FlagEngine:
    return FlagEngine(patterns=PATTERNS, decode_depth=3)


def rot47(text: str) -> str:
    return "".join(
        chr(33 + (ord(char) - 33 + 47) % 94) if 33 <= ord(char) <= 126 else char
        for char in text
    )


def xor_with_key(value: str, key: int) -> bytes:
    return bytes(byte ^ key for byte in value.encode("utf-8"))


def scan_sample(sample: dict) -> set[str]:
    engine = make_engine()
    if "text" in sample:
        engine.analyze_text(sample["text"], sample["name"])
    else:
        engine.analyze_bytes(sample["bytes"], sample["name"])
    return {flag.value for flag in engine.all_candidates()}


def benchmark_samples() -> tuple[list[tuple[dict, str]], list[dict]]:
    direct = "flag{d1rect_h1t}"
    positive = [
        ({"name": "direct.txt", "text": f"answer: {direct}"}, direct),
        (
            {
                "name": "base64.txt",
                "text": base64.b64encode(b"flag{b64_p4yl0ad}").decode(),
            },
            "flag{b64_p4yl0ad}",
        ),
        (
            {"name": "hex.txt", "text": b"flag{h3x_p4yl0ad}".hex()},
            "flag{h3x_p4yl0ad}",
        ),
        (
            {"name": "rot13.txt", "text": codecs.encode("flag{r0t13_h1t}", "rot_13")},
            "flag{r0t13_h1t}",
        ),
        (
            {"name": "rot47.txt", "text": rot47("flag{r0t47_h1t}")},
            "flag{r0t47_h1t}",
        ),
        (
            {"name": "url.txt", "text": quote("flag{url_h1t}", safe="")},
            "flag{url_h1t}",
        ),
        (
            {
                "name": "base32.txt",
                "text": base64.b32encode(b"flag{b32_h1t}").decode(),
            },
            "flag{b32_h1t}",
        ),
        (
            {
                "name": "double-base64.txt",
                "text": base64.b64encode(
                    base64.b64encode(b"flag{d0uble_b64}").rstrip(b"=")
                ).decode(),
            },
            "flag{d0uble_b64}",
        ),
        (
            {
                "name": "xor.bin",
                "bytes": bytes(range(256)) * 40
                + b" " * 32
                + xor_with_key("flag{x0r_p4yl0ad}", 0x5A)
                + b" " * 32
                + bytes(range(256)) * 10,
            },
            "flag{x0r_p4yl0ad}",
        ),
    ]
    negative = [
        {"name": "placeholder.txt", "text": "提交格式：flag{...} 或 flag{xxxx}"},
        {
            "name": "placeholder2.txt",
            "text": "flag{this_is_a_fake_flag} flag{your_flag_here} flag{example_flag}",
        },
        {
            "name": "benign.py",
            "text": "def parse(value):\n    return value.strip()\n# TODO: add tests\n",
        },
        {"name": "format.md", "text": "The flag format is ctf{...} for this challenge."},
        {
            "name": "noise.bin",
            "bytes": bytes((index * 37 + 11) % 256 for index in range(8192)),
        },
    ]
    return positive, negative


def test_xor_flag_inside_mixed_binary_is_recovered() -> None:
    expected = "flag{b1n4ry_x0r}"
    payload = (
        bytes(range(256)) * 50
        + b"\x00" * 64
        + xor_with_key(expected, 0x42)
        + b"\x00" * 64
        + bytes(range(256)) * 20
    )
    engine = make_engine()
    engine.analyze_bytes(payload, "mixed.bin")
    values = {flag.value for flag in engine.all_candidates()}
    assert expected in values


def test_placeholder_variants_are_not_reported() -> None:
    engine = make_engine()
    text = "\n".join(
        [
            "flag{...}",
            "flag{?????}",
            "flag{<flag>}",
            "flag{your_flag_here}",
            "flag{this_is_a_fake_flag}",
            "flag{test_flag}",
            "flag{example}",
            "flag{placeholder}",
        ]
    )
    assert engine.scan_direct(text, "notes.txt") == []


def test_real_flag_next_to_placeholder_is_kept() -> None:
    engine = make_engine()
    flags = engine.scan_direct(
        "格式 flag{...}，真实题目 flag{v3r1f13d_4nsw3r}", "notes.txt"
    )
    assert [flag.value for flag in flags] == ["flag{v3r1f13d_4nsw3r}"]


def test_benchmark_recall_and_precision() -> None:
    positive, negative = benchmark_samples()
    recovered: set[str] = set()
    for sample, expected in positive:
        values = scan_sample(sample)
        if expected in values:
            recovered.add(expected)
    recall = len(recovered) / len(positive)

    false_positives: list[str] = []
    for sample in negative:
        false_positives.extend(scan_sample(sample))

    assert recall == 1.0, f"recall={recall:.2f} missing={set(e for _, e in positive) - recovered}"
    assert false_positives == [], f"false positives: {false_positives}"


def test_direct_and_decoded_status_are_distinguished() -> None:
    engine = make_engine()
    engine.analyze_text(
        "flag{st4tus_direct} " + base64.b64encode(b"flag{st4tus_decoded}").decode(),
        "sample.txt",
    )
    statuses = {flag.value: flag.status for flag in engine.all_candidates()}
    assert statuses["flag{st4tus_direct}"] == FlagStatus.FOUND
    assert statuses["flag{st4tus_decoded}"] == FlagStatus.CANDIDATE


def labeled_corpus() -> tuple[list[tuple[dict, str]], list[dict]]:
    """Synthetic CTF-style corpus with explicit labels.

    This measures rule/decoder behaviour only; it is not a model-accuracy
    benchmark. Real-model accuracy stays BLOCKED until a GGUF is supplied.
    """
    nested_base64_hex = base64.b64encode(
        b"flag{b64_h3x_l4y3r}".hex().encode()
    ).decode()
    nested_base64_rot13 = base64.b64encode(
        codecs.encode("flag{n3st3d_r0t13}", "rot_13").encode()
    ).decode()
    url_of_base64 = quote(base64.b64encode(b"flag{url_b64_l4y3r}").decode(), safe="")
    long_flag = "flag{" + "l0ng_" * 18 + "t41l}"
    xor_block = (
        bytes(range(256)) * 20
        + b" " * 32
        + xor_with_key("flag{x0r_c0rpus_1}", 0x5A)
        + b" " * 32
        + bytes(range(256)) * 10
    )
    xor_ctf_block = (
        bytes(range(256)) * 12
        + b"\x00" * 48
        + xor_with_key("ctf{x0r_ctf_v4r14nt}", 0x6D)
        + b"\x00" * 48
    )
    positives = [
        ({"name": "p01-direct.txt", "text": "answer=flag{corpus_d1rect}"}, "flag{corpus_d1rect}"),
        (
            {"name": "p02-b64.txt", "text": base64.b64encode(b"flag{corpus_b64}").decode()},
            "flag{corpus_b64}",
        ),
        (
            {
                "name": "p03-b64-wrapped.txt",
                "text": "payload:\n"
                + base64.encodebytes(b"flag{corpus_b64_wr4pped}").decode(),
            },
            "flag{corpus_b64_wr4pped}",
        ),
        ({"name": "p04-hex.txt", "text": b"flag{corpus_h3x}".hex()}, "flag{corpus_h3x}"),
        (
            {
                "name": "p05-hex-spaced.txt",
                "text": " ".join(f"{byte:02x}" for byte in b"flag{corpus_h3x_g4p}"),
            },
            "flag{corpus_h3x_g4p}",
        ),
        (
            {"name": "p06-rot13.txt", "text": codecs.encode("flag{corpus_r0t13}", "rot_13")},
            "flag{corpus_r0t13}",
        ),
        ({"name": "p07-rot47.txt", "text": rot47("flag{corpus_r0t47}")}, "flag{corpus_r0t47}"),
        ({"name": "p08-url.txt", "text": quote("flag{corpus_url}", safe="")}, "flag{corpus_url}"),
        (
            {
                "name": "p09-b32.txt",
                "text": base64.b32encode(b"flag{corpus_b32}").decode(),
            },
            "flag{corpus_b32}",
        ),
        (
            {
                "name": "p10-double-b64.txt",
                "text": base64.b64encode(
                    base64.b64encode(b"flag{corpus_d0uble_b64}").rstrip(b"=")
                ).decode(),
            },
            "flag{corpus_d0uble_b64}",
        ),
        ({"name": "p11-b64-hex.txt", "text": nested_base64_hex}, "flag{b64_h3x_l4y3r}"),
        (
            {"name": "p12-b64-rot13.txt", "text": nested_base64_rot13},
            "flag{n3st3d_r0t13}",
        ),
        ({"name": "p13-url-b64.txt", "text": url_of_base64}, "flag{url_b64_l4y3r}"),
        (
            {
                "name": "p14-js-comment.txt",
                "text": "const k = 1; /* flag{corpus_js_c0mm3nt} */ console.log(k);",
            },
            "flag{corpus_js_c0mm3nt}",
        ),
        (
            {
                "name": "p15-upper.txt",
                "text": "Submit FLAG{corpus_upperc4s3} at the end.",
            },
            "FLAG{corpus_upperc4s3}",
        ),
        ({"name": "p16-ctf-prefix.txt", "text": f"proof: ctf{{corpus_ctf}}" }, "ctf{corpus_ctf}"),
        ({"name": "p17-long.txt", "text": long_flag}, long_flag),
        ({"name": "p18-xor.bin", "bytes": xor_block}, "flag{x0r_c0rpus_1}"),
        ({"name": "p19-xor-ctf.bin", "bytes": xor_ctf_block}, "ctf{x0r_ctf_v4r14nt}"),
    ]
    negatives = [
        {"name": "n01-placeholder.txt", "text": "提交格式：flag{...}"},
        {"name": "n02-placeholder2.txt", "text": "flag{?????} flag{<flag>} flag{[flag]}"},
        {
            "name": "n03-placeholder3.txt",
            "text": "flag{your_flag_here} flag{this_is_a_fake_flag} flag{test_flag}",
        },
        {"name": "n04-placeholder4.txt", "text": "flag{} flag{   }"},
        {"name": "n05-format.md", "text": "The flag format is ctf{...} for this challenge."},
        {
            "name": "n06-benign.py",
            "text": "def parse(value):\n    return value.strip()\n\n# TODO: add tests\n",
        },
        {
            "name": "n07-benign.md",
            "text": "# Notes\n\nNo secrets here. Build with `make test`.\n",
        },
        {
            "name": "n08-b64-benign.txt",
            "text": base64.b64encode(b"just a normal sentence with no answer").decode(),
        },
        {"name": "n09-hex-benign.txt", "text": b"plain notes, nothing to see".hex()},
        {"name": "n10-json.txt", "text": '{"status": "ok", "count": 3, "items": []}'},
        {"name": "n11-log.txt", "text": "2026-01-01 INFO started\n2026-01-01 WARN slow\n"},
        {
            "name": "n12-noise.bin",
            "bytes": bytes((index * 37 + 11) % 256 for index in range(16384)),
        },
        {
            "name": "n13-base64-noise.txt",
            "text": base64.b64encode(bytes(range(32, 96))).decode(),
        },
    ]
    return positives, negatives


def test_labeled_rule_corpus_precision_and_recall() -> None:
    positives, negatives = labeled_corpus()
    expected_flags = {expected for _, expected in positives}
    found_flags: set[str] = set()
    missed_samples: list[str] = []

    for sample, expected in positives:
        values = scan_sample(sample)
        found_flags.update(values)
        if expected not in values:
            missed_samples.append(f"{sample['name']} -> {expected} (got {sorted(values)})")

    false_positive_samples: list[str] = []
    for sample in negatives:
        values = scan_sample(sample)
        found_flags.update(values)
        if values:
            false_positive_samples.append(f"{sample['name']} -> {sorted(values)}")

    true_positives = len(found_flags & expected_flags)
    false_positives = len(found_flags - expected_flags)
    false_negatives = len(expected_flags - found_flags)
    precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 1.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 1.0
    )

    print(
        f"\nrule corpus: {len(positives)} positive / {len(negatives)} negative samples, "
        f"precision={precision:.3f} recall={recall:.3f} "
        f"tp={true_positives} fp={false_positives} fn={false_negatives}"
    )
    assert precision == 1.0, f"false positives: {sorted(found_flags - expected_flags)}"
    assert recall == 1.0, f"missed: {missed_samples}"
    assert false_positive_samples == [], false_positive_samples


def test_archive_member_flag_keeps_provenance(
    config: AppConfig, tmp_path: Path
) -> None:
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("inner/secret.txt", b"flag{1n_4rch1v3_pr0v3n4nc3}")
    source = tmp_path / "challenge.zip"
    source.write_bytes(archive_bytes.getvalue())

    workspace = TaskWorkspace.create(config.paths.workspace)
    result = IngestEngine(config, workspace).ingest([source])
    member = next(item for item in result.files if item.source == "archive")
    engine = make_engine()
    engine.analyze_text((workspace.root / member.path).read_text(), member.path)
    flags = engine.all_candidates()
    assert flags
    assert flags[0].value == "flag{1n_4rch1v3_pr0v3n4nc3}"
    assert flags[0].source == member.path
    assert member.path.startswith("extracted/")
