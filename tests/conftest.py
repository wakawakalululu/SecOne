from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from secone.config import AppConfig  # noqa: E402
from secone.paths import AppPaths  # noqa: E402


@pytest.fixture
def app_paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths(tmp_path / "app")
    paths.ensure()
    return paths


@pytest.fixture
def config(app_paths: AppPaths) -> AppConfig:
    cfg = AppConfig(app_paths)
    cfg.set("analysis.ai_enabled", False)
    return cfg
