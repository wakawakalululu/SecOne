from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "audit_bundle", ROOT / "scripts" / "audit_bundle.py"
)
assert SPEC and SPEC.loader
audit_bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_bundle
SPEC.loader.exec_module(audit_bundle)


def make_bundle(root: Path) -> Path:
    for _, rel in audit_bundle.REQUIRED_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    for dll in audit_bundle.VC_RUNTIME_DLLS:
        (root / dll).write_bytes(b"x")
    for name in audit_bundle.FIRST_RUN_DIRS:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "models").mkdir(exist_ok=True)
    (root / "runtime").mkdir(exist_ok=True)
    return root


def statuses(results, name: str) -> list[str]:
    return [item.status for item in results if item.name == name]


def test_complete_bundle_has_no_failures(tmp_path: Path) -> None:
    results = audit_bundle.audit_bundle(make_bundle(tmp_path / "bundle"))
    assert [item for item in results if item.status == "fail"] == []
    assert statuses(results, "path leakage") == ["ok"]
    assert statuses(results, "first-run state") == ["ok"]
    assert statuses(results, "llama runtime") == ["info"]


def test_missing_interpreter_is_a_failure(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "bundle")
    (bundle / "python312.dll").unlink()
    results = audit_bundle.audit_bundle(bundle)
    assert statuses(results, "embedded interpreter") == ["fail"]


def test_missing_vc_runtime_is_a_failure(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "bundle")
    (bundle / "msvcp140.dll").unlink()
    results = audit_bundle.audit_bundle(bundle)
    assert "fail" in statuses(results, "vc++ runtime")


def test_developer_path_in_config_is_a_failure(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "bundle")
    (bundle / "config" / "app.yaml").write_text(
        "model:\n  path: 'D:\\Users\\dev\\Desktop\\code\\SecOne\\models\\x.gguf'\n",
        encoding="utf-8",
    )
    results = audit_bundle.audit_bundle(bundle)
    assert statuses(results, "path leakage") == ["fail"]


def test_developer_path_inside_executable_is_a_failure(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "bundle")
    (bundle / "SecOne.exe").write_bytes(b"MZ\x00C:\\Users\\builder\\src\\secone")
    results = audit_bundle.audit_bundle(bundle)
    assert statuses(results, "path leakage") == ["fail"]


def test_dirty_first_run_directory_warns(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "bundle")
    (bundle / "data" / "history.db").write_bytes(b"sqlite")
    results = audit_bundle.audit_bundle(bundle)
    assert statuses(results, "first-run state") == ["warn"]


def test_bundled_model_weights_warn(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "bundle")
    (bundle / "models" / "weight.gguf").write_bytes(b"GGUF")
    results = audit_bundle.audit_bundle(bundle)
    assert statuses(results, "model weights") == ["warn"]


def test_runtime_is_required_when_expected(tmp_path: Path) -> None:
    bundle = make_bundle(tmp_path / "bundle")
    missing = audit_bundle.audit_bundle(bundle, expect_runtime=True)
    assert statuses(missing, "llama runtime") == ["fail"]

    (bundle / "runtime" / "llama-server.exe").write_bytes(b"MZ")
    present = audit_bundle.audit_bundle(bundle, expect_runtime=True)
    assert statuses(present, "llama runtime") == ["ok"]


def test_missing_bundle_root_fails(tmp_path: Path) -> None:
    results = audit_bundle.audit_bundle(tmp_path / "absent")
    assert statuses(results, "bundle root") == ["fail"]
