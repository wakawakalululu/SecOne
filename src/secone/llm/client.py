from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from ..config import AppConfig
from .server import LlamaServerManager

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    content: str
    model: str
    elapsed_seconds: float
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient:
    def __init__(self, config: AppConfig, manager: LlamaServerManager):
        self.config = config
        self.manager = manager
        self._opener = build_opener(ProxyHandler({}))

    @property
    def base_url(self) -> str:
        return self.manager.base_url

    def is_ready(self) -> bool:
        return self.manager.health()

    def chat(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
        cancel: threading.Event | None = None,
    ) -> LLMResponse:
        if not self.manager.health():
            raise LLMError("本地模型服务未启动，无法执行 AI 推理。")
        payload = {
            "model": "secone-local",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": float(
                temperature
                if temperature is not None
                else self.config.get("engine.temperature", 0.2)
            ),
            "max_tokens": int(
                max_tokens
                if max_tokens is not None
                else self.config.get("engine.max_tokens", 1536)
            ),
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.base_url}/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": "Bearer local",
            },
            method="POST",
        )
        request_timeout = timeout or int(self.config.get("engine.request_timeout", 300))
        started = time.monotonic()
        outcome: dict[str, object] = {}

        def _fetch() -> None:
            try:
                with self._opener.open(request, timeout=request_timeout) as response:
                    outcome["raw"] = response.read()
            except BaseException as exc:  # surfaced on the calling thread
                outcome["error"] = exc

        fetch = threading.Thread(
            target=_fetch, name="secone-llm-request", daemon=True
        )
        fetch.start()
        while fetch.is_alive():
            if cancel is not None and cancel.is_set():
                raise LLMError("模型推理已取消。")
            fetch.join(0.2)
        error = outcome.get("error")
        if isinstance(error, HTTPError):
            detail = ""
            try:
                detail = error.read().decode("utf-8", "replace")[:1000]
            except Exception:
                pass
            raise LLMError(
                f"模型接口返回 HTTP {error.code}：{detail or error.reason}"
            ) from error
        if isinstance(error, (URLError, TimeoutError, OSError)):
            raise LLMError(f"无法连接本地模型服务：{error}") from error
        if error is not None:
            raise LLMError(f"模型推理失败：{error}") from error
        raw = outcome.get("raw") or b""
        elapsed = time.monotonic() - started
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMError("模型接口返回了无法解析的响应。") from exc
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("模型接口没有返回 choices。")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict)
            )
        if not content:
            content = message.get("reasoning_content") or ""
        content = str(content).strip()
        if not content:
            raise LLMError("模型返回了空内容。请检查模型对话模板或上下文长度。")
        usage = data.get("usage") or {}
        model = self._model_label(str(data.get("model") or ""))
        logger.info(
            "LLM response in %.1fs, prompt=%s completion=%s",
            elapsed,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        return LLMResponse(
            content=content,
            model=model,
            elapsed_seconds=elapsed,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
        )

    def test(self) -> LLMResponse:
        return self.chat(
            system="你是本地模型连通性测试助手。只输出要求的短语，不要解释。",
            user="请只回复：SecOne 模型连接正常",
            max_tokens=48,
            temperature=0.0,
            timeout=min(int(self.config.get("engine.request_timeout", 300)), 120),
        )

    def list_models(self) -> list[str]:
        if not self.manager.health():
            return []
        try:
            with self._opener.open(f"{self.base_url}/v1/models", timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            return [str(item.get("id", "")) for item in data.get("data", [])]
        except (HTTPError, URLError, OSError, json.JSONDecodeError):
            return []

    def _model_label(self, raw: str) -> str:
        """Turn the service-reported model id into a report-safe label.

        llama-server reports the *absolute path* of the loaded weights as the
        model id. Writing that into a report would leak the operator's local
        directory layout, so path-shaped ids are replaced by the configured
        display name. Genuine ids from other OpenAI-compatible servers are kept.
        """
        candidate = raw.strip()
        if not candidate:
            return self.manager.display_label()
        normalized = candidate.replace("\\", "/")
        looks_like_path = bool(
            re.match(r"^[A-Za-z]:/", normalized)
            or normalized.startswith("/")
            or normalized.startswith("./")
            or normalized.lower().endswith(".gguf")
        )
        if looks_like_path:
            return self.manager.display_label()
        return candidate
