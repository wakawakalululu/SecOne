from __future__ import annotations

from .base import ARCHIVE_KINDS, AnalysisContext, AnalysisPlugin


class MiscPlugin(AnalysisPlugin):
    name = "misc"
    label = "综合检查"
    description = "对所有材料执行 Flag 规则匹配、编码恢复与二进制字符串检查。"

    def run(self, context: AnalysisContext, mode: str) -> None:
        files = context.files(exclude_kinds=ARCHIVE_KINDS | {"empty"})
        total = max(len(files), 1)
        for index, artifact in enumerate(files):
            context.report_progress(
                52 + int(14 * index / total),
                f"Flag 扫描：{artifact.path.rsplit('/', 1)[-1]}",
            )
            text = context.text_for(artifact)
            if text:
                context.analyze_text(text, artifact)
            data = context.bytes_for(artifact, limit=6 * 1024 * 1024)
            if data:
                context.analyze_bytes(data, artifact, include_text=not text)
            elif not text:
                context.add_warning(f"无法读取内容：{artifact.path}")
        for warning in context.flag_engine.warnings:
            context.add_warning(warning)
