from __future__ import annotations

import struct

from secone.config import AppConfig
from secone.llm.server import LlamaServerManager


def write_gguf(path, version: int = 3, magic: bytes = b"GGUF") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(magic + struct.pack("<I", version) + b"\x00" * 8)


def test_valid_gguf_header_is_recognized(config: AppConfig) -> None:
    config.set("engine.port", 1)
    write_gguf(config.model_path)
    info = LlamaServerManager(config).model_info()
    assert info.model_exists is True
    assert info.gguf_valid is True
    assert info.gguf_version == 3
    assert "Q6_K" in info.quantization


def test_invalid_gguf_header_is_reported(config: AppConfig) -> None:
    config.set("engine.port", 1)
    write_gguf(config.model_path, magic=b"NOPE")
    info = LlamaServerManager(config).model_info()
    assert info.model_exists is True
    assert info.gguf_valid is False
    assert info.summary == "模型文件不是有效 GGUF"


def test_missing_model_is_reported(config: AppConfig) -> None:
    config.set("engine.port", 1)
    info = LlamaServerManager(config).model_info()
    assert info.model_exists is False
    assert info.gguf_valid is False
    assert info.health_ok is False
    assert info.summary == "模型文件未安装"
