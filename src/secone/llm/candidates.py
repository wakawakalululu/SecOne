"""候选模型清单加载与校验。

清单文件位于 ``models/candidates.json``，只描述推荐模型及其获取渠道；
程序自身不做联网下载，下载动作由操作者在浏览器中完成。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 64
_MAX_NOTE_CHARS = 400
_MAX_NAME_CHARS = 120


@dataclass(frozen=True)
class ModelSource:
    label: str
    url: str


@dataclass(frozen=True)
class ModelCandidate:
    name: str
    quantization: str
    size_label: str
    architecture: str
    context_default: int
    note: str
    sources: tuple[ModelSource, ...] = field(default_factory=tuple)


def _clean_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    return text[:limit]


def _parse_sources(raw: object) -> tuple[ModelSource, ...]:
    if not isinstance(raw, list):
        return ()
    sources: list[ModelSource] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = _clean_text(item.get("url"), 500)
        if not url.startswith(("https://", "http://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        label = _clean_text(item.get("label"), 80) or url
        sources.append(ModelSource(label=label, url=url))
        if len(sources) >= 6:
            break
    return tuple(sources)


def _parse_candidate(raw: object) -> ModelCandidate | None:
    if not isinstance(raw, dict):
        return None
    name = _clean_text(raw.get("name"), _MAX_NAME_CHARS)
    sources = _parse_sources(raw.get("sources"))
    if not name or not sources:
        return None
    context_default = raw.get("context_default")
    if not isinstance(context_default, int) or context_default <= 0:
        context_default = 8192
    return ModelCandidate(
        name=name,
        quantization=_clean_text(raw.get("quantization"), 60),
        size_label=_clean_text(raw.get("size_label"), 120),
        architecture=_clean_text(raw.get("architecture"), 60),
        context_default=context_default,
        note=_clean_text(raw.get("note"), _MAX_NOTE_CHARS),
        sources=sources,
    )


def load_candidates(path: Path) -> list[ModelCandidate]:
    """Load and validate the candidate catalog; a missing or broken file yields []."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        logger.warning("候选模型清单读取失败 %s: %s", path, exc)
        return []
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("candidates")
    if not isinstance(raw_items, list):
        return []
    candidates: list[ModelCandidate] = []
    seen: set[str] = set()
    for item in raw_items:
        parsed = _parse_candidate(item)
        if parsed is None or parsed.name in seen:
            continue
        seen.add(parsed.name)
        candidates.append(parsed)
        if len(candidates) >= _MAX_CANDIDATES:
            break
    return candidates
