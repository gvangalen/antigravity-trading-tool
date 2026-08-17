from __future__ import annotations


class ReviewToolAdapter:
    async def execute(self, **_kwargs):
        raise LookupError("review_history_unavailable")
