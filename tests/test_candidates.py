from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from secone.config import AppConfig  # noqa: E402
from secone.db import TaskStore  # noqa: E402
from secone.llm import LLMClient, LlamaServerManager  # noqa: E402
from secone.llm.candidates import ModelCandidate, load_candidates  # noqa: E402
from secone.ui.context import AppContext  # noqa: E402
from secone.ui.pages.settings import SettingsPage  # noqa: E402

REPO_CANDIDATES = Path(__file__).resolve().parents[1] / "models" / "candidates.json"


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def build_context(config: AppConfig) -> AppContext:
    store = TaskStore(config.paths.db_file)
    manager = LlamaServerManager(config)
    client = LLMClient(config, manager)
    return AppContext(config, config.paths, store, manager, client)


def test_repo_catalog_is_valid() -> None:
    """仓库自带清单必须可解析、条目完整、渠道为 https，且包含 Qwen3.6/3.8 候选。"""
    candidates = load_candidates(REPO_CANDIDATES)
    assert len(candidates) >= 4
    names = [item.name for item in candidates]
    assert len(names) == len(set(names))
    assert "XuanmuSec-2.6B" in names
    assert any("Qwen3.6" in name for name in names)
    assert any("Qwen3.8" in name for name in names)
    for item in candidates:
        assert item.name
        assert item.note
        assert item.quantization
        assert item.size_label
        assert item.context_default > 0
        assert item.sources
        for source in item.sources:
            assert source.url.startswith("https://")
            assert source.label


def test_missing_catalog_returns_empty(tmp_path: Path) -> None:
    assert load_candidates(tmp_path / "absent.json") == []


def test_broken_json_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_candidates(path) == []


def test_malformed_entries_are_skipped(tmp_path: Path) -> None:
    payload = {
        "candidates": [
            "not-a-dict",
            {"name": "无渠道", "sources": []},
            {"name": "坏链接", "sources": [{"label": "ftp", "url": "ftp://example.com/a"}]},
            {"name": "重复", "sources": [{"url": "https://a.example/1"}]},
            {"name": "重复", "sources": [{"url": "https://a.example/2"}]},
            {
                "name": "  好 模 型  ",
                "quantization": "q4_K_M",
                "size_label": "约 1 GB",
                "architecture": "qwen3",
                "context_default": 0,  # 非法，回退默认值
                "note": "合法条目",
                "sources": [
                    {"label": "主渠道", "url": "https://example.com/main"},
                    {"label": "重复渠道", "url": "https://example.com/main"},
                    {"label": "无协议", "url": "example.com/x"},
                ],
            },
        ]
    }
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    candidates = load_candidates(path)
    assert len(candidates) == 2  # 重复去重后：'重复' + '好 模 型'
    first, second = candidates
    assert first.name == "重复"
    assert first.sources[0].url == "https://a.example/1"
    assert second.name == "好 模 型"
    assert second.context_default == 8192
    assert len(second.sources) == 1
    assert second.sources[0].label == "主渠道"


def test_settings_page_loads_catalog_and_copy_link(
    qt_app, config: AppConfig, tmp_path: Path
) -> None:
    """设置页从 models/candidates.json 装载候选，并支持复制链接与缺失降级。"""
    models_dir = config.paths.models
    models_dir.mkdir(parents=True, exist_ok=True)
    catalog = models_dir / "candidates.json"
    catalog.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "name": "Qwen3.6-35B-A3B",
                        "quantization": "Q4_K_M",
                        "size_label": "约 20 GB",
                        "architecture": "qwen3moe",
                        "context_default": 32768,
                        "note": "测试候选条目",
                        "sources": [
                            {"label": "发布页", "url": "https://example.com/qwen36"}
                        ],
                    },
                    {
                        "name": "Qwen3.8-27B",
                        "quantization": "Q4_K_M",
                        "size_label": "约 16 GB",
                        "architecture": "qwen3",
                        "context_default": 32768,
                        "note": "测试候选条目二",
                        "sources": [
                            {"label": "官方", "url": "https://example.com/qwen38"},
                            {"label": "GGUF", "url": "https://example.com/qwen38-gguf"},
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    context = build_context(config)
    settings = SettingsPage(context)
    try:
        assert settings.candidate_combo.isVisible() or settings.candidate_combo.count() == 2
        assert settings.candidate_combo.count() == 2
        assert "Qwen3.6-35B-A3B" in settings.candidate_combo.itemText(0)

        settings.candidate_combo.setCurrentIndex(0)
        detail = settings.candidate_detail.text()
        assert "qwen3moe" in detail
        assert "https://example.com/qwen36" in detail
        assert "Qwen3.8-27B" not in detail

        settings.candidate_combo.setCurrentIndex(1)
        assert "https://example.com/qwen38-gguf" in settings.candidate_detail.text()

        settings._copy_candidate_source()
        clipboard = QApplication.clipboard().text()
        assert "https://example.com/qwen38" in clipboard
        assert "https://example.com/qwen38-gguf" in clipboard
    finally:
        settings.deleteLater()


def test_settings_page_falls_back_without_catalog(
    qt_app, config: AppConfig
) -> None:
    """缺少清单文件时界面不崩溃，给出提示并隐藏下载按钮。"""
    context = build_context(config)
    settings = SettingsPage(context)
    try:
        assert settings.candidate_combo.count() == 0
        assert settings.candidate_open_btn.isHidden()
        assert settings.candidate_copy_btn.isHidden()
        assert "candidates.json" in settings.candidate_detail.text()
    finally:
        settings.deleteLater()
