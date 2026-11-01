from __future__ import annotations

import base64
import json
import threading
from pathlib import Path

import pytest

from secone.config import AppConfig
from secone.core.pipeline import (
    AnalysisPipeline,
    PipelineCancelled,
    PipelineError,
)
from secone.core.report import ReportWriter
from secone.db import TaskStore
from secone.domain import FlagStatus, TaskStatus


def build_materials(tmp_path: Path) -> Path:
    materials = tmp_path / "materials"
    materials.mkdir()
    (materials / "notes.txt").write_text(
        "\n".join(
            [
                "提交格式：flag{...}",
                f"base64: {base64.b64encode(b'flag{b64_st4g3}').decode()}",
                "plain: flag{pl41n_st4g3}",
            ]
        ),
        encoding="utf-8",
    )
    (materials / "vuln_app.py").write_text(
        "import os\n"
        "def run(request):\n"
        "    os.system(request.args.get('cmd', ''))\n"
        "    query = \"SELECT * FROM users WHERE name='{}'\".format(request.args['name'])\n"
        "    return eval(request.args.get('expr', '1'))\n",
        encoding="utf-8",
    )
    return materials


def test_pipeline_end_to_end(config: AppConfig, tmp_path: Path) -> None:
    store = TaskStore(config.paths.db_file)
    pipeline = AnalysisPipeline(config, store)

    result = pipeline.run([build_materials(tmp_path)], mode="auto", title_hint="离线流水线测试")

    assert result.status == TaskStatus.COMPLETED
    assert result.title == "离线流水线测试"
    assert len(result.files) == 2
    values = {flag.value for flag in result.flags}
    assert "flag{pl41n_st4g3}" in values
    assert "flag{b64_st4g3}" in values
    assert "flag{...}" not in values
    assert all(flag.status != FlagStatus.VERIFIED for flag in result.flags)

    rule_ids = {finding.rule_id for finding in result.findings}
    assert "web.command_exec" in rule_ids
    assert "web.eval" in rule_ids
    assert "web.sql_concat" in rule_ids

    record = store.get(result.task_id)
    assert record is not None
    assert record.status == TaskStatus.COMPLETED
    assert record.flag_count == len(result.flags)

    stored = store.get_result(result.task_id)
    assert stored is not None
    assert {flag.value for flag in stored.flags} == values

    result_json = json.loads(
        (Path(result.workspace) / "analysis" / "result.json").read_text(encoding="utf-8")
    )
    assert result_json["task_id"] == result.task_id
    assert (Path(result.workspace) / "flags" / "candidates.json").is_file()
    assert (Path(result.workspace) / "evidence" / "index.json").is_file()


def test_report_writer_outputs_all_formats(config: AppConfig, tmp_path: Path) -> None:
    store = TaskStore(config.paths.db_file)
    pipeline = AnalysisPipeline(config, store)
    result = pipeline.run([build_materials(tmp_path)], mode="auto")

    paths = ReportWriter(config, config.paths).write(result)

    for key in ("json", "markdown", "text", "summary"):
        assert Path(paths[key]).is_file()
    markdown = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "flag{pl41n_st4g3}" in markdown
    assert "方法与边界" in markdown
    assert "不执行用户提供的二进制" in markdown
    summary = Path(paths["summary"]).read_text(encoding="utf-8")
    assert result.task_id in summary


def test_cancelled_pipeline_marks_task_cancelled(
    config: AppConfig, tmp_path: Path
) -> None:
    store = TaskStore(config.paths.db_file)
    cancel_event = threading.Event()
    cancel_event.set()
    pipeline = AnalysisPipeline(config, store, cancel_event=cancel_event)

    with pytest.raises(PipelineCancelled):
        pipeline.run([build_materials(tmp_path)], mode="auto")

    records = store.list(1)
    assert records
    assert records[0].status == TaskStatus.CANCELLED
    assert "取消" in records[0].error
    assert store.get_result(records[0].id) is None


def test_unknown_mode_is_rejected(config: AppConfig) -> None:
    store = TaskStore(config.paths.db_file)
    pipeline = AnalysisPipeline(config, store)
    with pytest.raises(PipelineError, match="未知分析模式"):
        pipeline.run([], mode="unknown")
