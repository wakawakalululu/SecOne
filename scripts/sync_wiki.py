"""把 docs/wiki/ 同步到 GitHub Wiki 仓库。

docs/wiki/ 是唯一事实来源（随主仓库版本化）。本脚本把其中的页面复制到
Wiki 工作目录（默认仓库旁的 SecOne-wiki/），把页内相对链接转换回
GitHub Wiki 的 [[页面|标签]] 语法，重新生成 _Sidebar.md，并可选拉起
git 提交与推送。

用法：
    python scripts/sync_wiki.py [--repo-root PATH] [--wiki-dir PATH]
                                [--push] [--dry-run] [--message TEXT]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]
WIKI_DIR_DEFAULT = REPO_ROOT_DEFAULT.parent / "SecOne-wiki"

# [label](target.md) 仅当 target 是同目录相对 Markdown 链接时转换；
# 外链、图片（raw.githubusercontent.com）与子目录链接保持原样。
_MD_LINK = re.compile(r"(?<!\!)\[([^\[\]]+)\]\(([^)\s]+\.md)\)")
_SIDEBAR_ORDER = ["Home"]


def wiki_link(label: str, target: str) -> str:
    page = target[: -len(".md")]
    if label == page:
        return f"[[{page}]]"
    return f"[[{page}|{label}]]"


def convert_links(text: str) -> str:
    return _MD_LINK.sub(
        lambda m: wiki_link(m.group(1), m.group(2)) if "/" not in m.group(2) else m.group(0),
        text,
    )


def page_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def build_sidebar(pages: list[Path]) -> str:
    names = [p.stem for p in pages]
    ordered = [n for n in _SIDEBAR_ORDER if n in names] + sorted(
        n for n in names if n not in _SIDEBAR_ORDER
    )
    titles = {p.stem: page_title(p) for p in pages}
    lines = ["**SecOne Wiki**", ""]
    lines += [f"- [[{n}|{titles[n]}]]" for n in ordered]
    lines += [
        "",
        "**链接**",
        "",
        "- [仓库主页](https://github.com/wakawakalululu/SecOne)",
        "- [文档中心镜像（docs/wiki）](https://github.com/wakawakalululu/SecOne/tree/main/docs/wiki)",
        "- [发布说明](https://github.com/wakawakalululu/SecOne/blob/main/docs/RELEASE_NOTES.md)",
        "",
    ]
    return "\n".join(lines)


def run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {result.stderr.strip()}")
    return result.stdout.strip()


def sync(repo_root: Path, wiki_dir: Path, dry_run: bool = False) -> list[str]:
    docs = repo_root / "docs" / "wiki"
    if not docs.is_dir():
        raise SystemExit(f"缺少文档中心目录: {docs}")
    changed: list[str] = []
    pages = sorted(docs.glob("*.md"))
    plan: dict[Path, str] = {}
    for page in pages:
        plan[wiki_dir / page.name] = convert_links(page.read_text(encoding="utf-8"))
    plan[wiki_dir / "_Sidebar.md"] = build_sidebar(pages)

    for target, content in plan.items():
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.read_text(encoding="utf-8") == content:
            continue
        changed.append(target.name)
        if not dry_run:
            target.write_text(content, encoding="utf-8", newline="\n")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT_DEFAULT)
    parser.add_argument("--wiki-dir", type=Path, default=WIKI_DIR_DEFAULT)
    parser.add_argument("--push", action="store_true", help="提交并推送到 origin master")
    parser.add_argument("--dry-run", action="store_true", help="只报告将变更的文件")
    parser.add_argument("--message", default="docs: sync from docs/wiki")
    args = parser.parse_args(argv)

    wiki_dir = args.wiki_dir
    if not args.dry_run:
        if not (wiki_dir / ".git").is_dir():
            raise SystemExit(
                f"Wiki 工作目录不存在或未初始化: {wiki_dir}（先 git clone 仓库的 wiki.git）"
            )
        if wiki_dir.resolve() == args.repo_root.resolve():
            raise SystemExit("Wiki 工作目录不能是主仓库本身")

    changed = sync(args.repo_root, wiki_dir, dry_run=args.dry_run)
    if not changed:
        print("docs/wiki 与 Wiki 工作目录一致，无需变更。")
        return 0
    print("已变更:", ", ".join(changed))
    if args.dry_run:
        return 0

    run_git(["add", "-A"], wiki_dir)
    status = run_git(["status", "--porcelain"], wiki_dir)
    if status:
        run_git(["commit", "-m", args.message], wiki_dir)
        print("已提交:", args.message)
    if args.push:
        run_git(["push", "origin", "HEAD:master"], wiki_dir)
        print("已推送 origin master。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
