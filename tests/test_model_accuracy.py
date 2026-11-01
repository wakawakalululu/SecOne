from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_harness():
    spec = importlib.util.spec_from_file_location(
        "verify_model_accuracy", ROOT / "scripts" / "verify_model_accuracy.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = load_harness()


def test_extract_flags_keeps_strict_matches_only():
    text = "answer flag{ok_1} then flag{bad{nested}} and flag{ok_1}"
    assert harness.extract_flags(text) == ["flag{ok_1}"]


def test_malformed_flag_is_reported_separately():
    text = "flag{6202_d3srever{galf :rewsna laniF}"
    strict = harness.extract_flags(text)
    assert strict == []
    assert harness.extract_malformed(text, strict) == [
        "flag{6202_d3srever{galf :rewsna laniF}"
    ]


def test_runaway_nested_flag_is_reported_as_malformed():
    text = "flag{" * 40
    assert harness.extract_flags(text) == []
    malformed = harness.extract_malformed(text, [])
    assert len(malformed) == 1
    assert malformed[0].startswith("flag{flag{")
    assert len(malformed[0]) <= harness.MALFORMED_PREVIEW + 1


def test_production_corpus_is_well_formed():
    cases = harness.load_corpus(ROOT / "benchmarks" / "ctf_accuracy_v3.json")
    assert len(cases) == 24
    assert {case["category"] for case in cases} == {
        "plaintext",
        "base64",
        "base32",
        "hex",
        "url",
        "rot13",
        "rot47",
        "reversed",
        "double_base64",
        "base64_then_reversed",
        "source_comment",
        "xor",
        "caesar",
        "atbash",
        "decimal_ascii",
        "octal_ascii",
        "binary_ascii",
        "base58",
        "base64_then_rot13",
        "hex_then_reversed",
        "xor_5a",
        "rot13_then_hex",
        "url_fully_encoded",
        "spaced_hex",
    }
    for case in cases:
        assert harness.FLAG_RE.fullmatch(case["flag"])
        assert case["material"].strip()
        if not case.get("flag_literal_in_material"):
            assert case["flag"] not in case["material"]


def test_load_corpus_rejects_duplicate_ids(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "dup", "category": "x", "material": "m", "flag": "flag{a}"},
                    {"id": "dup", "category": "x", "material": "m", "flag": "flag{b}"},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="重复用例 id"):
        harness.load_corpus(corpus)


def test_load_corpus_rejects_non_flag_answer(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "bad", "category": "x", "material": "m", "flag": "not-a-flag"}
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="标准答案"):
        harness.load_corpus(corpus)


def test_cache_requires_matching_model_prompt_version_and_budget(tmp_path):
    cache = tmp_path / "case.json"
    payload = {
        "model": "m.gguf",
        "prompt_version": harness.PROMPT_VERSION,
        "max_tokens": 512,
        "content": "flag{cached}",
    }
    cache.write_text(json.dumps(payload), encoding="utf-8")
    model = Path("m.gguf")

    assert harness.cached_response(cache, model, 512)["content"] == "flag{cached}"
    assert harness.cached_response(cache, model, 256) is None
    assert harness.cached_response(cache, Path("other.gguf"), 512) is None

    payload["prompt_version"] = harness.PROMPT_VERSION + 1
    cache.write_text(json.dumps(payload), encoding="utf-8")
    assert harness.cached_response(cache, model, 512) is None


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "make_accuracy_corpus", ROOT / "scripts" / "make_accuracy_corpus.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v4_corpus_is_well_formed():
    cases = harness.load_corpus(ROOT / "benchmarks" / "ctf_accuracy_v4.json")
    assert len(cases) == 60
    assert len({case["id"] for case in cases}) == 60
    assert len({case["category"] for case in cases}) == 41
    for case in cases:
        assert case["material"].strip()
        if not case.get("flag_literal_in_material"):
            assert case["flag"] not in case["material"], case["id"]


def test_v4_corpus_matches_generator_output():
    generator = load_generator()
    committed = json.loads(
        (ROOT / "benchmarks" / "ctf_accuracy_v4.json").read_text(encoding="utf-8")
    )
    assert generator.build() == committed
