from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ...config import AppConfig
from ...domain import FileArtifact, Finding, Severity
from ..fileio import extract_text, printable_strings, read_bytes
from ..flag_engine import FlagEngine
from ..ingest import IngestResult
from ..workspace import TaskWorkspace

Progress = Callable[[int, str], None]

ARCHIVE_KINDS = {"zip", "7z", "rar", "gzip", "tar", "bzip2", "xz"}
BINARY_KINDS = {"elf", "pe", "binary", "wasm", "java_class"}
IMAGE_KINDS = {"png", "jpeg", "gif", "bmp", "webp", "tiff"}


@dataclass
class AnalysisContext:
    config: AppConfig
    workspace: TaskWorkspace
    ingest: IngestResult
    flag_engine: FlagEngine
    progress: Progress | None = None
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    _text_cache: dict[str, str] = field(default_factory=dict)
    _bytes_cache: dict[str, bytes] = field(default_factory=dict)
    _max_text_chars: int = 60000
    _max_finding_count: int = 400

    def __post_init__(self) -> None:
        self._max_text_chars = int(
            self.config.get("analysis.max_text_chars", 60000)
        )

    def path_of(self, artifact: FileArtifact) -> Path:
        return self.workspace.root / artifact.path

    def text_for(self, artifact: FileArtifact, limit: int | None = None) -> str:
        cap = limit or self._max_text_chars
        key = f"{artifact.path}:{cap}"
        if key not in self._text_cache:
            try:
                self._text_cache[key] = extract_text(
                    self.path_of(artifact), artifact.kind, max_chars=cap
                )
            except (OSError, PermissionError):
                self._text_cache[key] = ""
        return self._text_cache[key]

    def bytes_for(self, artifact: FileArtifact, limit: int = 16 * 1024 * 1024) -> bytes:
        key = f"{artifact.path}:{limit}"
        if key not in self._bytes_cache:
            try:
                self._bytes_cache[key] = read_bytes(self.path_of(artifact), limit)
            except (OSError, PermissionError):
                self._bytes_cache[key] = b""
        return self._bytes_cache[key]

    def strings_for(self, artifact: FileArtifact, limit: int = 600) -> list[tuple[int, str]]:
        data = self.bytes_for(artifact)
        return printable_strings(
            data,
            min_length=int(self.config.get("analysis.binary_string_min", 5)),
            limit=limit,
        )

    def add_finding(
        self,
        title: str,
        category: str,
        severity: str = Severity.INFO,
        description: str = "",
        evidence: str = "",
        artifact: FileArtifact | None = None,
        line: int | None = None,
        rule_id: str = "",
    ) -> Finding | None:
        if len(self.findings) >= self._max_finding_count:
            return None
        finding = Finding(
            title=title,
            category=category,
            severity=severity,
            description=description,
            evidence=evidence,
            path=artifact.path if artifact else "",
            line=line,
            rule_id=rule_id,
        )
        self.findings.append(finding)
        return finding

    def add_warning(self, message: str) -> None:
        if message and message not in self.warnings:
            self.warnings.append(message)

    def report_progress(self, percent: int, message: str) -> None:
        if self.progress:
            self.progress(max(0, min(percent, 100)), message)

    def scan_text(self, text: str, artifact: FileArtifact, method: str = "直接匹配") -> None:
        self.flag_engine.scan_direct(text, artifact.path, method=method)

    def analyze_text(self, text: str, artifact: FileArtifact) -> None:
        self.flag_engine.analyze_text(text, artifact.path)

    def analyze_bytes(
        self, data: bytes, artifact: FileArtifact, include_text: bool = True
    ) -> None:
        self.flag_engine.analyze_bytes(data, artifact.path, include_text=include_text)

    def files(
        self,
        kinds: Iterable[str] | None = None,
        exclude_kinds: Iterable[str] | None = None,
    ) -> list[FileArtifact]:
        kind_set = set(kinds) if kinds else None
        excluded = set(exclude_kinds) if exclude_kinds else None
        result = []
        for artifact in self.ingest.files:
            if kind_set is not None and artifact.kind not in kind_set:
                continue
            if excluded is not None and artifact.kind in excluded:
                continue
            result.append(artifact)
        return result


class AnalysisPlugin:
    name = "base"
    label = "Base"
    description = ""

    def run(self, context: AnalysisContext, mode: str) -> None:
        raise NotImplementedError
