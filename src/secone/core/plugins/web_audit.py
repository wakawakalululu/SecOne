from __future__ import annotations

import re
from dataclasses import dataclass

from ...domain import Severity
from .base import AnalysisContext, AnalysisPlugin


@dataclass(frozen=True)
class Rule:
    rule_id: str
    title: str
    severity: str
    pattern: re.Pattern[str]
    description: str


RULES = [
    Rule(
        "web.command_exec",
        "危险命令执行函数",
        Severity.HIGH,
        re.compile(r"(?i)\b(system|exec|shell_exec|passthru|popen|proc_open)\s*\("),
        "代码包含命令执行入口，应确认参数是否来自用户输入。",
    ),
    Rule(
        "web.eval",
        "动态代码执行",
        Severity.HIGH,
        re.compile(r"(?i)\b(eval|assert|create_function)\s*\("),
        "动态执行字符串代码容易引入任意代码执行风险。",
    ),
    Rule(
        "web.include",
        "变量文件包含",
        Severity.HIGH,
        re.compile(r"(?i)\b(include|require)(_once)?\s*\(\s*\$"),
        "文件包含路径来自变量，需检查路径穿越与远程包含。",
    ),
    Rule(
        "web.sql_concat",
        "疑似拼接 SQL 查询",
        Severity.HIGH,
        re.compile(
            r"(?i)(SELECT|INSERT|UPDATE|DELETE)\b[^;\n]{0,180}"
            r"(\+\s*[\"']?\s*\$|\.format\s*\(|%\s*\(|f[\"'])"
        ),
        "SQL 语句由字符串拼接构造，检查是否使用参数化查询。",
    ),
    Rule(
        "web.deserialize",
        "不安全反序列化",
        Severity.HIGH,
        re.compile(
            r"(?i)(pickle\.loads|yaml\.load\s*\(|unserialize\s*\(|ObjectInputStream|readObject\s*\()"
        ),
        "反序列化不可信数据可能导致远程代码执行。",
    ),
    Rule(
        "web.php_extract",
        "请求变量批量注册",
        Severity.HIGH,
        re.compile(r"(?i)\b(extract|parse_str)\s*\(\s*\$_(GET|POST|REQUEST|COOKIE)"),
        "将请求参数批量导入作用域会覆盖关键变量。",
    ),
    Rule(
        "web.tls_verify",
        "TLS 证书校验被关闭",
        Severity.HIGH,
        re.compile(
            r"(?i)(verify\s*=\s*False|rejectUnauthorized\s*:\s*false|"
            r"CURLOPT_SSL_VERIFYPEER\s*,\s*0)"
        ),
        "关闭证书校验会暴露中间人攻击风险。",
    ),
    Rule(
        "web.hardcoded_secret",
        "疑似硬编码凭据",
        Severity.MEDIUM,
        re.compile(
            r"(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|"
            r"private[_-]?key)\s*[:=]\s*[\"'][^\"'\s]{6,}"
        ),
        "源码中出现硬编码凭据，应迁移到安全的密钥管理系统。",
    ),
    Rule(
        "web.file_upload",
        "文件上传处理",
        Severity.MEDIUM,
        re.compile(r"(?i)move_uploaded_file\s*\("),
        "检查上传文件的扩展名、MIME 类型、保存路径与执行权限。",
    ),
    Rule(
        "web.xss_sink",
        "前端 HTML 注入点",
        Severity.MEDIUM,
        re.compile(
            r"(?i)(innerHTML\s*=|document\.write\s*\(|dangerouslySetInnerHTML)"
        ),
        "未转义内容写入 HTML 上下文可能导致 XSS。",
    ),
    Rule(
        "web.path_traversal",
        "可疑文件路径输入",
        Severity.MEDIUM,
        re.compile(
            r"(?i)(open|readFile|file_get_contents|send_file)\s*\(\s*(\$|request|req\.)"
        ),
        "文件路径可能受用户控制，检查规范化与目录边界限制。",
    ),
    Rule(
        "web.ssrf",
        "可疑服务端请求",
        Severity.MEDIUM,
        re.compile(
            r"(?i)(requests\.(get|post)\s*\(\s*(request|req)|"
            r"\$\.(get|ajax)\s*\(\s*(location|url))"
        ),
        "请求目标可能来自用户输入，检查 URL 白名单与内网地址限制。",
    ),
    Rule(
        "web.debug",
        "调试模式开启",
        Severity.MEDIUM,
        re.compile(r"(?i)(debug\s*[:=]\s*true|app\.run\([^)]*debug\s*=\s*True)"),
        "生产环境开启调试会泄露堆栈、源码或调试控制台。",
    ),
    Rule(
        "web.cors_wildcard",
        "CORS 允许任意来源",
        Severity.LOW,
        re.compile(r"(?i)Access-Control-Allow-Origin\s*[:=]\s*[\"']?\*"),
        "通配 CORS 策略会扩大跨域数据访问面。",
    ),
    Rule(
        "web.weak_hash",
        "弱哈希算法",
        Severity.LOW,
        re.compile(r"(?i)\b(md5|sha1)\s*\("),
        "MD5/SHA1 不适合密码或完整性校验场景。",
    ),
]

CODE_KINDS = {
    "text",
    "python",
    "javascript",
    "php",
    "source",
    "html",
    "json",
    "yaml",
}


class WebAuditPlugin(AnalysisPlugin):
    name = "web"
    label = "代码审计"
    description = "扫描源码中的危险函数、注入点、反序列化与配置风险。"

    def run(self, context: AnalysisContext, mode: str) -> None:
        files = [item for item in context.files() if item.kind in CODE_KINDS]
        if not files:
            context.add_warning("未发现可审计的文本源码；请拖入源码文件或压缩包。")
            return
        total = max(len(files), 1)
        for index, artifact in enumerate(files):
            context.report_progress(
                34 + int(20 * index / total),
                f"代码审计：{artifact.path.rsplit('/', 1)[-1]}",
            )
            text = context.text_for(artifact)
            if not text:
                continue
            context.analyze_text(text, artifact)
            self._audit_lines(context, artifact, text)

    def _audit_lines(self, context: AnalysisContext, artifact, text: str) -> None:
        file_hits = 0
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            for rule in RULES:
                if not rule.pattern.search(line):
                    continue
                stripped = line.strip()
                context.add_finding(
                    title=rule.title,
                    category="web",
                    severity=rule.severity,
                    description=rule.description,
                    evidence=stripped[:260],
                    artifact=artifact,
                    line=line_number,
                    rule_id=rule.rule_id,
                )
                file_hits += 1
                if file_hits >= 80:
                    context.add_warning(
                        f"{artifact.path} 命中过多，已限制为 80 条结果。"
                    )
                    return
