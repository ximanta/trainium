import uuid

from main.agents.trainium.db_manager import events_collection, transcripts_collection

# 16MB Mongo document limit guard (architecture doc §data model: "note the
# limit in code with an explicit guard rather than discovering it in
# production"). A 30-minute transcript is ~300-500 segments; this is a
# generous ceiling before that becomes a real risk.
MAX_SEGMENTS_PER_TRANSCRIPT = 5000


async def append_transcript_segment(
    simulation_id: str,
    speaker: str,
    ts_start: float,
    ts_end: float,
    text: str,
    slide: int | None = None,
) -> None:
    segment = {
        "id": f"seg_{uuid.uuid4().hex[:12]}",
        "speaker": speaker,
        "ts_start": ts_start,
        "ts_end": ts_end,
        "text": text,
        "slide": slide,
    }

    existing = await transcripts_collection.find_one(
        {"simulation_id": simulation_id}, {"segments": {"$slice": -1}, "_id": 1}
    )
    if existing is None:
        await transcripts_collection.insert_one(
            {
                "simulation_id": simulation_id,
                "version": 1,
                "stt_provider": "gemini-3.5-transcribe-live",
                "segments": [segment],
                "word_count": len(text.split()),
            }
        )
        return

    count = await transcripts_collection.count_documents(
        {"simulation_id": simulation_id, "segments": {"$size": MAX_SEGMENTS_PER_TRANSCRIPT}}
    )
    if count:
        # Guard hit: this session's transcript needs to move to a
        # split-segment design (per the doc's >60min note) before more
        # segments can be appended safely. Fail loudly rather than silently
        # truncating or blowing the 16MB document limit.
        raise RuntimeError(
            f"Transcript for simulation {simulation_id} hit the "
            f"{MAX_SEGMENTS_PER_TRANSCRIPT}-segment guard; needs a split-collection design."
        )

    await transcripts_collection.update_one(
        {"simulation_id": simulation_id},
        {
            "$push": {"segments": segment},
            "$inc": {"word_count": len(text.split())},
        },
    )


async def append_event(
    simulation_id: str, ts_s: float, kind: str, actor: str, persona_id: str | None, payload: dict
) -> None:
    await events_collection.insert_one(
        {
            "simulation_id": simulation_id,
            "ts_s": ts_s,
            "kind": kind,
            "actor": actor,
            "persona_id": persona_id,
            "payload": payload,
        }
    )
