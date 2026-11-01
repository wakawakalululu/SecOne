from __future__ import annotations

from dataclasses import dataclass

from ..config import AppConfig
from ..db import TaskStore
from ..llm import LLMClient, LlamaServerManager
from ..paths import AppPaths


@dataclass
class AppContext:
    config: AppConfig
    paths: AppPaths
    store: TaskStore
    manager: LlamaServerManager
    client: LLMClient
