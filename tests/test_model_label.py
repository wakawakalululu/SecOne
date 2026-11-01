from __future__ import annotations

from pathlib import Path

import pytest

from secone.config import AppConfig
from secone.llm.client import LLMClient
from secone.llm.server import LlamaServerManager
from secone.paths import AppPaths


@pytest.fixture
def manager(app_paths: AppPaths) -> LlamaServerManager:
    cfg = AppConfig(app_paths)
    cfg.set("engine.display_name", "XuanmuSec-2.6B")
    cfg.set("engine.gguf", "models/XuanmuSec-v2-Q6_K.gguf")
    return LlamaServerManager(cfg)


@pytest.fixture
def client(manager: LlamaServerManager) -> LLMClient:
    return LLMClient(manager.config, manager)


def test_windows_absolute_path_is_replaced(manager: LlamaServerManager, client: LLMClient) -> None:
    label = client._model_label(r"C:\Users\Admin\Desktop\code\SecOne\models\m.gguf")
    assert label == manager.display_label()
    assert "Admin" not in label


def test_posix_absolute_path_is_replaced(client: LLMClient) -> None:
    assert "opt" not in client._model_label("/opt/models/model.gguf")


def test_relative_gguf_path_is_replaced(client: LLMClient) -> None:
    assert client._model_label("./models/m.gguf").endswith("Q6_K")


def test_bare_gguf_filename_is_replaced(client: LLMClient) -> None:
    assert client._model_label("XuanmuSec-v2-Q6_K.gguf") == "XuanmuSec-2.6B · Q6_K"


def test_plain_model_id_is_kept(client: LLMClient) -> None:
    assert client._model_label("xuanmusec") == "xuanmusec"


def test_empty_id_falls_back_to_display_label(manager: LlamaServerManager, client: LLMClient) -> None:
    assert client._model_label("   ") == manager.display_label()


def test_display_label_never_contains_path(manager: LlamaServerManager) -> None:
    label = manager.display_label()
    assert "\\" not in label and "/" not in label
    assert label.startswith("XuanmuSec-2.6B")


def test_display_label_omits_unknown_quantization(app_paths: AppPaths) -> None:
    cfg = AppConfig(app_paths)
    cfg.set("engine.display_name", "CustomModel")
    cfg.set("engine.gguf", "models/mystery.bin")
    assert LlamaServerManager(cfg).display_label() == "CustomModel"
