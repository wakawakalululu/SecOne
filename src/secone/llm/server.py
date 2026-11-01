from __future__ import annotations

import json
import logging
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from ..config import AppConfig
from ..core.fileio import format_size

logger = logging.getLogger(__name__)


class ModelError(RuntimeError):
    pass


_GGUF_FIXED_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_GGUF_SCALAR_FORMATS = {
    0: "<B",
    1: "<b",
    2: "<H",
    3: "<h",
    4: "<I",
    5: "<i",
    6: "<f",
    7: "<B",
    10: "<Q",
    11: "<q",
    12: "<d",
}
_GGUF_CACHE: dict[tuple[str, int, int], dict] = {}


class _GgufReader:
    def __init__(self, handle, size: int, wide: bool):
        self.handle = handle
        self.size = size
        self.wide = wide

    def _read(self, count: int) -> bytes:
        if count < 0 or self.handle.tell() + count > self.size:
            raise ValueError("GGUF 元数据越界")
        data = self.handle.read(count)
        if len(data) != count:
            raise ValueError("GGUF 元数据不完整")
        return data

    def _skip(self, count: int) -> None:
        target = self.handle.tell() + count
        if count < 0 or target > self.size:
            raise ValueError("GGUF 元数据越界")
        self.handle.seek(count, 1)

    def u32(self) -> int:
        return struct.unpack("<I", self._read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self._read(8))[0]

    def count(self) -> int:
        return self.u64() if self.wide else self.u32()

    def string(self) -> str:
        length = self.count()
        if length > 16 * 1024 * 1024:
            raise ValueError("GGUF 字符串超出长度限制")
        return self._read(length).decode("utf-8", "replace")

    def scalar(self, value_type: int):
        fmt = _GGUF_SCALAR_FORMATS.get(value_type)
        if fmt is None:
            raise ValueError(f"未知 GGUF 元数据类型 {value_type}")
        return struct.unpack(fmt, self._read(struct.calcsize(fmt)))[0]

    def skip_value(self, value_type: int) -> None:
        if value_type == 8:
            length = self.count()
            if length > 16 * 1024 * 1024:
                raise ValueError("GGUF 字符串超出长度限制")
            self._skip(length)
            return
        if value_type == 9:
            self.skip_array()
            return
        size = _GGUF_FIXED_SIZES.get(value_type)
        if size is None:
            raise ValueError(f"未知 GGUF 元数据类型 {value_type}")
        self._skip(size)

    def skip_array(self) -> None:
        element_type = self.u32()
        count = self.count()
        if count > 25_000_000:
            raise ValueError("GGUF 数组超出长度限制")
        if element_type in _GGUF_FIXED_SIZES:
            self._skip(_GGUF_FIXED_SIZES[element_type] * count)
            return
        if element_type == 8:
            for _ in range(count):
                length = self.count()
                if length > 16 * 1024 * 1024:
                    raise ValueError("GGUF 字符串超出长度限制")
                self._skip(length)
            return
        if element_type == 9:
            for _ in range(count):
                self.skip_array()
            return
        raise ValueError(f"未知 GGUF 数组元素类型 {element_type}")


def read_gguf_metadata(path: Path, version: int) -> dict:
    try:
        stat = path.stat()
    except OSError as exc:
        return {"ok": False, "error": f"无法读取模型文件：{exc}"}
    cache_key = (str(path), int(stat.st_mtime), version)
    cached = _GGUF_CACHE.get(cache_key)
    if cached is not None:
        return cached
    result = {
        "ok": False,
        "error": "",
        "architecture": "",
        "name": "",
        "context_length": 0,
        "block_count": 0,
        "tokenizer_model": "",
        "chat_template": "",
    }
    if version < 2:
        result["error"] = "GGUF v1 元数据布局较旧，仅完成文件头校验。"
        _GGUF_CACHE[cache_key] = result
        return result
    try:
        with path.open("rb") as handle:
            handle.seek(16)
            reader = _GgufReader(handle, stat.st_size, wide=True)
            kv_count = reader.count()
            if kv_count > 8192:
                raise ValueError("GGUF 元数据条目数量异常")
            for _ in range(kv_count):
                key = reader.string()
                value_type = reader.u32()
                if value_type == 9:
                    reader.skip_array()
                    continue
                if value_type == 8:
                    value = reader.string()
                elif value_type in _GGUF_SCALAR_FORMATS:
                    value = reader.scalar(value_type)
                else:
                    reader.skip_value(value_type)
                    continue
                if key == "general.architecture":
                    result["architecture"] = str(value)
                elif key == "general.name":
                    result["name"] = str(value)
                elif key == "tokenizer.ggml.model":
                    result["tokenizer_model"] = str(value)
                elif key == "tokenizer.chat_template":
                    result["chat_template"] = str(value)[:8192]
                elif key.endswith(".context_length") and isinstance(value, int):
                    result["context_length"] = int(value)
                elif key.endswith(".block_count") and isinstance(value, int):
                    result["block_count"] = int(value)
        result["ok"] = True
    except (OSError, ValueError, struct.error) as exc:
        result["error"] = f"GGUF 元数据解析失败：{exc}"
    _GGUF_CACHE[cache_key] = result
    return result


