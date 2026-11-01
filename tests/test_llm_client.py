from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from secone.config import AppConfig
from secone.llm.client import LLMClient, LLMError
from secone.llm.server import LlamaServerManager


class MockLlamaHandler(BaseHTTPRequestHandler):
    scenario: dict = {}

    def log_message(self, *args) -> None:  # silence test output
        pass

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if self.path == "/v1/models":
            self._send_json(200, {"data": [{"id": "xuanmusec"}]})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        scenario = type(self).scenario
        if scenario.get("delay"):
            time.sleep(scenario["delay"])
        status = scenario.get("status", 200)
        self._send_json(status, scenario.get("payload", {}))


@pytest.fixture
def mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockLlamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    MockLlamaHandler.scenario = {}
    try:
        yield server, MockLlamaHandler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def make_client(config: AppConfig, server: ThreadingHTTPServer) -> LLMClient:
    config.set("engine.host", "127.0.0.1")
    config.set("engine.port", server.server_address[1])
    manager = LlamaServerManager(config)
    return LLMClient(config, manager)


def test_health_and_is_ready(config: AppConfig, mock_server) -> None:
    server, _ = mock_server
    client = make_client(config, server)
    assert client.manager.health() is True
    assert client.is_ready() is True


def test_chat_success(config: AppConfig, mock_server) -> None:
    server, handler = mock_server
    handler.scenario = {
        "payload": {
            "model": "xuanmusec",
            "choices": [{"message": {"role": "assistant", "content": "Flag 已找到"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 6},
        }
    }
    response = make_client(config, server).chat("system", "user", timeout=5)
    assert response.content == "Flag 已找到"
    assert response.prompt_tokens == 12
    assert response.completion_tokens == 6
    assert response.elapsed_seconds >= 0


def test_chat_reasoning_content_fallback(config: AppConfig, mock_server) -> None:
    server, handler = mock_server
    handler.scenario = {
        "payload": {
            "choices": [{"message": {"content": "", "reasoning_content": "推理内容"}}]
        }
    }
    response = make_client(config, server).chat("s", "u", timeout=5)
    assert response.content == "推理内容"


def test_chat_content_parts_are_joined(config: AppConfig, mock_server) -> None:
    server, handler = mock_server
    handler.scenario = {
        "payload": {
            "choices": [
                {"message": {"content": [{"text": "flag{"}, {"text": "demo}"}]}}
            ]
        }
    }
    response = make_client(config, server).chat("s", "u", timeout=5)
    assert response.content == "flag{demo}"


def test_chat_http_error_is_reported(config: AppConfig, mock_server) -> None:
    server, handler = mock_server
    handler.scenario = {"status": 500, "payload": {"error": "model crashed"}}
    with pytest.raises(LLMError) as excinfo:
        make_client(config, server).chat("s", "u", timeout=5)
    assert "HTTP 500" in str(excinfo.value)


def test_chat_empty_content_is_reported(config: AppConfig, mock_server) -> None:
    server, handler = mock_server
    handler.scenario = {"payload": {"choices": [{"message": {"content": "  "}}]}}
    with pytest.raises(LLMError) as excinfo:
        make_client(config, server).chat("s", "u", timeout=5)
    assert "空内容" in str(excinfo.value)


def test_chat_timeout_is_reported(config: AppConfig, mock_server) -> None:
    server, handler = mock_server
    handler.scenario = {"delay": 2, "payload": {"choices": []}}
    with pytest.raises(LLMError) as excinfo:
        make_client(config, server).chat("s", "u", timeout=0.5)
    assert "无法连接" in str(excinfo.value)


def test_chat_cancel_interrupts_wait(config: AppConfig, mock_server) -> None:
    server, handler = mock_server
    handler.scenario = {
        "delay": 5,
        "payload": {"choices": [{"message": {"content": "late"}}]},
    }
    client = make_client(config, server)
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()

    with pytest.raises(LLMError, match="取消"):
        client.chat("s", "u", timeout=10, cancel=cancel)

    assert time.monotonic() - started < 3


def test_chat_without_service_is_refused(config: AppConfig) -> None:
    config.set("engine.host", "127.0.0.1")
    config.set("engine.port", 1)
    client = LLMClient(config, LlamaServerManager(config))
    with pytest.raises(LLMError) as excinfo:
        client.chat("s", "u", timeout=1)
    assert "未启动" in str(excinfo.value)


def test_list_models(config: AppConfig, mock_server) -> None:
    server, _ = mock_server
    assert make_client(config, server).list_models() == ["xuanmusec"]
