from __future__ import annotations

import re
from pathlib import Path

CATEGORY_LABELS = {
    "crypto": "Crypto",
    "web": "Web",
    "forensics": "Forensics",
    "reverse": "Reverse",
    "pwn": "Pwn",
    "misc": "Misc",
}

CATEGORY_LABELS_CN = {
    "crypto": "Crypto",
    "web": "Web",
    "forensics": "取证",
    "reverse": "逆向",
    "pwn": "Pwn",
    "misc": "综合",
}

WEB_EXTENSIONS = {
    ".php",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".html",
    ".htm",
    ".jsp",
    ".asp",
    ".aspx",
    ".vue",
}
CODE_EXTENSIONS = {
    ".py",
    ".php",
    ".js",
    ".ts",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".pl",
    ".sh",
    ".ps1",
    ".html",
    ".sql",
}
CRYPTO_EXTENSIONS = {".pem", ".key", ".crt", ".enc", ".cipher", ".b64", ".hex"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
TRAFFIC_EXTENSIONS = {".pcap", ".pcapng", ".cap", ".evtx", ".raw", ".mem"}

WEB_PATTERNS = re.compile(
    r"(?i)(<\?php|\$_GET|\$_POST|mysqli?_|pdo|eval\s*\(|assert\s*\(|"
    r"include\s*\(|require\s*\(|shell_exec|passthru|proc_open|"
    r"document\.cookie|innerHTML|dangerouslySetInnerHTML|SELECT\s+.+\s+FROM|"
    r"express\(|flask|django|wp-config)"
)
CRYPTO_PATTERNS = re.compile(
    r"(?i)(base64|base32|base85|rot13|xor|rsa|aes|des|md5|sha(?:1|256|512)|"
    r"cipher|encrypt|decrypt|public\s+key|private\s+key|-----BEGIN|"
    r"\bpow\s*\(|\bn\s*=\s*0x|\be\s*=\s*0x|modinv|离散对数|栅栏|凯撒|维吉尼亚)"
)
PWN_PATTERNS = re.compile(
    r"(?i)(gets\s*\(|strcpy\s*\(|sprintf\s*\(|system\s*\(|/bin/sh|canary|"
    r"checksec|seccomp|stack\s+overflow|ret2|libc|pwntools|gets|vuln\s*\()"
)
REVERSE_PATTERNS = re.compile(
    r"(?i)(upx|ida|ghidra|ollydbg|x64dbg|逆向|serial|license|注册码|"
    r"mprotect|ptrace|anti[-_ ]?debug|keygen)"
)


def guess_category(path: Path, kind: str, sample: str = "") -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    scores = {"crypto": 0, "web": 0, "forensics": 0, "reverse": 0, "pwn": 0, "misc": 1}
    excerpt = sample[:12000]

    if kind == "elf":
        scores["pwn"] += 4
        scores["reverse"] += 4
    if kind == "pe":
        scores["reverse"] += 5
    if kind in {"pcap", "pcapng", "sqlite", "ole"}:
        scores["forensics"] += 5
    if kind in {"png", "jpeg", "gif", "bmp", "webp", "tiff", "pdf"}:
        scores["forensics"] += 3
        scores["misc"] += 1
    if kind in {"zip", "7z", "rar", "gzip", "tar", "bzip2", "xz"}:
        scores["forensics"] += 2
        scores["misc"] += 2
    if suffix in CRYPTO_EXTENSIONS:
        scores["crypto"] += 5
    if suffix in WEB_EXTENSIONS:
        scores["web"] += 3
    if suffix in CODE_EXTENSIONS:
        scores["web"] += 1
    if any(token in name for token in ("crypto", "cipher", "enc", "rsa", "base64", "rot")):
        scores["crypto"] += 4
    if any(token in name for token in ("web", "php", "source", "src", "www", "app")):
        scores["web"] += 2
    if any(token in name for token in ("pcap", "forensic", "disk", "memory", "dump")):
        scores["forensics"] += 5
    if any(token in name for token in ("pwn", "exploit", "vuln")):
        scores["pwn"] += 4
    if any(token in name for token in ("rev", "crackme", "keygen", "reverse")):
        scores["reverse"] += 4
    if suffix in TRAFFIC_EXTENSIONS:
        scores["forensics"] += 5
    if excerpt:
        if CRYPTO_PATTERNS.search(excerpt):
            scores["crypto"] += 3
        if WEB_PATTERNS.search(excerpt):
            scores["web"] += 3
        if PWN_PATTERNS.search(excerpt):
            scores["pwn"] += 2
            scores["reverse"] += 1
        if REVERSE_PATTERNS.search(excerpt):
            scores["reverse"] += 2
    if kind in {"text", "source", "python", "javascript", "php", "html", "json", "yaml"}:
        scores["misc"] += 1

    category, score = max(scores.items(), key=lambda item: item[1])
    if score <= 1:
        return "misc"
    return category


def aggregate_category(categories: list[str]) -> str:
    if not categories:
        return "misc"
    priority = ("pwn", "reverse", "crypto", "web", "forensics", "misc")
    counts = {category: categories.count(category) for category in set(categories)}
    return max(counts, key=lambda category: (counts[category], -priority.index(category)))
