"""
session.py — Save and resume merge review sessions.

Stores decisions made so far, position in the review queue, timestamps,
and SHA-256 hashes of both input files so we can detect file changes.
"""

from __future__ import annotations
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict


@dataclass
class SessionState:
    file_a_path: str
    file_b_path: str
    file_a_hash: str
    file_b_hash: str
    timestamp: float

    # MergeDecisions contents (plain dicts for JSON serialization)
    source_map: dict[str, str] = field(default_factory=dict)
    indi_map: dict[str, str] = field(default_factory=dict)
    family_map: dict[str, str] = field(default_factory=dict)

    source_disposition: dict[str, str] = field(default_factory=dict)
    indi_disposition: dict[str, str] = field(default_factory=dict)
    family_disposition: dict[str, str] = field(default_factory=dict)

    field_choices: dict[str, list] = field(default_factory=dict)

    # Review queue state
    source_candidate_idx: int = 0
    indi_candidate_idx: int = 0
    unmatched_source_idx: int = 0
    unmatched_indi_idx: int = 0

    # Batch approval state
    auto_approved: bool = False

    # CLI args to reproduce the session
    cli_args: dict = field(default_factory=dict)


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def save_session(path: str, state: SessionState) -> None:
    """Write session state to a JSON file."""
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(asdict(state), f, indent=2)
    import os
    os.replace(tmp, path)


def load_session(path: str) -> SessionState:
    """Load session state from a JSON file. Raises ValueError on hash mismatch."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    state = SessionState(**data)

    # Verify files haven't changed
    actual_a = _file_hash(state.file_a_path)
    actual_b = _file_hash(state.file_b_path)
    if actual_a != state.file_a_hash:
        raise ValueError(
            f'File A has changed since session was saved: {state.file_a_path}'
        )
    if actual_b != state.file_b_hash:
        raise ValueError(
            f'File B has changed since session was saved: {state.file_b_path}'
        )
    return state


def new_session(file_a_path: str, file_b_path: str, cli_args: dict | None = None) -> SessionState:
    """Create a new session for the given files."""
    return SessionState(
        file_a_path=file_a_path,
        file_b_path=file_b_path,
        file_a_hash=_file_hash(file_a_path),
        file_b_hash=_file_hash(file_b_path),
        timestamp=time.time(),
        cli_args=cli_args or {},
    )
