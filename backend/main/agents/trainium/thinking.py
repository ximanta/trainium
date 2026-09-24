"""Thinking-budget config that works across models.

`thinking_budget=0` is how structured output is kept clean: without it the
model's reasoning trace leaks into constrained JSON and the decoder loops
(see project memory, trainium-gemini-sdk-thinking-leak).

But the models disagree about it. As of 2026-09-24, gemini-3.5-flash-lite
rejects a budget of 0 outright with an opaque 400 INVALID_ARGUMENT, while
gemini-3.8-flash accepts it. Passing 0 blindly therefore turns a model swap
made for speed into a total failure with an error that says nothing about the
cause.
"""

from google.genai import types

# Models known to reject a zero budget. The smallest budget they accept is
# used instead, which keeps the trace short without tripping the check.
_REJECTS_ZERO_BUDGET = ("flash-lite",)
_MINIMUM_BUDGET = 128


def minimal_thinking(model: str) -> types.ThinkingConfig:
    """The smallest thinking budget `model` will accept."""
    if any(marker in model for marker in _REJECTS_ZERO_BUDGET):
        return types.ThinkingConfig(thinking_budget=_MINIMUM_BUDGET)
    return types.ThinkingConfig(thinking_budget=0)
