#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared validation utilities and constants for a2a clients."""

MAX_ID_LENGTH = 256
MAX_THREAD_ID_LENGTH = 256
MAX_BODY_LENGTH = 100_000


def _validate_project_name(name: str) -> None:
    """Reject project names that could cause path traversal or directory escape."""
    if not name or not name.strip():
        raise ValueError("project name must not be empty")
    if "/" in name or "\\" in name or name[0] == ".":
        raise ValueError(f"invalid project name {name!r} — must not contain path separators or start with '.'")


def _validate_agent_id(agent_id: str, label: str = "agent_id") -> None:
    """Validate agent ID is not empty and not too long."""
    if not agent_id or not agent_id.strip():
        raise ValueError(f"{label} must not be empty")
    agent_id = agent_id.strip()
    if len(agent_id) > MAX_ID_LENGTH:
        raise ValueError(f"{label} too long ({len(agent_id)} chars, max {MAX_ID_LENGTH})")
