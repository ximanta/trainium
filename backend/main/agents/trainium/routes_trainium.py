import asyncio
import io
import uuid
import wave
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Response
from google import genai
from google.genai import types

from main.agents.trainium.auth import User, get_current_admin, get_current_user
from main.agents.trainium.db_manager import (
    persona_templates_collection,
    rubrics_collection,
    scenarios_collection,
)
from main.agents.trainium.models import Rubric
from main.agents.trainium.routes_courses import configure_routes_courses
from main.agents.trainium.storage import download_file
from main.agents.trainium.voices import (
    PREVIEW_LINE,
    VOICE_BY_ID,
    VOICE_CATALOGUE,
    accent_prompt_for_voice,
)
from main.config import settings


def configure_routes_trainium(app: FastAPI) -> None:
    configure_routes_courses(app)

    @app.get("/trainium/health")
    async def health():
        return {"status": "ok", "agent": "trainium"}

    @app.get("/trainium/assets/{file_id}")
    async def get_asset(file_id: str, user: User = Depends(get_current_user)):
        content = await download_file(file_id)
        return Response(content=content, media_type="image/png")

    @app.get("/trainium/personas")
    async def list_personas(user: User = Depends(get_current_user)):
        cursor = persona_templates_collection.find({}, {"_id": 0})
        return await cursor.to_list(length=None)

    @app.get("/trainium/scenarios")
    async def list_scenarios(user: User = Depends(get_current_user)):
        cursor = scenarios_collection.find({}, {"_id": 0})
        return await cursor.to_list(length=None)

    @app.get("/trainium/voices")
    async def list_voices(user: User = Depends(get_current_user)):
        return [v.as_dict() for v in VOICE_CATALOGUE]

    @app.get("/trainium/voices/{voice_id}/preview")
    async def preview_voice(voice_id: str, user: User = Depends(get_current_user)):
        """Speak a fixed sample line in `voice_id`, for the admin voice picker.

        Runs the same accent steering as a live session, so what the admin hears
        is what the trainer will hear.
        """
        if voice_id not in VOICE_BY_ID:
            raise HTTPException(status_code=404, detail="Unknown voice")

        client = genai.Client(api_key=settings.gemini_api_key)
        try:
            result = await asyncio.to_thread(
                client.models.generate_content,
                model=settings.gemini_model_tts,
                contents=accent_prompt_for_voice(PREVIEW_LINE, voice_id),
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_id)
                        )
                    ),
                ),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Voice preview failed: {exc}") from exc

        parts = result.candidates[0].content.parts if result.candidates else []
        pcm = next((p.inline_data.data for p in parts if p.inline_data), None)
        if not pcm:
            raise HTTPException(status_code=502, detail="Voice preview returned no audio")

        # Gemini returns headerless 24kHz mono 16-bit PCM. Wrap it as WAV so an
        # <audio> element can play it without client-side decoding.
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        return Response(
            content=buffer.getvalue(),
            media_type="audio/wav",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/trainium/admin/whoami")
    async def admin_whoami(user: User = Depends(get_current_admin)):
        return user

    # Rubrics. Read is available to any authenticated user, so the trainer
    # side can show what a session will be evaluated against. Write is
    # admin only.

    @app.get("/trainium/rubrics")
    async def list_rubrics(user: User = Depends(get_current_user)):
        cursor = rubrics_collection.find({}, {"_id": 0})
        return await cursor.to_list(length=None)

    @app.get("/trainium/rubrics/{rubric_id}")
    async def get_rubric(rubric_id: str, user: User = Depends(get_current_user)):
        rubric = await rubrics_collection.find_one({"id": rubric_id}, {"_id": 0})
        if rubric is None:
            raise HTTPException(status_code=404, detail="Rubric not found")
        return rubric

    @app.post("/trainium/admin/rubrics")
    async def create_rubric(body: Rubric, user: User = Depends(get_current_admin)):
        rubric = body.model_copy(
            update={
                "id": body.id or f"rubric_{uuid.uuid4().hex[:12]}",
                "org_id": user.org_id,
                "created_by": user.id,
                "status": "draft",
                "version": 1,
            }
        )
        await rubrics_collection.insert_one(rubric.model_dump())
        return rubric

    @app.patch("/trainium/admin/rubrics/{rubric_id}")
    async def update_rubric(
        rubric_id: str, body: dict, user: User = Depends(get_current_admin)
    ):
        existing = await rubrics_collection.find_one({"id": rubric_id})
        if existing is None:
            raise HTTPException(status_code=404, detail="Rubric not found")
        body.pop("id", None)
        body.pop("org_id", None)
        body.pop("created_by", None)
        body["updated_at"] = datetime.now(timezone.utc)
        await rubrics_collection.update_one({"id": rubric_id}, {"$set": body})
        updated = await rubrics_collection.find_one({"id": rubric_id}, {"_id": 0})
        return updated

    @app.post("/trainium/admin/rubrics/{rubric_id}/publish")
    async def publish_rubric(rubric_id: str, user: User = Depends(get_current_admin)):
        existing = await rubrics_collection.find_one({"id": rubric_id})
        if existing is None:
            raise HTTPException(status_code=404, detail="Rubric not found")
        if not existing.get("competencies"):
            raise HTTPException(
                status_code=400, detail="Cannot publish a rubric with no competencies"
            )
        await rubrics_collection.update_one(
            {"id": rubric_id},
            {"$set": {"status": "published", "updated_at": datetime.now(timezone.utc)}},
        )
        updated = await rubrics_collection.find_one({"id": rubric_id}, {"_id": 0})
        return updated
