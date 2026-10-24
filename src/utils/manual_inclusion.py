"""Reader-chosen manual inclusion.

A paper can miss the score threshold and still be worth reading. Marking it
keeps the numbers as they were scored but records *why* it passes, so reports
stay honest about the LLM judgment.
"""

import re
from typing import Optional, Sequence

MANUAL_INCLUSION_REASON = "手动纳入（读者标记）"
MANUAL_EXCLUSION_REASON = "手动排除（读者标记）"
REINCLUSION_REASON = "重新纳入（读者标记）"


def _strip_version(value: str) -> str:
    return re.sub(r"v\d+$", "", str(value or "").strip())


def override_keys(
    *,
    source: str,
    paper_id: str,
    canonical_id: Optional[str] = None,
    arxiv_id: Optional[str] = None,
) -> Sequence[str]:
    """Identity keys a reader verdict follows.

    A verdict must survive a new arXiv version and join the journal/arXiv
    mirrors of the same paper, so it is stored under every known alias:
    the arXiv identifier first, then the source-local canonical identifier.
    """
    keys: list[str] = []
    for candidate in (arxiv_id, canonical_id, paper_id):
        text = _strip_version(candidate or "")
        if text and text.lower() not in keys:
            keys.append(text.lower())
    return keys[:2] or [f"{source}:{paper_id}".lower()]


def force_manual_inclusion(response: object) -> object:
    """Return a score response that counts as qualified despite its score."""
    if getattr(response, "is_qualified", False):
        return response
    return response.model_copy(
        update={
            "is_qualified": True,
            "qualification_reason": MANUAL_INCLUSION_REASON,
            "reader_verdict": "include",
        }
    )


def force_manual_exclusion(response: object) -> object:
    """Return a score response that counts as unqualified despite its score."""
    if not getattr(response, "is_qualified", True):
        return response
    return response.model_copy(
        update={
            "is_qualified": False,
            "qualification_reason": MANUAL_EXCLUSION_REASON,
            "reader_verdict": "exclude",
        }
    )
