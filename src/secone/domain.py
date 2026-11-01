from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class FlagStatus:
    FOUND = "found"
    VERIFIED = "verified"
    CANDIDATE = "candidate"
    NONE = "none"


class Severity:
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    ORDER = {INFO: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4}


class TaskStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FlagCandidate:
    value: str
    status: str = FlagStatus.CANDIDATE
    confidence: float = 0.5
    source: str = ""
    offset: int | None = None
    method: str = ""
    evidence: str = ""
    ai_generated: bool = False
    verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlagCandidate":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class Finding:
    title: str
    category: str
    severity: str = Severity.INFO
    description: str = ""
    evidence: str = ""
    path: str = ""
    line: int | None = None
    rule_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    @property
    def short_evidence(self) -> str:
        text = " ".join(self.evidence.split())
        return text[:180] + ("..." if len(text) > 180 else "")


@dataclass
class FileArtifact:
    path: str
    size: int
    sha256: str
    kind: str
    category: str = "misc"
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileArtifact":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class AnalysisResult:
    task_id: str
    title: str
    mode: str
    status: str = TaskStatus.COMPLETED
    created_at: str = field(default_factory=now_iso)
    completed_at: str = ""
    duration_seconds: float = 0.0
    summary: str = ""
    ai_text: str = ""
    ai_used: bool = False
    ai_error: str = ""
    engine: str = ""
    flags: list[FlagCandidate] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    files: list[FileArtifact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    workspace: str = ""
    report_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisResult":
        return cls(
            task_id=data.get("task_id", ""),
            title=data.get("title", ""),
            mode=data.get("mode", "auto"),
            status=data.get("status", TaskStatus.COMPLETED),
            created_at=data.get("created_at", now_iso()),
            completed_at=data.get("completed_at", ""),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            summary=data.get("summary", ""),
            ai_text=data.get("ai_text", ""),
            ai_used=bool(data.get("ai_used", False)),
            ai_error=data.get("ai_error", ""),
            engine=data.get("engine", ""),
            flags=[FlagCandidate.from_dict(item) for item in data.get("flags", [])],
            findings=[Finding.from_dict(item) for item in data.get("findings", [])],
            files=[FileArtifact.from_dict(item) for item in data.get("files", [])],
            warnings=list(data.get("warnings", [])),
            workspace=data.get("workspace", ""),
            report_paths=dict(data.get("report_paths", {})),
        )

    @property
    def confirmed_flags(self) -> list[FlagCandidate]:
        return [
            flag
            for flag in self.flags
            if flag.status in (FlagStatus.FOUND, FlagStatus.VERIFIED)
        ]

    @property
    def candidates(self) -> list[FlagCandidate]:
        return [flag for flag in self.flags if flag.status == FlagStatus.CANDIDATE]

    @property
    def highest_flag_status(self) -> str:
        if any(flag.status == FlagStatus.VERIFIED for flag in self.flags):
            return FlagStatus.VERIFIED
        if any(flag.status == FlagStatus.FOUND for flag in self.flags):
            return FlagStatus.FOUND
        if self.candidates:
            return FlagStatus.CANDIDATE
        return FlagStatus.NONE


@dataclass
class TaskRecord:
    id: str
    title: str
    mode: str
    status: str
    created_at: str
    completed_at: str = ""
    workspace: str = ""
    input_count: int = 0
    flag_count: int = 0
    summary: str = ""
    error: str = ""
    result_json: str = ""
