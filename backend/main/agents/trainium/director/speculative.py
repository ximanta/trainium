import asyncio
import time

from main.agents.trainium.director.layer_b import DirectorDecision, decide_and_speak
from main.agents.trainium.director.policy import DirectorPolicy
from main.agents.trainium.director.state import SessionState

# Tuned to the Layer B latency actually measured, 3-6s, not the 500ms the
# architecture doc assumed. A real session logged cache=0/11: speculation ran,
# produced a decision, and it expired before the trainer stopped talking,
# because the interval plus Layer B's own runtime exceeded the staleness
# window every time. Speculate more often and trust the result for longer;
# the turn-count guard below is what actually keeps a stale line out, and it
# is exact rather than a guess about elapsed time.
SPECULATION_INTERVAL_S = 2.0
STALE_AFTER_S = 20.0


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
        # How many persona turns had happened when the speculation ran. If it
        # has changed by the time the decision is used, the conversation has
        # moved on and the cached line no longer fits it.
        self._cached_turns: int = -1
        self._speaking = False
        # Counters for a real session: whether speculation actually hides the
        # Layer B call is the difference between a 1.5s reply and a 4s one,
        # and it cannot be judged from the code alone.
        self.hits = 0
        self.misses = 0
        self.speculations = 0
        # Why a speculation did not fire. Two sessions in a row logged
        # cache=0/15 with almost no speculations, and the reason cannot be
        # read off the code: each guard looks reasonable alone.
        self.skip_not_speaking = 0
        self.skip_in_flight = 0
        self.skip_same_text = 0
        self.skip_too_soon = 0

    def on_speech_start(self):
        self._speaking = True
        self._cached_decision = None
        self._cached_transcript_len = -1
        self._cached_turns = -1
        # Abandon a speculation still running from the previous turn. Layer B
        # takes about four seconds, longer than many turns, so without this a
        # short turn leaves a task in flight that blocks every speculation of
        # the next turn: a real session logged two speculations across fifteen
        # turns and never once hit the cache.
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        # The interval is measured from the last speculation's completion, so
        # a stale one would also hold the next turn off for two more seconds.
        self._cached_at = -999.0

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
            self.skip_not_speaking += 1
            return
        if self._task is not None and not self._task.done():
            self.skip_in_flight += 1
            return
        # Length of what is being said right now, not of the settled
        # transcript. transcript_recent only grows when a turn completes, so
        # gating on it meant the condition was true once and false for the
        # rest of the turn: twelve seconds of speech fired one speculation,
        # which had gone stale by the time the trainer stopped. Every turn
        # then paid Layer B in full, which is the latency this class exists
        # to hide.
        current_len = len(state.in_progress_partial)
        if current_len == self._cached_transcript_len:
            self.skip_same_text += 1
            return
        if time.monotonic() - self._cached_at < SPECULATION_INTERVAL_S:
            self.skip_too_soon += 1
            return

        self.speculations += 1
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
        self._cached_turns = state.turns_taken

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

        # A speculation computed before a persona spoke does not know that
        # persona has now had their turn, so serving it replays a line into a
        # conversation that has moved on: one session had the same learner
        # answer twice in a row, the second time repeating themselves. If
        # anyone has spoken since the speculation ran, it is stale whatever
        # the clock says.
        if self._cached_decision is not None and self._cached_turns != state.turns_taken:
            self._cached_decision = None

        if self._cached_decision is not None and is_fresh:
            decision = self._cached_decision
            self._cached_decision = None
            self.hits += 1
            return decision

        self.misses += 1

        if self._task is not None and not self._task.done():
            # A speculation is mid-flight against slightly stale transcript;
            # not worth waiting on since we'd rather pay one fresh call than
            # gamble on a result computed from incomplete speech.
            self._task.cancel()

        if not eligible_persona_ids:
            return None
        return await decide_and_speak(state, eligible_persona_ids)
