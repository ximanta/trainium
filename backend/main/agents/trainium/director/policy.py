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
}


@dataclass
class DirectorPolicy:
    """Layer A: deterministic gate. Pure Python, no LLM call, rejects most
    turns before Layer B ever runs. Architecture doc §3.3.
    """

    min_gap_s: float = 45.0
    max_interventions_per_10min: int = 6
    per_persona_cooldown_s: float = 180.0
    speak_probability_by_type: dict = field(default_factory=lambda: dict(SPEAK_PROBABILITY_BY_TYPE))
    objective_gate: bool = True
    multi_learner_p: float = 0.12
    group_discussion_p: float = 0.03

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

        # Hard triggers bypass the cooldown and probability roll entirely.
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
        """Personas not on their own per-persona cooldown."""
        return [
            pid
            for pid, p in state.persona_states.items()
            if state.elapsed_s - p.last_spoke_at >= self.per_persona_cooldown_s
        ]

    def _aggregate_speak_probability(self, state: SessionState) -> float:
        if not state.persona_states:
            return 0.0
        probs = [
            self.speak_probability_by_type.get(p.persona_type, 0.15)
            for p in state.persona_states.values()
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
