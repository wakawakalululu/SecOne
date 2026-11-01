from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..config import AppConfig
from ..domain import AnalysisResult, FlagStatus, Severity
from ..paths import AppPaths
from .fileio import format_size, kind_label
from .workspace import TaskWorkspace

FLAG_LABELS = {
    FlagStatus.VERIFIED: "已验证",
    FlagStatus.FOUND: "已发现",
    FlagStatus.CANDIDATE: "候选",
    FlagStatus.NONE: "未发现",
}
SEVERITY_LABELS = {
    Severity.CRITICAL: "严重",
    Severity.HIGH: "高危",
    Severity.MEDIUM: "中危",
    Severity.LOW: "低危",
    Severity.INFO: "信息",
}
MODE_LABELS = {
    "auto": "一键梭哈",
    "crypto": "Crypto 分析",
    "forensics": "文件取证",
    "web": "代码审计",
    "binary": "二进制静态分析",
}


class ReportWriter:
    def __init__(self, config: AppConfig, paths: AppPaths):
        self.config = config
        self.paths = paths

    def write(self, result: AnalysisResult) -> dict[str, str]:
        workspace = TaskWorkspace.open(Path(result.workspace))
        workspace.ensure()
        report_dir = workspace.report
        report_dir.mkdir(parents=True, exist_ok=True)

        json_path = report_dir / "report.json"
        md_path = report_dir / "report.md"
        txt_path = report_dir / "report.txt"
        summary_path = self.paths.output / f"{result.task_id}_summary.txt"
        summary_path.parent.mkdir(parents=True, exist_ok=True)

        result.report_paths = {
            "json": str(json_path),
            "markdown": str(md_path),
            "text": str(txt_path),
            "summary": str(summary_path),
        }
        json_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        markdown = self._markdown(result)
        md_path.write_text(markdown, encoding="utf-8")
        text = self._plain_text(result)
        txt_path.write_text(text, encoding="utf-8")
        summary_path.write_text(
            self._summary(result), encoding="utf-8"
        )
        workspace.flags.joinpath("candidates.json").write_text(
            json.dumps(
                [candidate.to_dict() for candidate in result.flags],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        workspace.evidence.joinpath("index.json").write_text(
            json.dumps(
                {
                    "task_id": result.task_id,
                    "flags": [candidate.to_dict() for candidate in result.flags],
                    "findings": [finding.to_dict() for finding in result.findings],
                    "files": [artifact.to_dict() for artifact in result.files],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        workspace.write_json("result.json", result.to_dict())
        return result.report_paths

    def _markdown(self, result: AnalysisResult) -> str:
        lines: list[str] = [
            f"# SecOne 安全分析报告 · {result.task_id}",
            "",
            f"> 产品：SecOne · 本地 AI 安全分析工作台  ",
            f"> 引擎：{result.engine or self.config.get('engine.display_name', 'SecOne 本地引擎')}  ",
            f"> 模式：{MODE_LABELS.get(result.mode, result.mode)}  ",
            f"> 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}  ",
            f"> 任务耗时：{result.duration_seconds:.2f} 秒",
            "",
            "## 结论摘要",
            "",
            result.summary or "无摘要。",
            "",
            "## Flag 候选",
            "",
        ]
        if result.flags:
            lines.extend(
                [
                    "| 状态 | 置信度 | 候选值 | 来源 | 方法 |",
                    "| --- | ---: | --- | --- | --- |",
                ]
            )
            for flag in result.flags:
                lines.append(
                    f"| {FLAG_LABELS.get(flag.status, flag.status)} "
                    f"| {flag.confidence:.0%} "
                    f"| `{self._escape_inline(flag.value)}` "
                    f"| `{self._escape_inline(flag.source)}` "
                    f"| {self._escape_inline(flag.method)} |"
                )
            lines.append("")
            lines.append("### 候选详情")
            lines.append("")
            for flag in result.flags:
                lines.append(
                    f"- **{flag.value}** · {FLAG_LABELS.get(flag.status, flag.status)} · "
                    f"{flag.confidence:.0%}"
                )
                lines.append(f"  - 来源：`{flag.source}`")
                if flag.offset is not None:
                    lines.append(f"  - 偏移：{flag.offset}")
                lines.append(f"  - 方法：{flag.method}")
                if flag.evidence:
                    lines.append(f"  - 证据：{flag.evidence}")
                if flag.ai_generated:
                    lines.append("  - 标记：AI 线索，已回查材料原文，尚未人工验证")
                lines.append("")
        else:
            lines.extend(["当前材料未发现符合规则的 Flag。", ""])

        lines.extend(["## 静态发现", ""])
        if result.findings:
            severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
            for severity in severity_order:
                group = [item for item in result.findings if item.severity == severity]
                if not group:
                    continue
                lines.append(f"### {SEVERITY_LABELS.get(severity, severity)}")
                lines.append("")
                for finding in group:
                    location = finding.path or "全局"
                    if finding.line:
                        location += f":{finding.line}"
                    lines.append(f"- **{finding.title}** · `{location}`")
                    if finding.description:
                        lines.append(f"  - {finding.description}")
                    if finding.evidence:
                        lines.append(
                            f"  - 证据：`{self._escape_inline(finding.evidence[:500])}`"
                        )
                    if finding.rule_id:
                        lines.append(f"  - 规则：`{finding.rule_id}`")
                lines.append("")
        else:
            lines.extend(["未发现需要记录的静态问题。", ""])

        lines.extend(["## 材料清单", "", "| 文件 | 类型 | 分类 | 大小 | SHA256 |", "| --- | --- | --- | ---: | --- |"])
        for artifact in result.files:
            lines.append(
                f"| `{self._escape_inline(artifact.path)}` "
                f"| {kind_label(artifact.kind)} "
                f"| {artifact.category} "
                f"| {format_size(artifact.size)} "
                f"| `{artifact.sha256[:16]}…` |"
            )
        lines.extend(["", "## AI 分析", ""])
        if result.ai_used and result.ai_text:
            lines.extend([result.ai_text, ""])
        elif result.ai_error:
            lines.extend([f"AI 分析未执行：{result.ai_error}", ""])
        else:
            lines.extend(["AI 分析未启用。", ""])

        if result.warnings:
            lines.extend(["## 运行提示", ""])
            for warning in result.warnings:
                lines.append(f"- {warning}")
            lines.append("")

        lines.extend(
            [
                "## 方法与边界",
                "",
                "- 所有分析均在本机离线完成；静态工具不执行用户提供的二进制。",
                "- Flag 为“候选”时表示来自解码、AI 线索或弱验证路径，仍需人工确认。",
                "- AI 输出经过原文回查；未在材料中出现的 flag 会被丢弃。",
                "- 本报告仅用于用户主动提供的 CTF 题目或获授权材料。",
                "",
            ]
        )
        return "\n".join(lines)

    def _plain_text(self, result: AnalysisResult) -> str:
        lines = [
            "SecOne 安全分析报告",
            "=" * 52,
            f"任务 ID：{result.task_id}",
            f"任务名称：{result.title}",
            f"模式：{MODE_LABELS.get(result.mode, result.mode)}",
            f"开始时间：{result.created_at}",
            f"完成时间：{result.completed_at}",
            f"耗时：{result.duration_seconds:.2f} 秒",
            f"模型：{result.engine or '未使用'}",
            "",
            "【结论摘要】",
            result.summary or "无摘要。",
            "",
            "【Flag 候选】",
        ]
        if result.flags:
            for flag in result.flags:
                lines.extend(
                    [
                        f"- {flag.value}",
                        f"  状态: {FLAG_LABELS.get(flag.status, flag.status)}",
                        f"  置信度: {flag.confidence:.0%}",
                        f"  来源: {flag.source}",
                        f"  方法: {flag.method}",
                        f"  证据: {flag.evidence}",
                    ]
                )
        else:
            lines.append("未发现符合规则的 Flag。")
        lines.extend(["", "【静态发现】"])
        if result.findings:
            for finding in result.findings:
                location = finding.path + (f":{finding.line}" if finding.line else "")
                lines.append(
                    f"[{SEVERITY_LABELS.get(finding.severity, finding.severity)}] "
                    f"{finding.title} @ {location}"
                )
                lines.append(f"  {finding.description}")
                if finding.evidence:
                    lines.append(f"  证据: {finding.evidence[:500]}")
        else:
            lines.append("无。")
        lines.extend(["", "【AI 分析】", result.ai_text if result.ai_used else (result.ai_error or "未启用")])
        if result.warnings:
            lines.extend(["", "【运行提示】"])
            lines.extend(f"- {warning}" for warning in result.warnings)
        lines.extend(
            [
                "",
                "【边界声明】",
                "本报告由 SecOne 在本机离线生成，仅用于获授权材料。",
                "候选 Flag 需要人工确认；AI 不会执行模型生成的命令。",
            ]
        )
        return "\n".join(lines)

    def _summary(self, result: AnalysisResult) -> str:
        confirmed = len(result.confirmed_flags)
        candidates = len(result.candidates)
        high = sum(
            1
            for finding in result.findings
            if finding.severity in (Severity.CRITICAL, Severity.HIGH)
        )
        flag_part = "未发现可靠 Flag" if not result.flags else (
            f"{confirmed} 个已发现 Flag、{candidates} 个候选"
        )
        ai_part = "AI 已完成分析" if result.ai_used else "AI 未参与"
        return (
            f"{result.task_id} · {result.title}\n"
            f"模式：{MODE_LABELS.get(result.mode, result.mode)}\n"
            f"文件：{len(result.files)} · 发现：{len(result.findings)}（高危 {high}）\n"
            f"Flag：{flag_part}\n"
            f"AI：{ai_part}\n"
            f"{result.summary}\n"
        )

    @staticmethod
    def _escape_inline(value: str) -> str:
        return value.replace("|", "\\|").replace("`", "\\`").replace("\n", " ")
