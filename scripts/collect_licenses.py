from __future__ import annotations

import importlib.metadata as metadata
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "licenses" / "python-packages"

PACKAGES = [
    "PySide6",
    "PySide6_Essentials",
    "PySide6_Addons",
    "shiboken6",
    "PyYAML",
    "pypdf",
    "Pillow",
    "py7zr",
    "pybcj",
    "pyppmd",
    "pycryptodomex",
    "inflate64",
    "multivolumefile",
    "brotli",
    "backports.zstd",
    "texttable",
    "psutil",
]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in PACKAGES:
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            print(f"skip (not installed): {name}")
            continue
        target = OUTPUT / f"{name}-{distribution.version}"
        target.mkdir(parents=True, exist_ok=True)
        copied = 0
        for entry in distribution.files or []:
            filename = entry.name.upper()
            if not any(token in filename for token in ("LICENSE", "COPYING", "NOTICE")):
                continue
            source = Path(distribution.locate_file(entry))
            if not source.is_file():
                continue
            destination = target / entry.name.replace("/", "_").replace("\\", "_")
            shutil.copy2(source, destination)
            copied += 1
        print(f"{name} {distribution.version}: {copied} license files")


if __name__ == "__main__":
    main()
