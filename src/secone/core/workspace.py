from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_name(name: str, fallback: str = "file") -> str:
    cleaned = _UNSAFE_NAME.sub("_", name).strip().rstrip(".")
    if not cleaned:
        cleaned = fallback
    stem = cleaned.split(".", 1)[0].upper()
    if stem in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:180]


def unique_destination(directory: Path, name: str) -> Path:
    candidate = directory / safe_name(name)
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(2, 10000):
        alternative = directory / f"{stem}_{index}{suffix}"
        if not alternative.exists():
            return alternative
    return directory / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


def new_task_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]


@dataclass(frozen=True)
class TaskWorkspace:
    root: Path

    @property
    def input(self) -> Path:
        return self.root / "input"

    @property
    def extracted(self) -> Path:
        return self.root / "extracted"

    @property
    def analysis(self) -> Path:
        return self.root / "analysis"

    @property
    def evidence(self) -> Path:
        return self.root / "evidence"

    @property
    def flags(self) -> Path:
        return self.root / "flags"

    @property
    def report(self) -> Path:
        return self.root / "report"

    @property
    def task_id(self) -> str:
        return self.root.name

    def ensure(self) -> None:
        for directory in (
            self.input,
            self.extracted,
            self.analysis,
            self.evidence,
            self.flags,
            self.report,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: dict) -> Path:
        target = self.analysis / name
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    @classmethod
    def create(cls, workspace_root: Path) -> "TaskWorkspace":
        root = workspace_root / new_task_id()
        workspace = cls(root)
        workspace.ensure()
        return workspace

    @classmethod
    def open(cls, root: Path) -> "TaskWorkspace":
        return cls(root)


def copy_material(
    source: Path,
    destination_root: Path,
    max_file_bytes: int,
    max_total_bytes: int,
    max_files: int,
    copy_file,
) -> tuple[int, int, list[str]]:
    """Copy files/folders into a task input directory with hard limits."""
    warnings: list[str] = []
    copied = 0
    total = 0

    def reserve(size: int) -> bool:
        nonlocal copied, total
        if copied >= max_files:
            return False
        if total + size > max_total_bytes:
            return False
        copied += 1
        total += size
        return True

    source = source.resolve()
    if source.is_symlink() or not source.exists():
        warnings.append(f"已跳过无效或符号链接路径：{source}")
        return copied, total, warnings

    if source.is_file():
        if source.stat().st_size > max_file_bytes:
            warnings.append(f"文件超过单文件限制，已跳过：{source.name}")
            return copied, total, warnings
        if not reserve(source.stat().st_size):
            warnings.append(f"超过任务文件数量或总大小限制，已跳过：{source.name}")
            return copied, total, warnings
        target = unique_destination(destination_root, source.name)
        copy_file(source, target)
        return copied, total, warnings

    if source.is_dir():
        root_target = unique_destination(destination_root, source.name)
        for item in source.rglob("*"):
            if item.is_symlink():
                warnings.append(f"已跳过符号链接：{item}")
                continue
            if not item.is_file():
                continue
            size = item.stat().st_size
            if size > max_file_bytes:
                warnings.append(f"文件超过单文件限制，已跳过：{item.name}")
                continue
            if not reserve(size):
                warnings.append(f"超过任务文件数量或总大小限制，已跳过：{item.name}")
                continue
            relative = item.relative_to(source)
            target = root_target.joinpath(*[safe_name(part) for part in relative.parts])
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_file(item, target)
        return copied, total, warnings

    warnings.append(f"不支持的输入路径：{source}")
    return copied, total, warnings


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
