#!/usr/bin/env python
"""End-to-end acceptance run: real llama-server + real GGUF + full pipeline.

Verifies the whole SecOne chain that unit tests cannot cover:

  1. the manager launches the real server and becomes healthy;
  2. ``AnalysisPipeline`` ingest -> plugins -> flag engine -> AI analysis
     completes and persists a task;
  3. the anti-hallucination guard rejects a model-proposed flag that does not
     literally occur in the material;
  4. reports are written in all three formats.

Usage:
  .\\.python\\python.exe scripts\\verify_ai_pipeline.py --port 18101
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from secone.config import AppConfig  # noqa: E402
from secone.core.flag_engine import FlagEngine  # noqa: E402
from secone.core.pipeline import AnalysisPipeline  # noqa: E402
from secone.core.report import ReportWriter  # noqa: E402
from secone.db import TaskStore  # noqa: E402
from secone.llm import LLMClient, LlamaServerManager  # noqa: E402
from secone.paths import AppPaths  # noqa: E402

SAMPLES = ROOT / "artifacts" / "demo_materials"


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""), flush=True)
        return bool(ok)

    @property
    def ok(self) -> bool:
        return all(row["ok"] for row in self.rows)


def guard_selftest(checks: Checks) -> None:
    """Anti-hallucination guard must reject invented flags and accept real ones."""
    engine = FlagEngine(patterns=[r"(?i)\bflag\{[^{}\r\n]{1,200}\}"])
    material = "题目材料里包含 flag{r34l_m4t3r14l_t0k3n} 这一行。"
    invented = "模型声称答案是 flag{1nv3nt3d_by_m0d3l}，但实际上材料里没有。"
    added, rejected = engine.add_ai_candidates(invented, material)
    checks.record(
        "防幻觉：拒绝材料中不存在的 flag",
        not added and rejected == ["flag{1nv3nt3d_by_m0d3l}"],
        f"added={[a.value for a in added]} rejected={rejected}",
    )
    added2, rejected2 = engine.add_ai_candidates(
        "材料中可见 flag{r34l_m4t3r14l_t0k3n}", material
    )
    checks.record(
        "防幻觉：接受材料中真实存在的 flag",
        len(added2) == 1 and not rejected2 and added2[0].status == "candidate",
        f"added={[a.value for a in added2]} status={added2[0].status if added2 else '-'}",
    )
    checks.record(
        "防幻觉：AI 候选不会被自动判定为答案",
        all(a.status == "candidate" and a.ai_generated for a in added2),
        f"{[(a.status, a.ai_generated) for a in added2]}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SecOne 全链路验收（真实模型）。")
    parser.add_argument("--gguf", type=Path, default=ROOT / "models" / "verify-qwen2.5-0.5b-instruct-q4_k_m.gguf")
    parser.add_argument("--runtime", type=Path, default=ROOT / "runtime" / "llama-server.exe")
    parser.add_argument("--port", type=int, default=18101)
    parser.add_argument("--json-out", type=Path, default=ROOT / "artifacts" / "ai_pipeline_verification.json")
    args = parser.parse_args(argv)

    checks = Checks()
    sandbox = Path(tempfile.mkdtemp(prefix="secone-ai-"))
    manager: LlamaServerManager | None = None
    started = time.monotonic()
    summary: dict = {}
    try:
        guard_selftest(checks)

        if not SAMPLES.is_dir():
            checks.record("演示材料存在", False, str(SAMPLES))
            return 1

        paths = AppPaths(sandbox)
        paths.ensure()
        config = AppConfig(paths)
        config.set("engine.gguf", str(args.gguf.resolve()))
        config.set("engine.runtime", str(args.runtime.resolve()))
        config.set("engine.port", args.port)
        config.set("engine.context_size", 4096)
        config.set("engine.max_tokens", 512)
        config.set("engine.startup_timeout", 180)
        config.set("engine.request_timeout", 240)
        config.set("analysis.ai_enabled", True)
        config.set("analysis.ai_context_chars", 6000)

        manager = LlamaServerManager(config)
        info = manager.start()
        checks.record("真实模型服务启动", info.health_ok, manager.base_url)
        checks.record("引擎标识包含模型名", bool(config.get("engine.display_name")), manager.engine_description())

        client = LLMClient(config, manager)
        store = TaskStore(paths.db_file)
        progress: list[tuple[int, str]] = []
        pipeline = AnalysisPipeline(
            config, store, llm=client, manager=manager,
            progress=lambda pct, msg: progress.append((pct, msg)),
        )
        result = pipeline.run([SAMPLES], mode="auto", title_hint="AI 全链路验收")
        checks.record(
            "流水线完成",
            result.task_id != "" and len(result.files) > 0,
            f"files={len(result.files)} flags={len(result.flags)} findings={len(result.findings)}",
        )
        checks.record(
            "AI 推理参与并返回内容",
            result.ai_used and bool(result.ai_text.strip()),
            f"ai_used={result.ai_used} chars={len(result.ai_text)} engine={result.engine} err={result.ai_error[:120]}",
        )
        checks.record(
            "进度回调覆盖 0-100",
            progress and progress[-1][0] == 100,
            f"steps={len(progress)} last={progress[-1] if progress else None}",
        )
        checks.record(
            "任务写入数据库并完成",
            (store.get(result.task_id) or None) is not None
            and store.get(result.task_id).status == "completed",
            f"status={store.get(result.task_id).status if store.get(result.task_id) else 'missing'}",
        )
        stored = store.get_result(result.task_id)
        checks.record(
            "结果可反序列化回读",
            stored is not None and stored.task_id == result.task_id,
            f"flags={len(stored.flags) if stored else 0}",
        )

        writer = ReportWriter(config, paths)
        report_paths = writer.write(result)
        missing = [name for name, path in report_paths.items() if not Path(path).is_file()]
        checks.record(
            "报告三格式落盘",
            not missing,
            f"{ {k: Path(v).name for k, v in report_paths.items()} } missing={missing}",
        )

        checks.record(
            "工作区产物齐全",
            all(
                (Path(result.workspace) / name).exists()
                for name in ("analysis/result.json", "flags/candidates.json", "evidence/index.json")
            ),
            result.workspace,
        )
        checks.record(
            "引擎标识不含本机路径",
            ("\\" not in result.engine and "/" not in result.engine and ":" not in result.engine)
            and config.get("engine.display_name") in result.engine,
            f"engine={result.engine!r}",
        )

        # Every flag the model proposed must be traceable to material text.
        ai_flags = [f for f in result.flags if f.ai_generated]
        checks.record(
            "AI 提出的候选均已回查材料",
            all(f.evidence.strip() for f in ai_flags),
            f"ai_flags={len(ai_flags)}",
        )
        summary = {
            "task_id": result.task_id,
            "flags": len(result.flags),
            "findings": len(result.findings),
            "ai_used": result.ai_used,
            "ai_chars": len(result.ai_text),
            "duration": round(result.duration_seconds, 1),
            "flag_values": [f.value for f in result.flags],
        }
        print("\n--- AI 输出摘录 ---")
        print(result.ai_text.strip()[:900])
        print("-------------------\n")
    except Exception as exc:  # noqa: BLE001 - acceptance harness
        checks.record("全链路执行", False, f"{type(exc).__name__}: {exc}")
    finally:
        if manager is not None:
            manager.stop()
            checks.record("服务已停止", not manager.health(timeout=1.0), manager.base_url)
        elapsed = time.monotonic() - started
        payload = {
            "ok": checks.ok,
            "elapsed_seconds": round(elapsed, 2),
            "model": str(args.gguf),
            "summary": summary,
            "checks": checks.rows,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"报告：{args.json_out}")
        print(f"结论：{'全部通过' if checks.ok else '存在失败项'}（{elapsed:.1f}s）")
        shutil.rmtree(sandbox, ignore_errors=True)
    return 0 if checks.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
