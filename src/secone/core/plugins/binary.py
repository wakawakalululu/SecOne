from __future__ import annotations

import struct
from datetime import datetime, timezone

from ...domain import Severity
from ..fileio import entropy, format_size, kind_label
from .base import AnalysisContext, AnalysisPlugin

PE_MACHINES = {
    0x14C: "x86",
    0x8664: "x64",
    0x1C0: "ARM",
    0xAA64: "ARM64",
}
ELF_MACHINES = {
    3: "x86",
    8: "MIPS",
    20: "PowerPC",
    40: "ARM",
    62: "x86-64",
    183: "AArch64",
    243: "RISC-V",
}
ELF_TYPES = {
    0: "NONE",
    1: "REL",
    2: "EXEC",
    3: "DYN/PIE",
    4: "CORE",
}
INTERESTING_STRINGS = (
    "/bin/sh",
    "/bin/bash",
    "system",
    "gets",
    "mprotect",
    "ptrace",
    "LD_PRELOAD",
    "seccomp",
    "flag{",
    "UPX!",
    "http://",
    "https://",
)


class BinaryPlugin(AnalysisPlugin):
    name = "binary"
    label = "二进制静态分析"
    description = "解析 PE/ELF 结构、保护属性、熵与可疑字符串，不执行样本。"

    def run(self, context: AnalysisContext, mode: str) -> None:
        files = context.files(kinds={"elf", "pe"})
        if not files:
            if mode == "auto":
                return
            context.add_warning("未发现 PE/ELF 二进制样本。")
            return
        total = max(len(files), 1)
        for index, artifact in enumerate(files):
            context.report_progress(
                36 + int(14 * index / total),
                f"二进制静态检查：{artifact.path.rsplit('/', 1)[-1]}",
            )
            data = context.bytes_for(artifact, limit=16 * 1024 * 1024)
            if not data:
                continue
            if artifact.kind == "pe":
                self._parse_pe(context, artifact, data)
            elif artifact.kind == "elf":
                self._parse_elf(context, artifact, data)
            self._strings(context, artifact, data)
            context.analyze_bytes(data, artifact)
        context.add_warning("二进制模块仅做静态分析，未在主机上执行任何样本。")

    def _parse_pe(self, context: AnalysisContext, artifact, data: bytes) -> None:
        if len(data) < 0x40 or data[:2] != b"MZ":
            return
        try:
            pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
            if pe_offset + 24 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\x00\x00":
                return
            machine, sections, timestamp, _, _, optional_size, characteristics = (
                struct.unpack_from("<HHIIIHH", data, pe_offset + 4)
            )
            optional_offset = pe_offset + 24
            magic = (
                struct.unpack_from("<H", data, optional_offset)[0]
                if optional_offset + 2 <= len(data)
                else 0
            )
            bits = "PE32+" if magic == 0x20B else "PE32"
            section_offset = optional_offset + optional_size
            details: list[str] = [
                f"{bits} · {PE_MACHINES.get(machine, f'machine 0x{machine:X}')} · "
                f"{sections} 个节",
                f"文件大小 {format_size(len(data))} · 熵 {entropy(data):.2f}",
            ]
            if timestamp:
                stamp = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(
                    timespec="seconds"
                )
                details.append(f"链接时间戳 {stamp}")
            if characteristics & 0x2000:
                details.append("DLL")
            if characteristics & 0x0002:
                details.append("可执行映像")

            section_names: list[str] = []
            wx_sections: list[str] = []
            high_entropy: list[str] = []
            max_end = 0
            for index in range(min(sections, 64)):
                offset = section_offset + index * 40
                if offset + 40 > len(data):
                    break
                raw_name = data[offset : offset + 8].split(b"\x00", 1)[0]
                name = raw_name.decode("ascii", "replace") or f"section_{index}"
                raw_size, raw_pointer = struct.unpack_from("<II", data, offset + 16)
                flags = struct.unpack_from("<I", data, offset + 36)[0]
                section_names.append(name)
                end = raw_pointer + raw_size
                max_end = max(max_end, end)
                if (flags & 0x80000000) and (flags & 0x20000000):
                    wx_sections.append(name)
                if raw_size and raw_pointer < len(data):
                    section_data = data[raw_pointer : min(raw_pointer + raw_size, len(data))]
                    if len(section_data) >= 4096 and entropy(section_data) >= 7.25:
                        high_entropy.append(name)
                if name.upper().startswith("UPX"):
                    high_entropy.append(name)

            details.append("节: " + ", ".join(section_names[:20]))
            overlay = len(data) - max_end
            if overlay > 512:
                details.append(f"文件尾部附加数据约 {format_size(overlay)}")
            context.add_finding(
                title="PE 文件结构",
                category="reverse",
                severity=Severity.INFO,
                description="完成 PE 头、节表、熵与尾部数据静态解析。",
                evidence="\n".join(details),
                artifact=artifact,
                rule_id="binary.pe.structure",
            )
            if wx_sections:
                context.add_finding(
                    title="PE 存在可写可执行节",
                    category="reverse",
                    severity=Severity.MEDIUM,
                    description="W+X 节可能是解包、JIT 或自修改代码迹象。",
                    evidence=", ".join(wx_sections),
                    artifact=artifact,
                    rule_id="binary.pe.wx",
                )
            if high_entropy:
                context.add_finding(
                    title="PE 可能存在加壳或加密节",
                    category="reverse",
                    severity=Severity.INFO,
                    description="高熵节或 UPX 命名提示二进制可能被压缩/加壳。",
                    evidence=", ".join(dict.fromkeys(high_entropy)),
                    artifact=artifact,
                    rule_id="binary.pe.high_entropy",
                )
        except (struct.error, IndexError, ValueError) as exc:
            context.add_warning(f"PE 解析失败：{artifact.path}（{exc}）")

    def _parse_elf(self, context: AnalysisContext, artifact, data: bytes) -> None:
        if len(data) < 52 or not data.startswith(b"\x7fELF"):
            return
        try:
            elf_class = data[4]
            endian = "<" if data[5] == 1 else ">"
            is_64 = elf_class == 2
            e_type, e_machine = struct.unpack_from(endian + "HH", data, 16)
            if is_64:
                e_entry = struct.unpack_from(endian + "Q", data, 24)[0]
                e_phoff = struct.unpack_from(endian + "Q", data, 32)[0]
                e_phentsize = struct.unpack_from(endian + "H", data, 54)[0]
                e_phnum = struct.unpack_from(endian + "H", data, 56)[0]
            else:
                e_entry = struct.unpack_from(endian + "I", data, 24)[0]
                e_phoff = struct.unpack_from(endian + "I", data, 28)[0]
                e_phentsize = struct.unpack_from(endian + "H", data, 42)[0]
                e_phnum = struct.unpack_from(endian + "H", data, 44)[0]

            stack_flags: int | None = None
            has_relro = False
            load_segments = 0
            for index in range(min(e_phnum, 128)):
                offset = e_phoff + index * e_phentsize
                if offset + e_phentsize > len(data) or e_phentsize < 32:
                    break
                p_type = struct.unpack_from(endian + "I", data, offset)[0]
                if is_64:
                    p_flags = struct.unpack_from(endian + "I", data, offset + 4)[0]
                else:
                    p_flags = struct.unpack_from(endian + "I", data, offset + 24)[0]
                if p_type == 1:
                    load_segments += 1
                if p_type == 0x6474E551:
                    stack_flags = p_flags
                if p_type == 0x6474E552:
                    has_relro = True
            nx = "未知"
            if stack_flags is not None:
                nx = "关闭（栈可执行）" if stack_flags & 0x1 else "开启"
            protections = [
                f"PIE: {'是' if e_type == 3 else '否'}",
                f"NX: {nx}",
                f"RELRO: {'部分' if has_relro else '未检测到'}",
            ]
            details = [
                f"ELF{64 if is_64 else 32} · {ELF_MACHINES.get(e_machine, f'machine {e_machine}')} · "
                f"{ELF_TYPES.get(e_type, e_type)}",
                f"入口点 0x{e_entry:X} · 文件大小 {format_size(len(data))} · 熵 {entropy(data):.2f}",
                "保护属性: " + " · ".join(protections),
                f"PT_LOAD 段: {load_segments}",
            ]
            context.add_finding(
                title="ELF 文件结构与保护属性",
                category="pwn",
                severity=Severity.INFO,
                description="完成 ELF 头、程序头与基础保护属性静态检查。",
                evidence="\n".join(details),
                artifact=artifact,
                rule_id="binary.elf.structure",
            )
            if stack_flags is not None and stack_flags & 0x1:
                context.add_finding(
                    title="ELF 栈可执行（NX 关闭）",
                    category="pwn",
                    severity=Severity.HIGH,
                    description="GNU_STACK 标记为可执行，栈上代码注入风险升高。",
                    evidence="PT_GNU_STACK 包含 PF_X",
                    artifact=artifact,
                    rule_id="binary.elf.exec_stack",
                )
            if e_type != 3:
                context.add_finding(
                    title="ELF 未启用 PIE",
                    category="pwn",
                    severity=Severity.MEDIUM,
                    description="非 ET_DYN 映像的代码地址固定，降低利用门槛。",
                    evidence=f"e_type={e_type}",
                    artifact=artifact,
                    rule_id="binary.elf.no_pie",
                )
            if not has_relro:
                context.add_finding(
                    title="ELF 未检测到 RELRO",
                    category="pwn",
                    severity=Severity.LOW,
                    description="未发现 PT_GNU_RELRO，GOT 等结构可能更易被改写。",
                    evidence="程序头中缺少 PT_GNU_RELRO",
                    artifact=artifact,
                    rule_id="binary.elf.no_relro",
                )
        except (struct.error, IndexError, ValueError) as exc:
            context.add_warning(f"ELF 解析失败：{artifact.path}（{exc}）")

    def _strings(self, context: AnalysisContext, artifact, data: bytes) -> None:
        strings = context.strings_for(artifact, limit=1200)
        interesting: list[str] = []
        for _offset, text in strings:
            for token in INTERESTING_STRINGS:
                if token in text:
                    line = text[:220]
                    if line not in interesting:
                        interesting.append(line)
                    break
            if len(interesting) >= 24:
                break
        if interesting:
            context.add_finding(
                title="二进制中的高价值字符串",
                category="reverse",
                severity=Severity.INFO,
                description="字符串可能提示命令执行、网络访问、调试或打包行为。",
                evidence="\n".join(interesting),
                artifact=artifact,
                rule_id="binary.interesting_strings",
            )
        context.add_finding(
            title="二进制摘要",
            category="reverse",
            severity=Severity.INFO,
            description=f"{kind_label(artifact.kind)}，共提取 {len(strings)} 条可打印字符串。",
            evidence=f"SHA256 {artifact.sha256}",
            artifact=artifact,
            rule_id="binary.summary",
        )
