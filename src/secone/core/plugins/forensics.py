from __future__ import annotations

import sqlite3
import struct
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ...domain import Severity
from ..fileio import entropy, format_size, kind_label, mime_type
from .base import ARCHIVE_KINDS, IMAGE_KINDS, AnalysisContext, AnalysisPlugin


class ForensicsPlugin(AnalysisPlugin):
    name = "forensics"
    label = "文件取证"
    description = "分析文件指纹、图片元数据、压缩包、数据库与流量包结构。"

    def run(self, context: AnalysisContext, mode: str) -> None:
        files = context.files(exclude_kinds={"empty"})
        total = max(len(files), 1)
        for index, artifact in enumerate(files):
            context.report_progress(
                34 + int(16 * index / total),
                f"取证检查：{artifact.path.rsplit('/', 1)[-1]}",
            )
            path = context.path_of(artifact)
            data = context.bytes_for(artifact, limit=4 * 1024 * 1024)
            if artifact.kind in IMAGE_KINDS:
                self._image_metadata(context, artifact, path)
            elif artifact.kind in {"pcap", "pcapng"}:
                self._traffic_header(context, artifact, data)
            elif artifact.kind == "sqlite":
                self._sqlite_info(context, artifact, path)
            elif artifact.kind == "pdf":
                self._pdf_metadata(context, artifact, path)
            if artifact.kind in ARCHIVE_KINDS:
                self._archive_info(context, artifact, path)
            if artifact.size >= 1024 * 1024 and data:
                value = entropy(data)
                if value >= 7.25 and artifact.kind not in IMAGE_KINDS:
                    context.add_finding(
                        title="高熵内容，疑似压缩或加密",
                        category="forensics",
                        severity=Severity.INFO,
                        description=f"文件熵为 {value:.2f}/8.0，可能存在加密、压缩或封装数据。",
                        evidence=f"{artifact.path} · {format_size(artifact.size)}",
                        artifact=artifact,
                        rule_id="forensics.high_entropy",
                    )
            mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
            if artifact.kind in {"pcap", "pcapng", "sqlite", "pdf"} or artifact.kind in IMAGE_KINDS:
                context.add_finding(
                    title="文件基础取证信息",
                    category="forensics",
                    severity=Severity.INFO,
                    description=(
                        f"类型 {kind_label(artifact.kind)}，MIME {mime_type(path)}，"
                        f"大小 {format_size(artifact.size)}，修改时间 {mtime}。"
                    ),
                    evidence=f"SHA256 {artifact.sha256}",
                    artifact=artifact,
                    rule_id="forensics.file_metadata",
                )

    def _image_metadata(self, context: AnalysisContext, artifact, path: Path) -> None:
        try:
            from PIL import Image, ExifTags

            with Image.open(path) as image:
                width, height = image.size
                details = [f"{image.format} {width}x{height} {image.mode}"]
                exif = image.getexif()
                interesting = {
                    "Artist",
                    "Software",
                    "DateTime",
                    "DateTimeOriginal",
                    "ImageDescription",
                    "Make",
                    "Model",
                    "XPComment",
                    "XPSubject",
                    "UserComment",
                    "Copyright",
                }
                exif_lines = []
                for tag_id, value in list(exif.items())[:80]:
                    tag = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if tag not in interesting or value in (None, ""):
                        continue
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", "replace").strip("\x00")
                    text = str(value)[:220]
                    if text:
                        exif_lines.append(f"{tag}: {text}")
                context.add_finding(
                    title="图片结构与 EXIF 元数据",
                    category="forensics",
                    severity=Severity.INFO,
                    description="；".join(details),
                    evidence="\n".join(exif_lines[:12]) or "未发现常用 EXIF 字段",
                    artifact=artifact,
                    rule_id="forensics.image_metadata",
                )
                context.analyze_bytes(context.bytes_for(artifact), artifact)
        except Exception as exc:
            context.add_warning(f"图片元数据解析失败：{artifact.path}（{exc}）")

    def _traffic_header(self, context: AnalysisContext, artifact, data: bytes) -> None:
        if len(data) < 24:
            return
        magic = data[:4]
        if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
            endian = "<"
        elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
            endian = ">"
        else:
            context.add_finding(
                title="PCAPNG 流量包",
                category="forensics",
                severity=Severity.INFO,
                description="检测到 PCAPNG 容器。第一版仅做结构识别与字符串检查。",
                evidence=artifact.path,
                artifact=artifact,
                rule_id="forensics.pcapng",
            )
            return
        try:
            _magic, major, minor, _zone, _sig, snaplen, network = struct.unpack(
                endian + "IHHiiii", data[:24]
            )
            context.add_finding(
                title="PCAP 流量包结构",
                category="forensics",
                severity=Severity.INFO,
                description=(
                    f"版本 {major}.{minor}，快照长度 {snaplen}，"
                    f"链路类型 {network}（{self._link_type(network)}）。"
                ),
                evidence="第一版不自动重组会话；可继续检查 HTTP、DNS、TCP 流与导出对象。",
                artifact=artifact,
                rule_id="forensics.pcap",
            )
        except struct.error:
            context.add_warning(f"PCAP 头部解析失败：{artifact.path}")

    @staticmethod
    def _link_type(value: int) -> str:
        return {0: "NULL", 1: "Ethernet", 101: "Raw IP", 105: "802.11", 113: "Linux SLL"}.get(
            value, "未知"
        )

    def _sqlite_info(self, context: AnalysisContext, artifact, path: Path) -> None:
        try:
            uri = f"file:{quote(path.as_posix())}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=5)
            try:
                cursor = connection.execute(
                    "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') "
                    "ORDER BY name LIMIT 40"
                )
                rows = cursor.fetchall()
            finally:
                connection.close()
            names = [f"{name} ({kind})" for name, kind in rows]
            context.add_finding(
                title="SQLite 数据库结构",
                category="forensics",
                severity=Severity.INFO,
                description=f"发现 {len(names)} 个表或视图。",
                evidence=", ".join(names[:30]) or "未发现用户表",
                artifact=artifact,
                rule_id="forensics.sqlite",
            )
        except Exception as exc:
            context.add_warning(f"SQLite 解析失败：{artifact.path}（{exc}）")

    def _pdf_metadata(self, context: AnalysisContext, artifact, path: Path) -> None:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            info = reader.metadata or {}
            lines = []
            for key in ("/Author", "/Creator", "/Producer", "/Title", "/Subject", "/CreationDate"):
                value = info.get(key)
                if value:
                    lines.append(f"{key}: {str(value)[:200]}")
            context.add_finding(
                title="PDF 文档元数据",
                category="forensics",
                severity=Severity.INFO,
                description=f"页数 {len(reader.pages)}，已提取文本用于 Flag 检查。",
                evidence="\n".join(lines) or "未发现显著文档元数据",
                artifact=artifact,
                rule_id="forensics.pdf",
            )
        except Exception as exc:
            context.add_warning(f"PDF 元数据解析失败：{artifact.path}（{exc}）")

    def _archive_info(self, context: AnalysisContext, artifact, path: Path) -> None:
        if artifact.kind == "zip":
            try:
                with zipfile.ZipFile(path) as archive:
                    entries = archive.infolist()
                    names = [entry.filename for entry in entries[:40] if not entry.is_dir()]
                    context.add_finding(
                        title="ZIP 压缩包内容",
                        category="forensics",
                        severity=Severity.INFO,
                        description=f"共 {len(entries)} 个条目，已按安全限制递归展开。",
                        evidence="\n".join(names) or "空压缩包",
                        artifact=artifact,
                        rule_id="forensics.archive.zip",
                    )
            except Exception as exc:
                context.add_warning(f"ZIP 目录读取失败：{artifact.path}（{exc}）")
        elif artifact.kind == "7z":
            try:
                import py7zr

                with py7zr.SevenZipFile(path, "r") as archive:
                    names = archive.getnames()
                context.add_finding(
                    title="7z 压缩包内容",
                    category="forensics",
                    severity=Severity.INFO,
                    description=f"共 {len(names)} 个条目。",
                    evidence="\n".join(names[:40]),
                    artifact=artifact,
                    rule_id="forensics.archive.7z",
                )
            except Exception as exc:
                context.add_warning(f"7z 目录读取失败：{artifact.path}（{exc}）")
