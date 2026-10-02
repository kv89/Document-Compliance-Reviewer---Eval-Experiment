"""Dataset sign-off gate (spec sections 9.3, 28).

Shared by every runner. A result is reportable only if a human reviewed the exact bytes it was
produced from, which is why the check is a hash comparison rather than a checkbox.
"""

from __future__ import annotations

import hashlib
import re

from agent.schemas.loaders import REPO_ROOT


def signoff_status(dataset_version: str) -> tuple[bool, str]:
    """Is the human spot-check signed off, and does it refer to the current dataset?

    An unsigned dataset may be used to verify machinery, but results from it must not be reported.
    A sign-off that names a different `ground_truth.jsonl` is worse than none, because it looks
    like approval of data nobody reviewed: regenerating the dataset must invalidate it.
    """
    base = REPO_ROOT / "dataset" / "generated" / dataset_version
    path = base / "validation.md"
    if not path.exists():
        return False, "no validation.md: the dataset has never been reviewed"

    text = path.read_text(encoding="utf-8")
    reviewer = re.search(r"\|\s*reviewer\s*\|(?P<value>[^|]*)\|", text)
    if reviewer is None or not reviewer.group("value").strip():
        return False, "validation.md sign-off table is empty"

    result = re.search(r"\|\s*result\s*\|(?P<value>[^|]*)\|", text)
    if result is None or result.group("value").strip().lower() != "accepted":
        return False, "validation.md records a sign-off that is not 'accepted'"

    recorded = re.search(
        r"\|\s*reviewed ground_truth\.jsonl sha256\s*\|(?P<value>[^|]*)\|", text
    )
    if recorded is None or not recorded.group("value").strip():
        return False, "sign-off records no ground_truth.jsonl sha256, so it cannot be verified"

    actual = hashlib.sha256((base / "ground_truth.jsonl").read_bytes()).hexdigest()
    claimed = recorded.group("value").strip().strip("`")
    if claimed != actual:
        return False, (
            f"sign-off is stale: it reviewed ground_truth.jsonl {claimed[:12]}... but the file on "
            f"disk is {actual[:12]}.... Re-review the dataset."
        )

    return True, f"signed off by {reviewer.group('value').strip()}"
