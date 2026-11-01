from __future__ import annotations

import bz2
import gzip
import lzma
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from ..config import AppConfig
from ..domain import FileArtifact
from .classify import guess_category
from .fileio import (
    decode_bytes,
    detect_kind,
    read_bytes,
    sha256_file,
)
from .workspace import (
    TaskWorkspace,
    copy_file,
    copy_material,
    safe_name,
    unique_destination,
)

Progress = Callable[[int, str], None]


@dataclass
class IngestResult:
    title: str
    files: list[FileArtifact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_bytes: int = 0
    input_count: int = 0
    duplicate_count: int = 0
    archives_extracted: int = 0

    @property
    def category(self) -> str:
        from .classify import aggregate_category

        return aggregate_category([item.category for item in self.files])


class _ExtractionBudget:
    def __init__(self, max_entries: int, max_total_bytes: int):
        self.max_entries = max_entries
        self.max_total_bytes = max_total_bytes
        self.entries = 0
        self.bytes = 0

    def can_accept(self, size: int) -> bool:
        return (
            self.entries < self.max_entries
            and self.bytes + max(size, 0) <= self.max_total_bytes
        )

    def consume(self, size: int) -> None:
        self.entries += 1
        self.bytes += max(size, 0)

    @property
    def remaining(self) -> int:
        return max(self.max_total_bytes - self.bytes, 0)


class IngestEngine:
    def __init__(self, config: AppConfig, workspace: TaskWorkspace):
        self.config = config
        self.workspace = workspace
        self.max_file_bytes = int(config.get("analysis.max_file_mb", 64)) * 1024 * 1024
        self.max_total_bytes = int(config.get("analysis.max_total_mb", 256)) * 1024 * 1024
        self.max_files = int(config.get("analysis.max_files", 500))
        self.archive_depth = int(config.get("analysis.archive_depth", 3))
        self.archive_max_entries = int(config.get("analysis.archive_max_entries", 400))
        self.archive_max_total = (
            int(config.get("analysis.archive_max_total_mb", 512)) * 1024 * 1024
        )
        self.warnings: list[str] = []
        self.budget = _ExtractionBudget(
            max_entries=self.archive_max_entries,
            max_total_bytes=self.archive_max_total,
        )
        self._archive_queue: list[tuple[Path, int]] = []
        self._queued: set[Path] = set()

    def ingest(
        self,
        sources: list[Path],
        text: str = "",
        title_hint: str = "",
        progress: Progress | None = None,
    ) -> IngestResult:
        self.warnings = []
        input_count = 0
        for source in sources:
            count, _size, warnings = copy_material(
                source,
                self.workspace.input,
                self.max_file_bytes,
                self.max_total_bytes,
                self.max_files,
                copy_file,
            )
            input_count += count
            self.warnings.extend(warnings)

        if text.strip():
            text_name = datetime.now().strftime("pasted_%Y%m%d_%H%M%S.txt")
            target = unique_destination(self.workspace.input, text_name)
            target.write_text(text, encoding="utf-8")
            input_count += 1
            if input_count > self.max_files:
                self.warnings.append("粘贴文本超过任务文件数量限制。")

        if progress:
            progress(8, "整理材料并识别文件类型")

        self._discover_archives(self.workspace.input)
        extracted = 0
        while self._archive_queue:
            archive_path, depth = self._archive_queue.pop(0)
            if depth > self.archive_depth:
                self.warnings.append(
                    f"压缩包嵌套超过 {self.archive_depth} 层，已跳过：{archive_path.name}"
                )
                continue
            if self._extract_archive(archive_path, depth):
                extracted += 1
                self._discover_archives(
                    self._archive_target(archive_path, depth), depth + 1
                )

        if progress:
            progress(18, "计算文件指纹并建立索引")

        files: list[FileArtifact] = []
        seen_hashes: dict[str, str] = {}
        duplicates = 0
        total_bytes = 0
        candidates = sorted(
            [*self.workspace.input.rglob("*"), *self.workspace.extracted.rglob("*")]
        )
        for path in candidates:
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
                if size > self.max_file_bytes:
                    self.warnings.append(
                        f"超过单文件分析限制，未纳入：{path.name}（{size} 字节）"
                    )
                    continue
                digest = sha256_file(path)
                if digest in seen_hashes:
                    duplicates += 1
                    continue
                seen_hashes[digest] = path.as_posix()
                sample = read_bytes(path, 512 * 1024)
                kind = detect_kind(sample, path)
                sample_text = ""
                if kind not in {
                    "binary",
                    "elf",
                    "pe",
                    "png",
                    "jpeg",
                    "gif",
                    "bmp",
                    "webp",
                    "tiff",
                    "pdf",
                    "zip",
                    "7z",
                    "rar",
                    "gzip",
                    "tar",
                    "bzip2",
                    "xz",
                }:
                    sample_text = decode_bytes(sample[:24000])
                category = guess_category(path, kind, sample_text)
                files.append(
                    FileArtifact(
                        path=path.relative_to(self.workspace.root).as_posix(),
                        size=size,
                        sha256=digest,
                        kind=kind,
                        category=category,
                        source="input"
                        if self._is_relative_to(path, self.workspace.input)
                        else "archive",
                    )
                )
                total_bytes += size
                if len(files) > self.max_files:
                    self.warnings.append("分析文件数量超过上限，后续文件已忽略。")
                    break
            except (OSError, PermissionError) as exc:
                self.warnings.append(f"读取失败，已跳过：{path.name}（{exc}）")

        if duplicates:
            self.warnings.append(f"检测到 {duplicates} 个重复文件，已自动去重。")

        title = title_hint.strip() or self._make_title(sources, text)
        result = IngestResult(
            title=title,
            files=files,
            warnings=self.warnings.copy(),
            total_bytes=total_bytes,
            input_count=max(input_count, len(files)),
            duplicate_count=duplicates,
            archives_extracted=extracted,
        )
        self.workspace.write_json(
            "inventory.json",
            {
                "title": title,
                "category": result.category,
                "files": [item.to_dict() for item in files],
                "warnings": result.warnings,
            },
        )
        if progress:
            progress(24, f"已索引 {len(files)} 个唯一文件")
        return result

    def _discover_archives(self, root: Path, depth: int = 0) -> None:
        if not root.exists():
            return
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                kind = self._archive_kind(path)
            except OSError:
                continue
            if kind in {"zip", "7z", "rar", "gzip", "tar", "bzip2", "xz"}:
                if path not in self._queued:
                    self._queued.add(path)
                    self._archive_queue.append((path, depth))

    def _extract_archive(self, path: Path, depth: int) -> bool:
        if self.budget.entries >= self.budget.max_entries:
            self.warnings.append("压缩包条目总数超过限制，停止继续解压。")
            return False
        kind = self._archive_kind(path)
        target = self._archive_target(path, depth)
        target.mkdir(parents=True, exist_ok=True)
        before_entries = self.budget.entries
        before_bytes = self.budget.bytes
        try:
            if kind == "zip":
                self._extract_zip(path, target)
            elif kind in {"tar", "gzip", "bzip2", "xz"} and self._is_tar(path):
                self._extract_tar(path, target)
            elif kind == "gzip":
                self._extract_stream_compressed(path, target, "gzip")
            elif kind == "bzip2":
                self._extract_stream_compressed(path, target, "bz2")
            elif kind == "xz":
                self._extract_stream_compressed(path, target, "xz")
            elif kind == "7z":
                self._extract_7z(path, target)
            elif kind == "rar":
                self.warnings.append(
                    f"RAR 解压需要外部分析组件，当前仅保留原文件：{path.name}"
                )
                return False
            else:
                return False
        except Exception as exc:
            self.warnings.append(f"解压失败：{path.name}（{exc}）")
            return False

        added = self.budget.entries - before_entries
        if added:
            self.warnings.append(
                f"已解压 {path.name}：{added} 个条目，"
                f"{self.budget.bytes - before_bytes} 字节。"
            )
        if not any(target.iterdir()):
            shutil.rmtree(target, ignore_errors=True)
            return False
        return True

    def _archive_target(self, archive_path: Path, depth: int) -> Path:
        try:
            relative = archive_path.relative_to(self.workspace.root)
        except ValueError:
            relative = Path(safe_name(archive_path.name))
        stem = safe_name("__".join(relative.with_suffix("").parts))
        digest = sha256_file(archive_path)[:8]
        return self.workspace.extracted / f"{stem}_{digest}"

    def _extract_zip(self, path: Path, target: Path) -> None:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if self.budget.entries >= self.budget.max_entries:
                    self.warnings.append(f"压缩包达到条目上限：{path.name}")
                    break
                if info.flag_bits & 0x1:
                    self.warnings.append(f"检测到加密 ZIP 条目，已跳过：{info.filename}")
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    self.warnings.append(f"检测到符号链接，已跳过：{info.filename}")
                    continue
                relative = self._safe_member_path(info.filename)
                if relative is None:
                    self.warnings.append(f"拒绝可疑压缩路径：{info.filename}")
                    continue
                if not self.budget.can_accept(info.file_size):
                    self.warnings.append("压缩包展开超过安全限制，已停止。")
                    break
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(info) as source, destination.open("wb") as handle:
                    while True:
                        chunk = source.read(256 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if self.budget.bytes + written > self.budget.max_total_bytes:
                            raise RuntimeError("压缩包展开大小超过安全限制")
                        handle.write(chunk)
                self.budget.consume(written)

    def _extract_tar(self, path: Path, target: Path) -> None:
        with tarfile.open(path, mode="r:*") as archive:
            for info in archive:
                if self.budget.entries >= self.budget.max_entries:
                    self.warnings.append(f"压缩包达到条目上限：{path.name}")
                    break
                if info.isdir():
                    continue
                if info.issym() or info.islnk() or info.ischr() or info.isblk() or info.isfifo():
                    self.warnings.append(f"跳过特殊归档条目：{info.name}")
                    continue
                if not info.isfile():
                    continue
                relative = self._safe_member_path(info.name)
                if relative is None:
                    self.warnings.append(f"拒绝可疑归档路径：{info.name}")
                    continue
                if not self.budget.can_accept(info.size):
                    self.warnings.append("归档展开超过安全限制，已停止。")
                    break
                source = archive.extractfile(info)
                if source is None:
                    continue
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with source, destination.open("wb") as handle:
                    while True:
                        chunk = source.read(256 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if self.budget.bytes + written > self.budget.max_total_bytes:
                            raise RuntimeError("归档展开大小超过安全限制")
                        handle.write(chunk)
                self.budget.consume(written)

    def _extract_7z(self, path: Path, target: Path) -> None:
        try:
            import py7zr
        except ImportError:
            self.warnings.append("未安装 py7zr，无法解压 7z 文件。")
            return
        with py7zr.SevenZipFile(path, mode="r") as archive:
            if archive.needs_password():
                self.warnings.append(f"检测到加密 7z，已跳过：{path.name}")
                return
            infos = archive.list()
            total = 0
            for info in infos:
                if info.is_directory:
                    continue
                if self._safe_member_path(info.filename) is None:
                    self.warnings.append(f"拒绝可疑 7z 路径：{info.filename}")
                    return
                total += int(getattr(info, "uncompressed", 0) or 0)
            if not self.budget.can_accept(total):
                self.warnings.append("7z 展开超过安全限制，已跳过。")
                return
            archive.extractall(path=target)
            for item in target.rglob("*"):
                if item.is_file():
                    self.budget.consume(item.stat().st_size)

    def _extract_stream_compressed(self, path: Path, target: Path, kind: str) -> None:
        if not self.budget.can_accept(0):
            self.warnings.append("压缩包展开超过安全限制，已停止。")
            return
        name = path.name
        for suffix in (".gz", ".bz2", ".xz"):
            if name.lower().endswith(suffix):
                name = name[: -len(suffix)]
                break
        destination = target / safe_name(name or "decompressed.bin")
        opener = {"gzip": gzip.open, "bz2": bz2.open, "xz": lzma.open}[kind]
        written = 0
        with opener(path, "rb") as source, destination.open("wb") as handle:
            while True:
                chunk = source.read(256 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if self.budget.bytes + written > self.budget.max_total_bytes:
                    raise RuntimeError("解压数据超过安全限制")
                handle.write(chunk)
        self.budget.consume(written)

    @staticmethod
    def _safe_member_path(name: str) -> Path | None:
        normalized = name.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or pure.anchor:
            return None
        if any(part in ("..", "") for part in pure.parts):
            return None
        if re.match(r"^[A-Za-z]:", normalized):
            return None
        parts = [safe_name(part) for part in pure.parts if part not in (".", "")]
        if not parts:
            return None
        return Path(*parts)

    @staticmethod
    def _archive_kind(path: Path) -> str:
        lower = path.name.lower()
        if any(
            lower.endswith(suffix)
            for suffix in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
        ):
            return "tar"
        kind = detect_kind(read_bytes(path, 32), path)
        if kind in {"zip", "7z", "rar", "gzip", "bzip2", "xz"}:
            return kind
        suffix = path.suffix.lower()
        if suffix in {".zip", ".jar", ".apk"}:
            return "zip"
        if suffix == ".7z":
            return "7z"
        if suffix == ".rar":
            return "rar"
        if suffix == ".gz":
            return "gzip"
        if suffix == ".bz2":
            return "bzip2"
        if suffix == ".xz":
            return "xz"
        return kind

    @staticmethod
    def _is_tar(path: Path) -> bool:
        lower = path.name.lower()
        return any(
            lower.endswith(suffix)
            for suffix in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
        )

    @staticmethod
    def _is_relative_to(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def _make_title(sources: list[Path], text: str) -> str:
        if sources:
            if len(sources) == 1:
                return sources[0].name
            return f"{sources[0].name} 等 {len(sources)} 个材料"
        for line in text.splitlines():
            line = line.strip()
            if line:
                return line[:42]
        return "未命名分析任务"
