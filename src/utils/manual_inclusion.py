"""Reader-chosen manual inclusion.

A paper can miss the score threshold and still be worth reading. Marking it
keeps the numbers as they were scored but records *why* it passes, so reports
stay honest about the LLM judgment.
"""

MANUAL_INCLUSION_REASON = "手动纳入（读者标记）"
MANUAL_EXCLUSION_REASON = "手动排除（读者标记）"


def force_manual_inclusion(response: object) -> object:
    """Return a score response that counts as qualified despite its score."""
    if getattr(response, "is_qualified", False):
        return response
    return response.model_copy(
        update={
            "is_qualified": True,
            "qualification_reason": MANUAL_INCLUSION_REASON,
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
        }
    )
