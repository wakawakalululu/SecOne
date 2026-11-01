from __future__ import annotations

import io
import zipfile

from secone.config import AppConfig
from secone.core.ingest import IngestEngine
from secone.core.workspace import TaskWorkspace


def ingest(config: AppConfig, workspace: TaskWorkspace, sources, text: str = ""):
    return IngestEngine(config, workspace).ingest(list(sources), text=text)


def make_zip(entries: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    buffer.seek(0)
    return buffer


def test_zip_extraction_and_nested_text(config: AppConfig, tmp_path) -> None:
    source = tmp_path / "challenge.zip"
    source.write_bytes(
        make_zip(
            {
                "level/readme.txt": b"flag{1n_4rch1v3}",
                "level/notes.md": b"hello",
            }
        ).getvalue()
    )
    workspace = TaskWorkspace.create(config.paths.workspace)
    result = ingest(config, workspace, [source])
    assert result.archives_extracted == 1
    extracted_text = "\n".join(
        (workspace.root / artifact.path).read_text(encoding="utf-8", errors="replace")
        for artifact in result.files
        if artifact.source == "archive"
    )
    assert "flag{1n_4rch1v3}" in extracted_text
    assert any(artifact.source == "input" for artifact in result.files)


def test_zip_path_traversal_is_rejected(config: AppConfig, tmp_path) -> None:
    source = tmp_path / "evil.zip"
    source.write_bytes(
        make_zip({"../escape.txt": b"owned", "safe/ok.txt": b"ok"}).getvalue()
    )
    workspace = TaskWorkspace.create(config.paths.workspace)
    result = ingest(config, workspace, [source])
    assert any("拒绝可疑压缩路径" in warning for warning in result.warnings)
    assert not (workspace.root.parent.parent / "escape.txt").exists()
    assert list(workspace.extracted.rglob("escape.txt")) == []
    assert list(workspace.extracted.rglob("ok.txt"))


def test_zip_entry_limit_is_enforced(config: AppConfig, tmp_path) -> None:
    config.set("analysis.archive_max_entries", 2)
    source = tmp_path / "many.zip"
    source.write_bytes(
        make_zip({f"file_{i}.txt": b"data" for i in range(8)}).getvalue()
    )
    workspace = TaskWorkspace.create(config.paths.workspace)
    result = ingest(config, workspace, [source])
    extracted = [artifact for artifact in result.files if artifact.source == "archive"]
    assert len(extracted) <= 2
    assert any("上限" in warning for warning in result.warnings)


def test_duplicate_files_are_deduplicated(config: AppConfig, tmp_path) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("identical content", encoding="utf-8")
    second.write_text("identical content", encoding="utf-8")
    workspace = TaskWorkspace.create(config.paths.workspace)
    result = ingest(config, workspace, [first, second])
    assert len(result.files) == 1
    assert result.duplicate_count == 1


def test_pasted_text_becomes_material(config: AppConfig, tmp_path) -> None:
    workspace = TaskWorkspace.create(config.paths.workspace)
    result = ingest(config, workspace, [], text="flag{p4st3d_t3xt}")
    assert len(result.files) == 1
    artifact = result.files[0]
    assert artifact.path.endswith(".txt")
    assert "flag{p4st3d_t3xt}" in (workspace.root / artifact.path).read_text(
        encoding="utf-8"
    )
