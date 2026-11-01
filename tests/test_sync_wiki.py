from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sync_wiki", ROOT / "scripts" / "sync_wiki.py")
assert SPEC and SPEC.loader
sync_wiki = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync_wiki
SPEC.loader.exec_module(sync_wiki)


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=path, check=True)


def make_docs(root: Path) -> Path:
    docs = root / "docs" / "wiki"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "Home.md").write_text(
        "# SecOne 首页\n\n参见 [[安装与部署]] 与 [使用指南](使用指南.md)。\n",
        encoding="utf-8",
    )
    (docs / "安装与部署.md").write_text(
        "# 安装与部署\n\n返回 [首页](Home.md)；外链 [GitHub](https://github.com/x/y) 保留；"
        "子目录 [子页](sub/page.md) 不转换；图片 ![p](https://img.example/a.png) 不受影响。\n",
        encoding="utf-8",
    )
    return docs


def test_convert_links_only_relative_same_dir() -> None:
    text = (
        "[首页](Home.md) [带标签](安装与部署.md) [外链](https://a.example/b.md) "
        "[子目录](sub/page.md) ![图](https://img.example/a.png) [[已有]] 保留"
    )
    converted = sync_wiki.convert_links(text)
    assert "[[Home|首页]]" in converted
    assert "[[安装与部署|带标签]]" in converted
    assert "https://a.example/b.md" in converted
    assert "(sub/page.md)" in converted
    assert "![](https://img.example/a.png)" in converted or "![图]" in converted
    assert "[[已有]]" in converted


def test_wiki_link_label_forms() -> None:
    assert sync_wiki.wiki_link("Home", "Home.md") == "[[Home]]"
    assert sync_wiki.wiki_link("首页", "Home.md") == "[[Home|首页]]"


def test_sync_converts_and_generates_sidebar(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    make_docs(repo_root)
    wiki_dir = tmp_path / "wiki"
    init_git_repo(wiki_dir)

    changed = sync_wiki.sync(repo_root, wiki_dir)
    assert set(changed) == {"Home.md", "安装与部署.md", "_Sidebar.md"}

    home = (wiki_dir / "Home.md").read_text(encoding="utf-8")
    assert "[[安装与部署]]" in home  # 标签与页面同名时省略
    install = (wiki_dir / "安装与部署.md").read_text(encoding="utf-8")
    assert "[[Home|首页]]" in install
    assert "(https://github.com/x/y)" in install
    assert "(sub/page.md)" in install
    sidebar = (wiki_dir / "_Sidebar.md").read_text(encoding="utf-8")
    assert sidebar.index("[[Home|SecOne 首页]]") < sidebar.index("[[安装与部署")
    assert "docs/wiki" in sidebar


def test_sync_is_idempotent(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    make_docs(repo_root)
    wiki_dir = tmp_path / "wiki"
    init_git_repo(wiki_dir)

    assert sync_wiki.sync(repo_root, wiki_dir)
    assert sync_wiki.sync(repo_root, wiki_dir) == []
    assert sync_wiki.sync(repo_root, wiki_dir) == []


def test_sync_dry_run_writes_nothing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    make_docs(repo_root)
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    changed = sync_wiki.sync(repo_root, wiki_dir, dry_run=True)
    assert len(changed) == 3
    assert list(wiki_dir.iterdir()) == []


def test_main_commit_on_real_wiki_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    make_docs(repo_root)
    (repo_root / ".git").mkdir()
    wiki_dir = tmp_path / "wiki"
    init_git_repo(wiki_dir)

    exit_code = sync_wiki.main(
        ["--repo-root", str(repo_root), "--wiki-dir", str(wiki_dir), "--message", "sync test"]
    )
    assert exit_code == 0
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=wiki_dir, capture_output=True, text=True, check=True
    ).stdout
    assert "sync test" in log
    # 第二次运行无变更，不再产生提交
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=wiki_dir, capture_output=True, text=True, check=True
    ).stdout
    assert sync_wiki.main(["--repo-root", str(repo_root), "--wiki-dir", str(wiki_dir)]) == 0
    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=wiki_dir, capture_output=True, text=True, check=True
    ).stdout
    assert before == after
