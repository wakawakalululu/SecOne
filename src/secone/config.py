from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

from .paths import AppPaths, app_root

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "name": "SecOne",
        "edition": "Local Intelligence Workstation",
        "version": "1.0.0-rc1",
        "language": "zh-CN",
        "operator": "",
    },
    "engine": {
        "display_name": "SecOne 本地引擎",
        "gguf": "models/XuanmuSec-v2-Q6_K.gguf",
        "runtime": "runtime/llama-server.exe",
        "host": "127.0.0.1",
        "port": 18080,
        "context_size": 8192,
        "max_tokens": 1536,
        "temperature": 0.2,
        "gpu_layers": 0,
        "threads": 0,
        "auto_start": True,
        "request_timeout": 300,
        "startup_timeout": 120,
        "managed": True,
        "extra_args": [],
    },
    "analysis": {
        "max_files": 500,
        "max_file_mb": 64,
        "max_total_mb": 256,
        "max_text_chars": 60000,
        "ai_context_chars": 16000,
        "decode_depth": 3,
        "max_decode_results": 80,
        "archive_depth": 3,
        "archive_max_entries": 400,
        "archive_max_total_mb": 512,
        "binary_string_min": 5,
        "ai_enabled": True,
    },
    "ui": {"theme": "dark", "open_report_folder": False},
    "flags": {
        "patterns": [
            r"(?i)\bflag\{[^{}\r\n]{1,200}\}",
            r"(?i)\bctf\{[^{}\r\n]{1,200}\}",
            r"(?i)\bsecone\{[^{}\r\n]{1,200}\}",
            r"(?i)\bflag\([^()\r\n]{1,200}\)",
        ],
        "custom_prefixes": [],
    },
    "paths": {
        "workspace": "workspace",
        "output": "output",
        "data": "data",
        "logs": "logs",
    },
}

DEFAULT_SYSTEM_PROMPT = (
    "你是 SecOne 本地安全分析工作台中的分析引擎。"
    "只分析用户主动提供的、已获授权的材料。"
    "不得编造文件内容、命令输出、偏移地址或 flag；证据不足时明确说明。"
    "使用中文回答，引用原文并解释依据。"
)

DEFAULT_USER_TEMPLATE = """分析模式：{mode_label}
任务材料摘要：
{inventory}

静态工具发现：
{findings}

已提取的 Flag 候选：
{flags}

材料摘录：
-----BEGIN MATERIAL-----
{material}
-----END MATERIAL-----

请输出材料研判、可复现的解题路径、Flag 判断和下一步建议。"""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


class AppConfig:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.file = paths.config / "app.yaml"
        self.prompts_file = paths.config / "prompts.yaml"
        self.data: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self._prompts: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.file.exists():
            with self.file.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
            if not isinstance(raw, dict):
                raise ValueError(f"配置文件格式错误：{self.file}")
            self.data = _deep_merge(DEFAULT_CONFIG, raw)
        else:
            self.data = copy.deepcopy(DEFAULT_CONFIG)

        self._prompts = {}
        if self.prompts_file.exists():
            with self.prompts_file.open("r", encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
            if isinstance(raw, dict):
                self._prompts = raw
        self._prompts.setdefault("system", DEFAULT_SYSTEM_PROMPT)
        self._prompts.setdefault("user_template", DEFAULT_USER_TEMPLATE)

    def reload(self) -> None:
        self.load()

    def save(self) -> None:
        self.paths.config.mkdir(parents=True, exist_ok=True)
        with self.file.open("w", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(
                self.data,
                handle,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )

    def get(self, dotted: str, default: Any = None) -> Any:
        current: Any = self.data
        for part in dotted.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        current = self.data
        for part in parts[:-1]:
            node = current.get(part)
            if not isinstance(node, dict):
                node = {}
                current[part] = node
            current = node
        current[parts[-1]] = value

    def prompt(self, key: str) -> str:
        return str(self._prompts.get(key, ""))

    def resolve(self, value: str | Path) -> Path:
        return self.paths.resolve(value)

    @property
    def model_path(self) -> Path:
        return self.resolve(str(self.get("engine.gguf", "")))

    @property
    def runtime_path(self) -> Path:
        return self.resolve(str(self.get("engine.runtime", "")))

    @property
    def api_base_url(self) -> str:
        host = str(self.get("engine.host", "127.0.0.1"))
        port = int(self.get("engine.port", 18080))
        return f"http://{host}:{port}"

    def flag_patterns(self) -> list[str]:
        patterns = [str(item) for item in self.get("flags.patterns", []) if str(item).strip()]
        for prefix in self.get("flags.custom_prefixes", []) or []:
            prefix = str(prefix).strip()
            if prefix:
                patterns.append(
                    re.escape(prefix) + r"\{[^{}\r\n]{1,200}\}"
                )
        return patterns


def load_config(root: Path | None = None) -> AppConfig:
    base = root.resolve() if root else app_root()
    paths = AppPaths(base)
    paths.ensure()
    return AppConfig(paths)
