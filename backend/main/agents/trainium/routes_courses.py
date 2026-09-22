import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, UploadFile

from main.agents.trainium.auth import User, get_current_admin
from main.agents.trainium.db_manager import courses_collection
from main.agents.trainium.ingestion.pptx_extract import extract_slide_text
from main.agents.trainium.ingestion.slide_render import render_slides_to_png
from main.agents.trainium.models import Course, CourseAsset, SlideContent
from main.agents.trainium.storage import upload_file


def configure_routes_courses(app: FastAPI) -> None:
    @app.post("/trainium/admin/courses")
    async def create_course(
        body: dict, user: User = Depends(get_current_admin)
    ):
        course = Course(
            id=f"course_{uuid.uuid4().hex[:12]}",
            org_id=user.org_id,
            owner_id=user.id,
            title=body.get("title", "Untitled course"),
            description=body.get("description", ""),
        )
        await courses_collection.insert_one(course.model_dump())
        return course

    @app.get("/trainium/admin/courses")
    async def list_courses(user: User = Depends(get_current_admin)):
        cursor = courses_collection.find({"org_id": user.org_id}, {"_id": 0, "slides": 0})
        return await cursor.to_list(length=None)

    @app.get("/trainium/admin/courses/{course_id}")
    async def get_course(course_id: str, user: User = Depends(get_current_admin)):
        course = await courses_collection.find_one(
            {"id": course_id, "org_id": user.org_id}, {"_id": 0}
        )
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        return course

    @app.post("/trainium/admin/courses/{course_id}/assets")
    async def upload_course_asset(
        course_id: str,
        file: UploadFile,
        kind: str = "pptx",
        user: User = Depends(get_current_admin),
    ):
        course = await courses_collection.find_one({"id": course_id, "org_id": user.org_id})
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")

        content = await file.read()
        sha256 = hashlib.sha256(content).hexdigest()
        file_id = await upload_file(file.filename, content, file.content_type or "")

        asset = CourseAsset(
            kind=kind,
            file_id=file_id,
            filename=file.filename,
            size_bytes=len(content),
            sha256=sha256,
        )

        await courses_collection.update_one(
            {"id": course_id},
            {
                "$push": {"assets": asset.model_dump()},
                "$set": {"status": "ingesting", "updated_at": datetime.now(timezone.utc)},
            },
        )

        if kind == "pptx":
            try:
                slides = await _ingest_pptx(course_id, content)
                await courses_collection.update_one(
                    {"id": course_id},
                    {
                        "$set": {
                            "slides": [s.model_dump() for s in slides],
                            "status": "draft",
                            "ingest_error": None,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
            except Exception as exc:
                await courses_collection.update_one(
                    {"id": course_id},
                    {
                        "$set": {
                            "status": "failed",
                            "ingest_error": str(exc),
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                raise HTTPException(
                    status_code=422, detail=f"Ingestion failed: {exc}"
                ) from exc

        updated = await courses_collection.find_one(
            {"id": course_id}, {"_id": 0}
        )
        return updated


async def _ingest_pptx(course_id: str, pptx_bytes: bytes) -> list[SlideContent]:
    text_slides = extract_slide_text(pptx_bytes)
    images = await render_slides_to_png(pptx_bytes)

    slides = []
    for text_slide, image_bytes in zip(text_slides, images):
        image_file_id = await upload_file(
            f"{course_id}_slide_{text_slide['slide_number']}.png",
            image_bytes,
            "image/png",
        )
        slides.append(
            SlideContent(
                slide_number=text_slide["slide_number"],
                title=text_slide["title"],
                body=text_slide["body"],
                notes=text_slide["notes"],
                image_file_id=image_file_id,
            )
        )
    return slides
