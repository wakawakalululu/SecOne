from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())


def app_root() -> Path:
    override = os.environ.get("SECONE_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if _is_frozen():
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def runtime(self) -> Path:
        return self.root / "runtime"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def db_file(self) -> Path:
        return self.data / "history.db"

    def ensure(self) -> None:
        for directory in (
            self.config,
            self.models,
            self.runtime,
            self.data,
            self.workspace,
            self.output,
            self.logs,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def resolve(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()


def setup_logging(paths: AppPaths) -> Path:
    paths.logs.mkdir(parents=True, exist_ok=True)
    log_file = paths.logs / "secone.log"
    root = logging.getLogger()
    if not any(getattr(handler, "_secone_handler", False) for handler in root.handlers):
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler._secone_handler = True  # type: ignore[attr-defined]
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    return log_file
