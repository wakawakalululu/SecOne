from __future__ import annotations

import struct

from secone.config import AppConfig
from secone.llm.server import LlamaServerManager, read_gguf_metadata


def u32(value: int) -> bytes:
    return struct.pack("<I", value)


def u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def gstr(value: str) -> bytes:
    payload = value.encode("utf-8")
    return u64(len(payload)) + payload


def kv_string(key: str, value: str) -> bytes:
    return gstr(key) + u32(8) + gstr(value)


def kv_u32(key: str, value: int) -> bytes:
    return gstr(key) + u32(4) + u32(value)


def kv_u32_array(key: str, values: list[int]) -> bytes:
    return gstr(key) + u32(9) + u32(4) + u64(len(values)) + b"".join(
        u32(item) for item in values
    )


def write_gguf_metadata(path, version: int = 3, *, truncate: bool = False) -> None:
    entries = [
        kv_string("general.architecture", "lfm2"),
        kv_string("general.name", "XuanmuSec-2.6B"),
        kv_string("tokenizer.ggml.model", "gpt2"),
        kv_string("tokenizer.chat_template", "{{ messages }}"),
        kv_u32("lfm2.context_length", 8192),
        kv_u32("lfm2.block_count", 30),
        kv_u32_array("tokenizer.ggml.tokens", list(range(5))),
    ]
    body = b"".join(entries)
    header = b"GGUF" + u32(version) + u64(0) + u64(len(entries))
    if truncate:
        body = body[: len(body) // 2]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + body)


def test_metadata_parser_reads_architecture_and_chat_template(
    config: AppConfig,
) -> None:
    config.set("engine.port", 1)
    write_gguf_metadata(config.model_path)
    info = LlamaServerManager(config).model_info()
    assert info.gguf_valid is True
    assert info.metadata_ok is True
    assert info.architecture == "lfm2"
    assert info.context_length == 8192
    assert info.block_count == 30
    assert info.tokenizer_model == "gpt2"
    assert info.chat_template_present is True
    assert info.runtime_verified is False


def test_metadata_parser_handles_truncated_file(config: AppConfig) -> None:
    config.set("engine.port", 1)
    write_gguf_metadata(config.model_path, truncate=True)
    info = LlamaServerManager(config).model_info()
    assert info.gguf_valid is True
    assert info.metadata_ok is False
    assert "GGUF 元数据" in info.metadata_error
    assert info.chat_template_present is False
    assert info.runtime_verified is False
    assert "运行中" not in info.summary


def test_metadata_missing_chat_template_is_reported(config: AppConfig) -> None:
    config.set("engine.port", 1)
    path = config.model_path
    entries = [kv_string("general.architecture", "lfm2")]
    header = b"GGUF" + u32(3) + u64(0) + u64(len(entries))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + b"".join(entries))
    info = LlamaServerManager(config).model_info()
    assert info.metadata_ok is True
    assert info.chat_template_present is False
    assert info.summary == "模型已就绪，但缺少对话模板"


def test_gguf_v1_reports_legacy_layout(config: AppConfig) -> None:
    config.set("engine.port", 1)
    path = config.model_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"GGUF" + u32(1) + u64(0) + u64(0))
    result = read_gguf_metadata(path, 1)
    assert result["ok"] is False
    assert "v1" in result["error"]
    info = LlamaServerManager(config).model_info()
    assert info.gguf_valid is True
    assert info.metadata_ok is False
