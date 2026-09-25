"""Shared models for the replacement-candidate Codex orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class FailureCategory(str, Enum):
    PREREQUISITE = "prerequisite failure"
    CONTROLLER = "controller/orchestration failure"
    CODEX = "Codex execution failure"
    TEST = "test failure"


class OrchestrationError(RuntimeError):
    def __init__(self, category: FailureCategory, message: str):
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class Task:
    mode: str
    number: int
    title: str
    body: str
    url: str


@dataclass(frozen=True)
class Workspace:
    branch: str
    path: Path


@dataclass(frozen=True)
class PreflightReport:
    repo_root: Path
    git_name: str
    git_email: str
    codex_version: str
    codex_auth_status: str