@dataclass
class ModelInfo:
    display_name: str
    model_path: Path
    runtime_path: Path
    model_exists: bool
    runtime_exists: bool
    gguf_valid: bool
    size_bytes: int
    quantization: str
    gguf_version: int = 0
    health_ok: bool = False
    managed: bool = True
    architecture: str = ""
    context_length: int = 0
    block_count: int = 0
    tokenizer_model: str = ""
    chat_template: str = ""
    metadata_ok: bool = False
    metadata_error: str = ""

    @property
    def chat_template_present(self) -> bool:
        return bool(self.chat_template.strip())

    @property
    def runtime_verified(self) -> bool:
        return self.health_ok

    @property
    def summary(self) -> str:
        if not self.model_exists:
            return "模型文件未安装"
        if not self.gguf_valid:
            return "模型文件不是有效 GGUF"
        if self.health_ok:
            return "本地推理服务运行中"
        if self.metadata_ok and not self.chat_template_present:
            return "模型已就绪，但缺少对话模板"
        if not self.runtime_exists:
            return "推理引擎未安装"
        return "模型已就绪，服务未启动（尚未完成实机推理验证）"


class LlamaServerManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self._process: subprocess.Popen | None = None
        self._log_path: Path | None = None
        self._lock = threading.RLock()
        self._opener = build_opener(ProxyHandler({}))

    @property
    def host(self) -> str:
        return str(self.config.get("engine.host", "127.0.0.1"))

    @property
    def port(self) -> int:
        return int(self.config.get("engine.port", 18080))

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def managed(self) -> bool:
        return bool(self.config.get("engine.managed", True))

    def model_info(self) -> ModelInfo:
        model_path = self.config.model_path
        runtime_path = self.config.runtime_path
        exists = model_path.is_file()
        runtime_exists = runtime_path.is_file()
        size = model_path.stat().st_size if exists else 0
        version = 0
        valid = False
        if exists:
            try:
                with model_path.open("rb") as handle:
                    header = handle.read(16)
                if header[:4] == b"GGUF" and len(header) >= 16:
                    version = struct.unpack_from("<I", header, 4)[0]
                    valid = 1 <= version <= 10
            except OSError:
                valid = False
        quantization = self._quantization(model_path.name)
        metadata = read_gguf_metadata(model_path, version) if valid else {}
        return ModelInfo(
            display_name=str(
                self.config.get("engine.display_name", "SecOne 本地引擎")
            ),
            model_path=model_path,
            runtime_path=runtime_path,
            model_exists=exists,
            runtime_exists=runtime_exists,
            gguf_valid=valid,
            size_bytes=size,
            quantization=quantization,
            gguf_version=version,
            health_ok=self.health(),
            managed=self.managed,
            architecture=str(metadata.get("architecture", "")),
            context_length=int(metadata.get("context_length", 0) or 0),
            block_count=int(metadata.get("block_count", 0) or 0),
            tokenizer_model=str(metadata.get("tokenizer_model", "")),
            chat_template=str(metadata.get("chat_template", "")),
            metadata_ok=bool(metadata.get("ok", False)),
            metadata_error=str(metadata.get("error", "")),
        )

    def health(self, timeout: float = 1.5) -> bool:
        try:
            request = self._opener.open(f"{self.base_url}/health", timeout=timeout)
            with request:
                return 200 <= getattr(request, "status", 200) < 300
        except (URLError, OSError, ValueError):
            return False

    def status(self) -> str:
        info = self.model_info()
        if info.health_ok:
            return "running"
        if not info.model_exists:
            return "missing_model"
        if not info.gguf_valid:
            return "invalid_model"
        if not info.runtime_exists and self.managed:
            return "missing_runtime"
        return "stopped"

    def start(self) -> ModelInfo:
        with self._lock:
            if self.health():
                return self.model_info()
            info = self.model_info()
            if not info.model_exists:
                raise ModelError(
                    f"未找到模型文件：{info.model_path}\n"
                    "请将 GGUF 放入 models/，或在“模型与设置”页修改模型路径。"
                )
            if not info.gguf_valid:
                raise ModelError(
                    f"模型文件校验失败：{info.model_path}\n"
                    "文件头不是有效 GGUF。请确认下载完整且未与分卷文件混淆。"
                )
            if not self.managed:
                raise ModelError(
                    f"外部推理服务不可达：{self.base_url}\n"
                    "请先启动 llama-server，或切换为“由 SecOne 管理本地服务”。"
                )
            if not info.runtime_exists:
                raise ModelError(
                    f"未找到 llama-server：{info.runtime_path}\n"
                    "请将锁定版本的 llama.cpp 运行组件放入 runtime/。"
                )
            if self._port_in_use():
                raise ModelError(
                    f"端口 {self.port} 已被其他程序占用。"
                    "请在设置页更换端口，或关闭占用该端口的程序。"
                )
            self._start_process(info)
            try:
                self._wait_ready()
            except Exception:
                self.stop()
                raise
            return self.model_info()

    def _start_process(self, info: ModelInfo) -> None:
        self.config.paths.logs.mkdir(parents=True, exist_ok=True)
        self._log_path = self.config.paths.logs / "llama-server.log"
        context_size = int(self.config.get("engine.context_size", 8192))
        gpu_layers = int(self.config.get("engine.gpu_layers", 0))
        threads = int(self.config.get("engine.threads", 0))
        args: list[str] = [
            str(info.runtime_path),
            "-m",
            str(info.model_path),
            "--host",
            self.host,
            "--port",
            str(self.port),
            "-c",
            str(context_size),
            "-ngl",
            str(gpu_layers),
        ]
        if threads > 0:
            args.extend(["-t", str(threads)])
        args.extend(str(value) for value in self.config.get("engine.extra_args", []) or [])
        logger.info("Starting llama-server: %s", args)
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log_handle = self._log_path.open("ab")
        try:
            self._process = subprocess.Popen(
                args,
                cwd=str(info.runtime_path.parent),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
        except OSError as exc:
            log_handle.close()
            raise ModelError(f"启动 llama-server 失败：{exc}") from exc
        finally:
            try:
                log_handle.close()
            except Exception:
                pass

    def _wait_ready(self) -> None:
        timeout = int(self.config.get("engine.startup_timeout", 120))
        deadline = time.monotonic() + max(timeout, 5)
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                code = self._process.returncode
                tail = self.log_tail(24)
                raise ModelError(
                    f"llama-server 提前退出（代码 {code}）。\n{tail or '日志为空'}"
                )
            if self.health(timeout=1.0):
                logger.info("llama-server ready at %s", self.base_url)
                return
            time.sleep(0.6)
        raise ModelError(
            f"模型加载超时（{timeout} 秒）。\n{self.log_tail(24) or '请检查日志 logs/llama-server.log'}"
        )

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            if not process or process.poll() is not None:
                return
            logger.info("Stopping llama-server pid=%s", process.pid)
            try:
                process.terminate()
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass

    def restart(self) -> ModelInfo:
        self.stop()
        time.sleep(0.5)
        return self.start()

    def log_tail(self, lines: int = 40) -> str:
        path = self._log_path or (self.config.paths.logs / "llama-server.log")
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(content.splitlines()[-lines:])

    def _port_in_use(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((self.host, self.port)) == 0

    @staticmethod
    def _quantization(filename: str) -> str:
        upper = filename.upper()
        for quant in ("Q8_0", "Q6_K", "Q5_K_M", "Q5_K_S", "Q4_K_M", "Q4_K_S", "Q4_0", "F16", "BF16"):
            if quant in upper:
                return quant
        return "未知"

    def read_model_manifest(self) -> dict:
        manifest = self.config.paths.models / "model.json"
        if not manifest.exists():
            return {}
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def engine_description(self) -> str:
        info = self.model_info()
        parts = [info.display_name]
        if info.quantization != "未知":
            parts.append(info.quantization)
        if info.size_bytes:
            parts.append(format_size(info.size_bytes))
        return " · ".join(parts)

    def display_label(self) -> str:
        """Report-safe model name: configured display name plus quantization.

        Never derived from the on-disk path, so reports and the UI cannot leak
        the operator's directory layout.
        """
        name = (
            str(self.config.get("engine.display_name", "SecOne 本地引擎")).strip()
            or "SecOne 本地引擎"
        )
        info = self.model_info()
        if info.quantization and info.quantization != "未知":
            return f"{name} · {info.quantization}"
        return name

    def discover_models(self, limit: int = 12) -> list[Path]:
        """List usable GGUF files in the models directory, largest first.

        Lets the UI offer a one-click switch when the configured filename does
        not match what the operator actually installed, instead of dead-ending
        on "模型文件未安装".
        """
        models_dir = self.config.paths.models
        if not models_dir.is_dir():
            return []
        found: list[tuple[int, Path]] = []
        try:
            for entry in models_dir.iterdir():
                if not entry.is_file() or entry.suffix.lower() != ".gguf":
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    continue
                if size < 64 * 1024:
                    continue
                found.append((size, entry))
        except OSError:
            return []
        found.sort(key=lambda item: (-item[0], item[1].name.lower()))
        return [path for _size, path in found[:limit]]
