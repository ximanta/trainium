import random
from dataclasses import dataclass, field

from main.agents.trainium.director.state import SessionState

SPEAK_PROBABILITY_BY_TYPE = {
    "curious": 0.35,
    "beginner": 0.20,
    "skeptic": 0.30,
    "silent": 0.05,
    "confused": 0.25,
    "fast_learner": 0.15,
    "distracted": 0.15,
    "hacker": 0.20,
    "senior_practitioner": 0.20,
    # Custom learners have no type-derived behaviour, so they sit at the middle
    # of the range unless the admin sets a probability explicitly.
    "custom": 0.20,
}


@dataclass
class DirectorPolicy:
    """Layer A: deterministic gate. Pure Python, no LLM call, rejects most
    turns before Layer B ever runs. Architecture doc §3.3.
    """

    min_gap_s: float = 45.0
    # Was 6, which is one learner every 100 seconds. A real session hit the
    # limit after nine minutes and then went permanently silent while the
    # trainer kept asking "anyone?" and "Arjun can you speak up?". The ceiling
    # exists to stop a runaway Director, not to pace a class, so it sits well
    # above what a lively room actually uses.
    max_interventions_per_10min: int = 15
    per_persona_cooldown_s: float = 180.0
    speak_probability_by_type: dict = field(default_factory=lambda: dict(SPEAK_PROBABILITY_BY_TYPE))
    objective_gate: bool = True
    multi_learner_p: float = 0.12
    group_discussion_p: float = 0.03

    def turn_budget(self, duration_s: float) -> int:
        """Hard ceiling on persona turns for a session of this length.

        Deliberately not derived from `max_interventions_per_10min`: that is a
        pacing valve set generously so a lively class is never silenced, while
        this is a spend ceiling. Tying them together meant raising the pacing
        limit tripled the budget, which is the opposite of what a cost control
        should do. Eight turns per ten minutes is roughly twice what a real
        session used, so it never binds in practice but still caps a runaway.

        Sized against a measured session rather than guessed: a real class ran
        at 11.8 turns per ten minutes, so the ceiling sits at 18, comfortably
        above an active room and far below anything that could run up a bill.
        """
        return max(10, int((duration_s / 600.0) * 18))

    def should_open_gate(
        self,
        state: SessionState,
        trainer_paused_s: float,
        trainer_asked_open_question: bool,
        trainer_stated_misconception: bool,
        scenario_directive_due: bool,
        rng: random.Random | None = None,
    ) -> bool:
        rng = rng or random
        last_intervention = max(
            (p.last_spoke_at for p in state.persona_states.values()), default=-999.0
        )
        since_last = state.elapsed_s - last_intervention

        # Out of time or out of turns: nothing reopens the gate, including the
        # hard triggers, because both are cost ceilings rather than pacing.
        if state.out_of_budget():
            return False

        # A held floor outranks every trigger below, including the pause one: a
        # trainer who says "let me explain first" and then pauses to think is
        # still explaining, and a persona jumping into that pause is exactly the
        # behaviour they asked to stop. Hands can still go up; that is handled
        # in Layer B, which is allowed to run so the queue builds.
        if state.floor_held:
            return False

        # Hard triggers bypass the cooldown and probability roll entirely.
        # A named question is the strongest of them: ignoring someone the
        # trainer just addressed is the one thing a classroom never does.
        if state.awaiting_reply_from:
            return True
        if trainer_asked_open_question:
            return True
        if trainer_paused_s > 8.0:
            return True
        if trainer_stated_misconception:
            return True
        if scenario_directive_due:
            return True

        if since_last < self.min_gap_s:
            return False
        if state.interventions_in_last_10min() >= self.max_interventions_per_10min:
            return False

        return rng.random() < self._aggregate_speak_probability(state)

    def eligible_personas(self, state: SessionState) -> list[str]:
        """Personas off cooldown, not muted, and not already waiting with a
        raised hand (their pending line is held until the trainer calls on
        them, so they must not be reselected in the meantime).
        """
        # A question put to someone by name belongs to them. Their own
        # cooldown is waived too, since the trainer just asked them directly
        # and "they spoke recently" is not a reason to leave it hanging.
        addressed = state.awaiting_reply_from
        if addressed:
            persona = state.persona_states.get(addressed)
            if persona is not None and not persona.muted:
                return [addressed]

        return [
            pid
            for pid, p in state.persona_states.items()
            if not p.muted
            and not p.hand_raised
            and state.elapsed_s - p.last_spoke_at >= self.per_persona_cooldown_s
        ]

    def _aggregate_speak_probability(self, state: SessionState) -> float:
        if not state.persona_states:
            return 0.0
        # Muted personas cannot speak, so they must not contribute to the
        # chance that *someone* speaks; otherwise a fully muted classroom
        # still opens the gate and then finds nobody eligible.
        probs = [
            p.speak_probability
            if p.speak_probability is not None
            else self.speak_probability_by_type.get(p.persona_type, 0.15)
            for p in state.persona_states.values()
            if not p.muted
        ]
        # Probability at least one persona wants to speak, treating each
        # independently: 1 - product(1 - p_i).
        product = 1.0
        for p in probs:
            product *= 1.0 - p
        return 1.0 - product

    def is_objective_taught(self, state: SessionState, objective_id: str | None) -> bool:
        if not self.objective_gate or objective_id is None:
            return True
        return objective_id in state.objectives_covered
