import asyncio
import time

from main.agents.trainium.director.layer_b import DirectorDecision, decide_and_speak
from main.agents.trainium.director.policy import DirectorPolicy
from main.agents.trainium.director.state import SessionState

SPECULATION_INTERVAL_S = 4.0
STALE_AFTER_S = 6.0  # if the cached decision is older than this, don't trust it


class SpeculativeDirector:
    """Runs Layer B ahead of time on partial transcript while the trainer is
    still speaking, so the real endpointing moment only has to validate a
    cached decision instead of paying Layer B's full latency cold.

    Architecture doc §3.2: "This removes 400-700ms from the critical path,
    and is the reason the Director is not a per-turn LangGraph invocation."
    In practice (see project memory: trainium-m2-latency-findings), Layer B
    alone measured 2.3-2.7s, well over the doc's 500ms estimate, so hiding it
    behind ongoing speech is not an optimization here, it's load-bearing.
    """

    def __init__(self, policy: DirectorPolicy):
        self.policy = policy
        self._task: asyncio.Task | None = None
        self._cached_decision: DirectorDecision | None = None
        self._cached_at: float = -999.0
        self._cached_transcript_len: int = -1
        self._speaking = False

    def on_speech_start(self):
        self._speaking = True
        self._cached_decision = None
        self._cached_transcript_len = -1

    def on_speech_end(self):
        self._speaking = False

    def note_partial_transcript(
        self, state: SessionState, eligible_persona_ids: list[str]
    ) -> None:
        """Call this each time new partial transcript text arrives while the
        trainer is speaking. Fires a speculative Layer B pass at most once
        per SPECULATION_INTERVAL_S, and only if the transcript actually grew
        since the last speculation (no point re-running on the same text).
        """
        if not self._speaking:
            return
        if self._task is not None and not self._task.done():
            return
        current_len = len(state.transcript_recent)
        if current_len == self._cached_transcript_len:
            return
        if time.monotonic() - self._cached_at < SPECULATION_INTERVAL_S:
            return

        self._task = asyncio.create_task(self._speculate(state, eligible_persona_ids, current_len))

    async def _speculate(
        self, state: SessionState, eligible_persona_ids: list[str], transcript_len: int
    ) -> None:
        if not eligible_persona_ids:
            return
        try:
            decision = await decide_and_speak(state, eligible_persona_ids)
        except Exception:
            return
        self._cached_decision = decision
        self._cached_at = time.monotonic()
        self._cached_transcript_len = transcript_len

    async def resolve(
        self, state: SessionState, eligible_persona_ids: list[str]
    ) -> DirectorDecision | None:
        """Called at real endpointing (activity_end). Returns a cached
        decision if one is fresh enough, otherwise falls back to a
        synchronous Layer B call.

        Freshness is time-based, not an exact transcript match: the
        trainer's transcript grows continuously while speaking, so requiring
        the cached decision's transcript length to exactly match the final
        transcript would almost always miss in real speech (a speculation
        computed even 1s before the real stop is stale by that rule). The
        doc's own framing, "if they stop now, who speaks," tolerates a few
        more words having been said since the speculation ran; only staleness
        in time matters.
        """
        is_fresh = time.monotonic() - self._cached_at < STALE_AFTER_S

        if self._cached_decision is not None and is_fresh:
            decision = self._cached_decision
            self._cached_decision = None
            return decision

        if self._task is not None and not self._task.done():
            # A speculation is mid-flight against slightly stale transcript;
            # not worth waiting on since we'd rather pay one fresh call than
            # gamble on a result computed from incomplete speech.
            self._task.cancel()

        if not eligible_persona_ids:
            return None
        return await decide_and_speak(state, eligible_persona_ids)
