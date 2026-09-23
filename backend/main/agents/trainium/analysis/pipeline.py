"""The analysis run: transcript evidence, video evidence, then scores.

Kicked off automatically when a session ends. Runs as a background task so a
trainer closing their laptop does not cancel their own report.
"""

import asyncio
import uuid

from main.agents.trainium.analysis.extract import extract_moments
from main.agents.trainium.analysis.score import score_competencies
from main.agents.trainium.analysis.video import analyse_video
from main.agents.trainium.db_manager import (
    recordings_collection,
    reports_collection,
    rubrics_collection,
    simulations_collection,
    transcripts_collection,
)
from main.agents.trainium.storage import download_file

DEFAULT_RUBRIC_ID = "rubric_default_v1"
VIDEO_RUBRIC_ID = "rubric_delivery_v1"

# Below this, there was no session worth reporting on. A trainer who joined,
# said nothing and left should not get a page of scores built from silence,
# and every such run costs tokens.
MIN_SEGMENTS_FOR_REPORT = 4


async def _load_rubric(rubric_id: str) -> list[dict]:
    rubric = await rubrics_collection.find_one({"id": rubric_id}, {"_id": 0})
    return (rubric or {}).get("competencies", [])


async def run_analysis(simulation_id: str) -> None:
    """Produce the report for a finished session.

    Every failure is recorded on the report rather than raised: this runs
    detached, so an exception here would vanish into the event loop and the
    session would simply never show a report with no indication why.
    """
    report_id = f"rep_{uuid.uuid4().hex[:12]}"
    await reports_collection.insert_one(
        {
            "id": report_id,
            "simulation_id": simulation_id,
            "rubric_id": DEFAULT_RUBRIC_ID,
            "status": "running",
            "scores": [],
            "video_scores": [],
            "video_analysed": False,
        }
    )
    await simulations_collection.update_one(
        {"id": simulation_id}, {"$set": {"status": "analyzing"}}
    )

    try:
        transcript = await transcripts_collection.find_one(
            {"simulation_id": simulation_id}, {"_id": 0}
        )
        segments = (transcript or {}).get("segments", [])

        if len(segments) < MIN_SEGMENTS_FOR_REPORT:
            await reports_collection.update_one(
                {"id": report_id},
                {
                    "$set": {
                        "status": "failed",
                        "error": "This session was too short to report on.",
                    }
                },
            )
            await simulations_collection.update_one(
                {"id": simulation_id}, {"$set": {"status": "complete"}}
            )
            return

        by_id = {s["id"]: s for s in segments}
        competencies = await _load_rubric(DEFAULT_RUBRIC_ID)
        video_competencies = await _load_rubric(VIDEO_RUBRIC_ID)

        recording = await recordings_collection.find_one(
            {"simulation_id": simulation_id, "track": "camera"}, {"_id": 0}
        )

        # The transcript pass and the video pass are independent, so they run
        # together rather than one after the other. Video is much the slower
        # of the two.
        async def video_pass() -> list:
            if not recording or not video_competencies:
                return []
            try:
                data = await download_file(recording["file_id"])
            except Exception:
                return []
            return await analyse_video(
                data, recording.get("content_type", "video/webm"), video_competencies
            )

        moments, video_moments = await asyncio.gather(
            extract_moments(segments, competencies), video_pass()
        )

        # Resolve each extracted moment back to the real timestamps on its
        # segment. The model is not asked for times, only for which segment,
        # which removes a whole class of invented numbers.
        evidence = [
            {
                "competency_key": m.competency_key,
                "quote": m.quote,
                "ts_start": by_id[m.segment_id].get("ts_start", 0.0),
                "ts_end": by_id[m.segment_id].get("ts_end", 0.0),
                "speaker": by_id[m.segment_id].get("speaker", "trainer"),
                "source": "transcript",
                "positive": m.positive,
            }
            for m in moments
            if m.segment_id in by_id
        ]

        video_evidence = [
            {
                "competency_key": v.competency_key,
                "quote": v.observation,
                "ts_start": v.ts_s,
                "ts_end": v.ts_s,
                "speaker": "trainer",
                "source": "video",
                "positive": v.positive,
            }
            for v in video_moments
        ]

        spoken = await score_competencies(evidence, competencies)
        delivery = (
            await score_competencies(video_evidence, video_competencies)
            if video_evidence
            else None
        )

        labels = {c["key"]: c["label"] for c in competencies}
        video_labels = {c["key"]: c["label"] for c in video_competencies}

        def attach(scored, ev, label_map) -> list[dict]:
            return [
                {
                    "competency_key": s.competency_key,
                    "label": label_map.get(s.competency_key, s.competency_key),
                    "score": s.score,
                    "rationale": s.rationale,
                    "evidence": [
                        e for e in ev if e["competency_key"] == s.competency_key
                    ],
                }
                for s in scored.scores
            ]

        await reports_collection.update_one(
            {"id": report_id},
            {
                "$set": {
                    "status": "complete",
                    "scores": attach(spoken, evidence, labels),
                    "video_scores": (
                        attach(delivery, video_evidence, video_labels) if delivery else []
                    ),
                    "summary": spoken.summary,
                    "strengths": spoken.strengths,
                    "improvements": spoken.improvements,
                    "video_analysed": bool(video_evidence),
                }
            },
        )
        await simulations_collection.update_one(
            {"id": simulation_id}, {"$set": {"status": "complete"}}
        )

    except Exception as exc:
        await reports_collection.update_one(
            {"id": report_id},
            {"$set": {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}},
        )
        await simulations_collection.update_one(
            {"id": simulation_id}, {"$set": {"status": "failed"}}
        )


def schedule_analysis(simulation_id: str) -> None:
    """Start a report without waiting for it.

    The reference is dropped deliberately: the task outlives this call, and
    the report's own status field is how progress is tracked.
    """
    asyncio.create_task(run_analysis(simulation_id))
