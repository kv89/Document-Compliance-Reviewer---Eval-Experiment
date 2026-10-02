"""Loading and saving helpers for the experiment's on-disk formats.

JSONL is the source of truth for ground truth and for trial rows; SQLite is a derived convenience
view built later by a loader script (spec section 23).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, TypeVar

from pydantic import BaseModel

from agent.schemas.models import GroundTruthCase, Policy

T = TypeVar("T", bound=BaseModel)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / "dataset" / "policies"


def load_policy(policy_id: str = "POL-001") -> Policy:
    path = POLICY_DIR / f"{policy_id}.json"
    return Policy.model_validate_json(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path, model: type[T]) -> list[T]:
    items: list[T] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(model.model_validate_json(line))
            except Exception as exc:  # noqa: BLE001 - we want the line number in the message
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
    return items


def write_jsonl(path: Path, items: Iterable[BaseModel]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(item.model_dump_json() + "\n")
            count += 1
    return count


def append_jsonl(path: Path, items: Iterable[BaseModel]) -> int:
    """Append trial rows. Results files are append-only (spec section 12)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as fh:
        for item in items:
            fh.write(item.model_dump_json() + "\n")
            count += 1
    return count


def load_ground_truth(dataset_version: str) -> list[GroundTruthCase]:
    path = REPO_ROOT / "dataset" / "generated" / dataset_version / "ground_truth.jsonl"
    return read_jsonl(path, GroundTruthCase)


def load_document(case: GroundTruthCase) -> str:
    """Read a case document, preserving exact bytes.

    newline="" is required: character offsets in evidence are measured against the file as stored,
    so newline translation would silently shift every offset.
    """
    path = REPO_ROOT / case.document_path
    with path.open(encoding="utf-8", newline="") as fh:
        return fh.read()


def iter_pretty_json(obj: BaseModel) -> Iterator[str]:
    yield json.dumps(obj.model_dump(mode="json"), indent=2, ensure_ascii=False)
