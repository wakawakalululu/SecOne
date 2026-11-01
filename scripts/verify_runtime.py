#!/usr/bin/env python
"""Real-runtime verification for the SecOne local inference path.

This script exercises the *production* code paths -- ``LlamaServerManager`` and
``LLMClient`` -- against a real ``llama-server`` binary and a real GGUF file.
It is an acceptance harness, not a unit test: it launches a child process,
waits for /health, performs a chat completion, and shuts the server down.

Usage (from the repository root, with the project-local interpreter):

    .\\.python\\python.exe scripts\\verify_runtime.py ^
        --gguf models\\verify-qwen2.5-0.5b-instruct-q4_k_m.gguf ^
        --runtime runtime\\llama-server.exe ^
        --port 18099

Exit codes: 0 = every check passed, 1 = at least one check failed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from secone.config import AppConfig  # noqa: E402
from secone.llm.client import LLMClient, LLMError  # noqa: E402
from secone.llm.server import LlamaServerManager, ModelError  # noqa: E402
from secone.paths import AppPaths  # noqa: E402


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append({"check": name, "ok": bool(ok), "detail": detail})
        mark = "PASS" if ok else "FAIL"
        line = f"[{mark}] {name}"
        if detail:
            line += f" :: {detail}"
        print(line, flush=True)
        return bool(ok)

    @property
    def ok(self) -> bool:
        return all(row["ok"] for row in self.rows)


def probe_binary(path: Path, checks: Checks) -> str:
    if not checks.record("runtime/llama-server.exe 存在", path.is_file(), str(path)):
        return ""
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(path.parent),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        checks.record("llama-server --version 可执行", False, str(exc))
        return ""
    version = (completed.stdout or completed.stderr).strip()
    checks.record(
        "llama-server --version 可执行", completed.returncode == 0, version.replace("\n", " | ")[:160]
    )
    return version


def build_manager(args: argparse.Namespace) -> tuple[AppConfig, LlamaServerManager, Path]:
    sandbox = Path(tempfile.mkdtemp(prefix="secone-verify-"))
    paths = AppPaths(sandbox)
    paths.ensure()
    config = AppConfig(paths)
    config.set("engine.gguf", str(args.gguf.resolve()))
    config.set("engine.runtime", str(args.runtime.resolve()))
    config.set("engine.port", args.port)
    config.set("engine.host", "127.0.0.1")
    config.set("engine.managed", True)
    config.set("engine.context_size", args.context_size)
    config.set("engine.threads", args.threads)
    config.set("engine.gpu_layers", 0)
    config.set("engine.startup_timeout", args.startup_timeout)
    config.set("engine.request_timeout", args.request_timeout)
    manager = LlamaServerManager(config)
    return config, manager, sandbox


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验证 SecOne 的本地推理链路（真实 llama-server + 真实 GGUF）。")
    parser.add_argument("--gguf", type=Path, default=ROOT / "models" / "verify-qwen2.5-0.5b-instruct-q4_k_m.gguf")
    parser.add_argument("--runtime", type=Path, default=ROOT / "runtime" / "llama-server.exe")
    parser.add_argument("--port", type=int, default=18099)
    parser.add_argument("--context-size", type=int, default=2048)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--startup-timeout", type=int, default=180)
    parser.add_argument("--request-timeout", type=int, default=180)
    parser.add_argument("--json-out", type=Path, default=ROOT / "artifacts" / "runtime_verification.json")
    args = parser.parse_args(argv)

    checks = Checks()
    sandbox: Path | None = None
    manager: LlamaServerManager | None = None
    started_at = time.monotonic()
    try:
        probe_binary(args.runtime, checks)
        checks.record("GGUF 文件存在", args.gguf.is_file(), str(args.gguf))

        config, manager, sandbox = build_manager(args)
        info = manager.model_info()
        checks.record(
            "GGUF 头校验通过",
            info.gguf_valid,
            f"v{info.gguf_version} arch={info.architecture or '?'} ctx={info.context_length}",
        )
        checks.record(
            "GGUF 元数据解析通过",
            bool(info.metadata_ok),
            f"block_count={info.block_count} tokenizer={info.tokenizer_model or '?'} "
            f"template={'有' if info.chat_template_present else '无'} {info.metadata_error}".strip(),
        )
        checks.record("启动前健康检查为未运行", not info.health_ok, manager.status())

        try:
            started = manager.start()
        except ModelError as exc:
            checks.record("LlamaServerManager.start()", False, str(exc).replace("\n", " / ")[:400])
            raise
        checks.record(
            "LlamaServerManager.start()",
            started.health_ok,
            f"status={manager.status()} 用时 {time.monotonic() - started_at:.1f}s",
        )
        checks.record(
            "服务绑定 127.0.0.1",
            started.health_ok and manager.base_url == f"http://127.0.0.1:{args.port}",
            manager.base_url,
        )

        client = LLMClient(config, manager)
        checks.record("LLMClient.is_ready()", client.is_ready(), "")
        models = client.list_models()
        checks.record("GET /v1/models", bool(models), ", ".join(models)[:160])

        try:
            reply = client.test()
        except LLMError as exc:
            checks.record("LLMClient.test() 对话", False, str(exc)[:300])
            raise
        checks.record(
            "LLMClient.test() 对话",
            bool(reply.content.strip()),
            f"{reply.elapsed_seconds:.1f}s prompt={reply.prompt_tokens} "
            f"completion={reply.completion_tokens} :: {reply.content.strip()[:80]}",
        )

        pinned = client.chat(
            system="你是严格的问答助手，只输出 JSON，不要 Markdown。",
            user='请输出 JSON：{"engine":"SecOne","ok":true}',
            max_tokens=96,
            temperature=0.0,
        )
        checks.record(
            "结构化输出（temperature=0）",
            "{" in pinned.content,
            pinned.content.strip().replace("\n", " ")[:160],
        )

        log_tail = manager.log_tail(6)
        checks.record(
            "服务日志已落盘",
            bool(log_tail),
            (log_tail.splitlines()[-1][:120] if log_tail else "logs/llama-server.log 为空"),
        )
    finally:
        if manager is not None:
            try:
                manager.stop()
            except Exception as exc:  # pragma: no cover - defensive
                checks.record("LlamaServerManager.stop()", False, str(exc))
        if manager is not None:
            checks.record(
                "LlamaServerManager.stop() 后端口释放",
                not manager.health(timeout=1.0),
                manager.base_url,
            )
        elapsed = time.monotonic() - started_at
        payload = {
            "ok": checks.ok,
            "elapsed_seconds": round(elapsed, 2),
            "gguf": str(args.gguf),
            "runtime": str(args.runtime),
            "port": args.port,
            "checks": checks.rows,
        }
        try:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"\n报告：{args.json_out}")
        except OSError as exc:
            print(f"无法写入报告：{exc}", file=sys.stderr)
        if sandbox is not None:
            shutil.rmtree(sandbox, ignore_errors=True)
        print(f"结论：{'全部通过' if checks.ok else '存在失败项'}（{elapsed:.1f}s）")
    return 0 if checks.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
