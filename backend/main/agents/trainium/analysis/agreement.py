"""Krippendorff's alpha between model scores and human scores.

Chosen over percent agreement or Cohen's kappa because it handles what this
data actually looks like: ordinal 1-5 scores, more than two raters, and gaps
where a rater skipped a competency or the session gave no basis to judge it.
Percent agreement would also flatter us, since it treats a 4-vs-5 disagreement
the same as 1-vs-5.

Alpha is 1 for perfect agreement, 0 for agreement no better than chance, and
negative for systematic disagreement. The spec's ship gate is 0.6 per
competency (architecture doc §6).
"""

from collections import defaultdict
from dataclasses import dataclass

# Ordinal difference, the squared-rank metric Krippendorff defines for ordered
# categories. For a contiguous 1-5 scale this reduces to the squared gap, so a
# 1-vs-5 disagreement counts sixteen times a 4-vs-5 one.
def _delta(a: float, b: float) -> float:
    return (a - b) ** 2


@dataclass
class CompetencyAgreement:
    competency_key: str
    alpha: float
    units: int  # sessions where at least two raters scored this competency
    passes: bool


def krippendorff_alpha(units: list[list[float]]) -> float:
    """Alpha over a list of units, each holding that unit's observed scores.

    A unit is one session-competency pair; its values are the scores different
    raters gave it. Units with fewer than two values carry no information about
    agreement and are dropped.
    """
    usable = [u for u in units if len(u) >= 2]
    if len(usable) < 2:
        return float("nan")

    # Built from the coincidence matrix rather than raw pair counts. The
    # distinction matters: a unit rated by three people contributes its pairs
    # weighted by 1/(m-1), and the expected term must use those same weights.
    # Pooling values unweighted instead inflates alpha, which is the mistake
    # this implementation was checked against a published example to catch.
    coincidence: dict[tuple[float, float], float] = {}
    for u in usable:
        m = len(u)
        for i, a in enumerate(u):
            for j, b in enumerate(u):
                if i == j:
                    continue
                key = (a, b)
                coincidence[key] = coincidence.get(key, 0.0) + 1.0 / (m - 1)

    total = sum(coincidence.values())
    if total < 2:
        return float("nan")

    observed = sum(w * _delta(a, b) for (a, b), w in coincidence.items()) / total

    # Marginals of the coincidence matrix are what "by chance" means here: how
    # often each value occurs across the whole sample, weighted the same way.
    marginal: dict[float, float] = {}
    for (a, _), w in coincidence.items():
        marginal[a] = marginal.get(a, 0.0) + w

    expected = sum(
        na * marginal[b] * _delta(a, b)
        for a, na in marginal.items()
        for b in marginal
        if a != b
    ) / (total * (total - 1))

    if expected == 0:
        # Every rater gave every unit the same value. Perfect agreement, though
        # it also means the data has no variance to disagree about.
        return 1.0
    return 1.0 - (observed / expected)


def measure_agreement(
    ratings: list[dict], threshold: float
) -> list[CompetencyAgreement]:
    """Alpha per competency across a golden set.

    `ratings` is a flat list of {simulation_id, competency_key, rater, score},
    mixing the model in as one rater alongside the humans. Grouping by
    competency rather than pooling is deliberate: the spec gates per
    competency, and pooled alpha would hide one criterion scoring badly behind
    six scoring well.
    """
    by_competency: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in ratings:
        by_competency[r["competency_key"]][r["simulation_id"]].append(float(r["score"]))

    results = []
    for key, sessions in sorted(by_competency.items()):
        alpha = krippendorff_alpha(list(sessions.values()))
        usable = sum(1 for v in sessions.values() if len(v) >= 2)
        results.append(
            CompetencyAgreement(
                competency_key=key,
                alpha=alpha,
                units=usable,
                # NaN fails: an unmeasurable competency has not passed a gate,
                # it has simply not been measured.
                passes=alpha == alpha and alpha >= threshold,
            )
        )
    return results
