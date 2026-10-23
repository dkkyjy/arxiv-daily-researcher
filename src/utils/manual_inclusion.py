"""Reader-chosen manual inclusion.

A paper can miss the score threshold and still be worth reading. Marking it
keeps the numbers as they were scored but records *why* it passes, so reports
stay honest about the LLM judgment.
"""

MANUAL_INCLUSION_REASON = "手动纳入（读者标记）"


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
