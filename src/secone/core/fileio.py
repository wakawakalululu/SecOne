from __future__ import annotations

import hashlib
import math
import mimetypes
import re
from pathlib import Path

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".php",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".pl",
    ".sh",
    ".ps1",
    ".bat",
    ".cmd",
    ".html",
    ".htm",
    ".css",
    ".xml",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".conf",
    ".cfg",
    ".env",
    ".log",
    ".sql",
    ".pem",
    ".key",
    ".crt",
    ".srt",
    ".csv",
}

ARCHIVE_EXTENSIONS = {
    ".zip",
    ".jar",
    ".apk",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".tbz2",
    ".xz",
    ".txz",
}

KIND_LABELS = {
    "text": "文本",
    "python": "Python 源码",
    "javascript": "JavaScript 源码",
    "php": "PHP 源码",
    "source": "源码",
    "html": "HTML",
    "json": "JSON",
    "yaml": "YAML",
    "pdf": "PDF 文档",
    "png": "PNG 图片",
    "jpeg": "JPEG 图片",
    "gif": "GIF 图片",
    "bmp": "BMP 图片",
    "webp": "WebP 图片",
    "tiff": "TIFF 图片",
    "zip": "ZIP 压缩包",
    "7z": "7z 压缩包",
    "rar": "RAR 压缩包",
    "gzip": "GZip 压缩包",
    "tar": "Tar 归档",
    "bzip2": "BZip2 压缩包",
    "xz": "XZ 压缩包",
    "elf": "ELF 二进制",
    "pe": "PE 二进制",
    "sqlite": "SQLite 数据库",
    "pcap": "PCAP 流量包",
    "pcapng": "PCAPNG 流量包",
    "wasm": "WebAssembly",
    "java_class": "Java Class",
    "ole": "OLE 文档",
    "binary": "二进制",
    "empty": "空文件",
}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def read_bytes(path: Path, limit: int = 8 * 1024 * 1024) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit)


def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    if b"\x00" in data[:4096]:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return True
        return False
    sample = data[:8192]
    printable = sum(
        1
        for byte in sample
        if byte in (9, 10, 13) or 32 <= byte <= 126 or byte >= 128
    )
    return printable / max(len(sample), 1) > 0.88


def detect_kind(data: bytes, path: Path | None = None) -> str:
    if not data:
        return "empty"
    if data.startswith(b"\x7fELF"):
        return "elf"
    if data.startswith(b"MZ"):
        return "pe"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "text"
    if b"\x00" in data[:4096]:
        if data.startswith(b"SQLite format 3\x00"):
            return "sqlite"
        if data.startswith(b"\x0a\x0d\x0d\x0a"):
            return "pcapng"
        if data[:4] in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1"):
            return "pcap"
        if data.startswith(b"\xca\xfe\xba\xbe"):
            return "java_class"
        if data.startswith(b"\x00asm"):
            return "wasm"
        if data.startswith(b"\xd0\xcf\x11\xe0"):
            return "ole"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "webp"
        return "binary"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
        return "zip"
    if data.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if data.startswith(b"Rar!\x1a\x07"):
        return "rar"
    if data.startswith(b"\x1f\x8b"):
        return "gzip"
    if data.startswith(b"BZh"):
        return "bzip2"
    if data.startswith(b"\xfd7zXZ\x00"):
        return "xz"
    if data.startswith(b"ustar"):
        return "tar"
    if is_probably_text(data):
        return _text_kind(path)
    return "binary"


def _text_kind(path: Path | None) -> str:
    if not path:
        return "text"
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
        return "javascript"
    if suffix == ".php":
        return "php"
    if suffix in {
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cs",
        ".java",
        ".go",
        ".rs",
        ".rb",
        ".pl",
        ".sh",
        ".ps1",
    }:
        return "source"
    if suffix in (".html", ".htm"):
        return "html"
    if suffix == ".json":
        return "json"
    if suffix in (".yaml", ".yml"):
        return "yaml"
    if suffix == ".pdf":
        return "pdf"
    return "text"


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind.upper())


def decode_bytes(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    for encoding in ("utf-8", "gb18030", "big5", "shift_jis", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_text(path: Path, kind: str, max_chars: int = 60000) -> str:
    try:
        if kind == "pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            parts: list[str] = []
            for page in reader.pages[:80]:
                parts.append(page.extract_text() or "")
                if sum(len(part) for part in parts) >= max_chars:
                    break
            return "\n".join(parts)[:max_chars]
        data = read_bytes(path, max_bytes_for_text(max_chars))
        if kind in {"png", "jpeg", "gif", "bmp", "webp", "tiff", "elf", "pe", "binary"}:
            return ""
        return decode_bytes(data)[:max_chars]
    except Exception:
        return ""


def max_bytes_for_text(max_chars: int) -> int:
    return min(max(max_chars * 8, 1_000_000), 32 * 1024 * 1024)


def printable_strings(
    data: bytes,
    min_length: int = 5,
    min_printable_ratio: float = 0.90,
    limit: int = 1200,
) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    pattern = re.compile(rb"[\x20-\x7e]{4,}")
    for match in pattern.finditer(data):
        raw = match.group()
        if len(raw) < min_length:
            continue
        if len(raw) / max(len(raw), 1) < min_printable_ratio:
            continue
        results.append((match.start(), raw.decode("ascii", errors="replace")))
        if len(results) >= limit:
            break
    if len(results) < limit:
        utf16 = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")
        for match in utf16.finditer(data):
            raw = match.group().decode("utf-16-le", errors="replace")
            results.append((match.start(), raw))
            if len(results) >= limit:
                break
    results.sort(key=lambda item: item[0])
    return results[:limit]


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for byte in data[:2 * 1024 * 1024]:
        counts[byte] += 1
    total = sum(counts)
    value = 0.0
    for count in counts:
        if count:
            probability = count / total
            value -= probability * math.log2(probability)
    return value


def mime_type(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
