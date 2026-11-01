from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "package_model", ROOT / "scripts" / "package_model.py"
)
assert SPEC and SPEC.loader
package_model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_model)


def write_gguf(path: Path, *, magic: bytes = b"GGUF", version: int = 3, size: int = 128 * 1024) -> Path:
    data = bytearray(size)
    data[:4] = magic
    struct.pack_into("<IQQ", data, 4, version, 12, 8)
    path.write_bytes(data)
    return path


def make_args(tmp_path: Path, gguf: Path, **overrides) -> argparse.Namespace:
    values = {
        "gguf": gguf,
        "runtime_dir": None,
        "license": [],
        "model_json": ROOT / "models" / "model.json",
        "output": tmp_path / "out",
        "name": "demo-model",
        "no_zip": False,
        "force": False,
        "allow_missing_model_licenses": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_gguf_header_validation(tmp_path: Path) -> None:
    assert package_model.read_gguf_header(write_gguf(tmp_path / "ok.gguf")) == (3, 12, 8)
    with pytest.raises(ValueError, match="魔数"):
        package_model.read_gguf_header(write_gguf(tmp_path / "bad.gguf", magic=b"NOPE"))
    with pytest.raises(ValueError, match="版本"):
        package_model.read_gguf_header(write_gguf(tmp_path / "v9.gguf", version=9))
    with pytest.raises(ValueError, match="偏小"):
        package_model.read_gguf_header(write_gguf(tmp_path / "tiny.gguf", size=1024))


def test_build_package_with_manifest(tmp_path: Path) -> None:
    gguf = write_gguf(tmp_path / "XuanmuSec-test.gguf")
    package_dir = package_model.build(make_args(tmp_path, gguf))

    metadata = json.loads((package_dir / "models" / "model.json").read_text(encoding="utf-8"))
    assert metadata["filename"] == gguf.name
    assert metadata["expected_size_bytes"] == gguf.stat().st_size
    assert metadata["sha256"] == hashlib.sha256(gguf.read_bytes()).hexdigest()

    manifest = (package_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
    lines = [line for line in manifest.splitlines() if line.strip()]
    assert all("SHA256SUMS.txt" not in line for line in lines)
    assert any(line.endswith("  models/XuanmuSec-test.gguf") for line in lines)
    assert any(line.endswith("  INSTALL.txt") for line in lines)

    zip_path = tmp_path / "out" / "demo-model.zip"
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert "demo-model/models/XuanmuSec-test.gguf" in archive.namelist()
        assert "demo-model/SHA256SUMS.txt" in archive.namelist()
    assert zip_path.with_suffix(".zip.sha256").is_file()


def test_requires_model_licenses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing required license must abort the build before any output exists.

    ``REQUIRED_LICENSES`` is patched to a name that is guaranteed absent so the
    check stays meaningful regardless of which license texts happen to be
    checked into ``licenses/``.
    """
    monkeypatch.setattr(
        package_model, "REQUIRED_LICENSES", ("LICENSE-DOES-NOT-EXIST.txt",)
    )
    gguf = write_gguf(tmp_path / "model.gguf")
    args = make_args(tmp_path, gguf, allow_missing_model_licenses=False)
    with pytest.raises(SystemExit, match="缺少模型许可文件"):
        package_model.build(args)
    assert not (tmp_path / "out" / "demo-model").exists()


@pytest.mark.parametrize("license_name", ["LICENSE-XuanmuSec.txt", "LICENSE-LFM1.0.txt"])
def test_package_ships_required_licenses(tmp_path: Path, license_name: str) -> None:
    """Both model licenses must be present upstream and land inside the package."""
    source = ROOT / "licenses" / license_name
    assert source.is_file() and source.stat().st_size > 0, f"缺少许可文本：{source}"

    gguf = write_gguf(tmp_path / "XuanmuSec-test.gguf")
    args = make_args(
        tmp_path, gguf, allow_missing_model_licenses=False, no_zip=True
    )
    package_dir = package_model.build(args)
    packaged = package_dir / "licenses" / license_name
    assert packaged.is_file()
    assert packaged.read_bytes() == source.read_bytes()


def test_lfm_license_is_upstream_verbatim() -> None:
    """Guard against accidentally shipping a paraphrase of the LFM license."""
    text = (ROOT / "licenses" / "LICENSE-LFM1.0.txt").read_text(encoding="utf-8")
    assert text.lstrip().startswith("LFM Open License v1.0")
    assert "Liquid AI, Inc." in text
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in text
    assert "END OF TERMS AND CONDITIONS" in text
    assert len(text) > 8000


def test_xuanmu_notice_points_to_bundled_apache_text() -> None:
    """The notice references Apache-2.0.txt, so that file must exist and ship."""
    notice = (ROOT / "licenses" / "LICENSE-XuanmuSec.txt").read_text(encoding="utf-8")
    assert "Apache-2.0.txt" in notice
    assert "LICENSE-LFM1.0.txt" in notice

    apache = ROOT / "licenses" / "Apache-2.0.txt"
    assert apache.is_file()
    apache_text = apache.read_text(encoding="utf-8")
    assert "Apache License" in apache_text
    assert "Version 2.0" in apache_text
    assert "END OF TERMS AND CONDITIONS" in apache_text


def test_package_ships_apache_text_even_without_runtime(tmp_path: Path) -> None:
    gguf = write_gguf(tmp_path / "XuanmuSec-test.gguf")
    package_dir = package_model.build(make_args(tmp_path, gguf, no_zip=True))
    assert (package_dir / "licenses" / "Apache-2.0.txt").is_file()


def test_runtime_bundle_includes_llama_cpp_license(tmp_path: Path) -> None:
    """Shipping llama.cpp binaries without its MIT text would be a licence breach."""
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "llama-server.exe").write_bytes(b"MZ-fake")
    (runtime_dir / "llama.dll").write_bytes(b"MZ-fake-dll")

    gguf = write_gguf(tmp_path / "XuanmuSec-test.gguf")
    args = make_args(tmp_path, gguf, runtime_dir=runtime_dir, no_zip=True)
    package_dir = package_model.build(args)

    shipped = {p.name for p in (package_dir / "licenses").iterdir()}
    assert {"LICENSE-llama.cpp.txt", "Apache-2.0.txt"} <= shipped
    assert (package_dir / "runtime" / "llama-server.exe").is_file()
    assert (package_dir / "runtime" / "llama.dll").is_file()


def test_runtime_license_missing_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        package_model, "RUNTIME_LICENSES", ("LICENSE-ABSENT-RUNTIME.txt",)
    )
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "llama-server.exe").write_bytes(b"MZ-fake")
    gguf = write_gguf(tmp_path / "XuanmuSec-test.gguf")
    args = make_args(tmp_path, gguf, runtime_dir=runtime_dir, no_zip=True)
    with pytest.raises(SystemExit, match="随包分发"):
        package_model.build(args)


def test_default_package_name_falls_back_to_gguf_stem(tmp_path: Path) -> None:
    """A non-Latin display_name must not collapse the default package name into dashes."""
    model_json = tmp_path / "model.json"
    model_json.write_text(
        json.dumps({"display_name": "本地推理引擎", "quantization": "Q6_K"}),
        encoding="utf-8",
    )
    gguf = write_gguf(tmp_path / "XuanmuSec-v2-Q6_K.gguf")
    args = make_args(tmp_path, gguf, name="", model_json=model_json, no_zip=True)
    package_dir = package_model.build(args)
    assert package_dir.name == "SecOne-model-XuanmuSec-v2-Q6_K"
