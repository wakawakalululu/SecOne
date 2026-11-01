"""Static deployment-dependency audit for the Nuitka bundle.

This does not replace a clean-machine acceptance test. It verifies the
invariants that a clean Windows install depends on: bundled interpreter,
Qt platform plugin, VC++ runtime, release config, licenses, pristine
first-run directories, and absence of developer paths.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = ROOT / "dist" / "SecOne"

REQUIRED_FILES = (
    ("main executable", "SecOne.exe"),
    ("embedded interpreter", "python312.dll"),
    ("interpreter shim", "python3.dll"),
    ("Qt platform plugin", "PySide6/qt-plugins/platforms/qwindows.dll"),
    ("Qt core", "qt6core.dll"),
    ("Qt gui", "qt6gui.dll"),
    ("Qt widgets", "qt6widgets.dll"),
    ("app config", "config/app.yaml"),
    ("prompt config", "config/prompts.yaml"),
    ("XuanmuSec license", "licenses/LICENSE-XuanmuSec.txt"),
    ("LFM 1.0 license", "licenses/LICENSE-LFM1.0.txt"),
    ("Apache-2.0 license", "licenses/Apache-2.0.txt"),
    ("llama.cpp license", "licenses/LICENSE-llama.cpp.txt"),
)

# Required because the bundle must not depend on a system-wide
# VC++ Redistributable. ucrtbase.dll is intentionally not listed: it ships
# with Windows 10/11.
VC_RUNTIME_DLLS = (
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)

FIRST_RUN_DIRS = ("data", "logs", "output", "workspace")
DEV_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._$-]+")
UNIX_HOME_RE = re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/")
TEXT_SUFFIXES = {".yaml", ".yml", ".json", ".md", ".txt", ".ini", ".cfg", ".log", ".iss"}
BINARY_SCAN = ("SecOne.exe", "python312.dll", "pyside6.abi3.dll")


@dataclass
class Result:
    status: str
    name: str
    detail: str


def _ok(name: str, detail: str) -> Result:
    return Result("ok", name, detail)


def _warn(name: str, detail: str) -> Result:
    return Result("warn", name, detail)


def _fail(name: str, detail: str) -> Result:
    return Result("fail", name, detail)


def _info(name: str, detail: str) -> Result:
    return Result("info", name, detail)


def _iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def _find_dev_paths_text(root: Path) -> list[str]:
    hits: list[str] = []
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if DEV_PATH_RE.search(text) or UNIX_HOME_RE.search(text):
            hits.append(path.relative_to(root).as_posix())
    return hits


def _find_dev_paths_binary(root: Path) -> list[str]:
    hits: list[str] = []
    for name in BINARY_SCAN:
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if re.search(rb"[A-Za-z]:\\Users\\[A-Za-z0-9._$-]+", data):
            hits.append(name)
    return hits


def audit_bundle(root: Path, expect_runtime: bool = False) -> list[Result]:
    results: list[Result] = []

    if not root.is_dir():
        return [_fail("bundle root", f"{root} is not a directory")]

    files = [p for p in root.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    results.append(_info("bundle", f"{len(files)} files, {total_bytes} bytes"))

    for label, rel in REQUIRED_FILES:
        path = root / rel
        if not path.is_file():
            results.append(_fail(label, f"missing: {rel}"))
        elif path.stat().st_size == 0:
            results.append(_fail(label, f"empty: {rel}"))
        else:
            results.append(_ok(label, f"{rel} ({path.stat().st_size} bytes)"))

    for dll in VC_RUNTIME_DLLS:
        path = root / dll
        if path.is_file():
            results.append(_ok("vc++ runtime", f"{dll} ({path.stat().st_size} bytes)"))
        else:
            results.append(_fail("vc++ runtime", f"missing: {dll}"))

    dirty = []
    for name in FIRST_RUN_DIRS:
        directory = root / name
        if not directory.is_dir():
            results.append(_warn("first-run dir", f"missing directory: {name}/"))
            continue
        leaked = [p for p in directory.rglob("*") if p.is_file()]
        if leaked:
            dirty.append(f"{name}/ ({len(leaked)} files)")
    if dirty:
        results.append(_warn("first-run state", "not pristine: " + ", ".join(dirty)))
    else:
        results.append(_ok("first-run state", "data/, logs/, output/, workspace/ are empty"))

    ggufs = [p.name for p in (root / "models").glob("*.gguf")]
    if ggufs:
        results.append(_warn("model weights", "bundled in program dir: " + ", ".join(ggufs)))
    else:
        results.append(_ok("model weights", "no .gguf in models/ (weights ship separately)"))

    server = root / "runtime" / "llama-server.exe"
    if server.is_file():
        results.append(_ok("llama runtime", f"runtime/llama-server.exe ({server.stat().st_size} bytes)"))
    elif expect_runtime:
        results.append(_fail("llama runtime", "runtime/llama-server.exe missing but required"))
    else:
        results.append(_info("llama runtime", "not bundled; supplied by the model package"))

    text_hits = _find_dev_paths_text(root)
    binary_hits = _find_dev_paths_binary(root)
    if text_hits or binary_hits:
        detail = "dev paths in text: " + (", ".join(text_hits) if text_hits else "none")
        detail += "; binaries: " + (", ".join(binary_hits) if binary_hits else "none")
        results.append(_fail("path leakage", detail))
    else:
        results.append(_ok("path leakage", "no user-profile paths in text files or key binaries"))

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit the SecOne deployment bundle")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument(
        "--expect-runtime",
        action="store_true",
        help="require runtime/llama-server.exe (model package layout)",
    )
    args = parser.parse_args(argv)

    results = audit_bundle(args.bundle, expect_runtime=args.expect_runtime)
    for item in results:
        print(f"{item.status.upper():4} - {item.name}: {item.detail}")

    failures = sum(1 for item in results if item.status == "fail")
    warnings = sum(1 for item in results if item.status == "warn")
    print(f"\nsummary: {len(results)} checks, {failures} failed, {warnings} warnings")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
