import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, UploadFile

from main.agents.trainium.auth import User, get_current_admin
from main.agents.trainium.db_manager import courses_collection, teaching_graphs_collection
from main.agents.trainium.ingestion.pptx_extract import extract_slide_text
from main.agents.trainium.ingestion.slide_render import (
    extract_pdf_text,
    render_pdf_to_png,
    render_slides_to_png,
)
from main.agents.trainium.ingestion.teaching_graph import generate_teaching_graph
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

        # Both deck formats produce one slide per page and share everything
        # after extraction, so they differ only in how the pages are read.
        if kind in ("pptx", "pdf"):
            try:
                slides = (
                    await _ingest_pptx(course_id, content)
                    if kind == "pptx"
                    else await _ingest_pdf(course_id, content)
                )
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

    @app.post("/trainium/admin/courses/{course_id}/teaching-graph/generate")
    async def generate_course_teaching_graph(
        course_id: str, user: User = Depends(get_current_admin)
    ):
        course = await courses_collection.find_one({"id": course_id, "org_id": user.org_id})
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if not course.get("slides"):
            raise HTTPException(
                status_code=400, detail="Course has no ingested slides to generate from"
            )

        latest = await teaching_graphs_collection.find_one(
            {"course_id": course_id}, sort=[("version", -1)]
        )
        next_version = (latest["version"] + 1) if latest else 1

        graph = await generate_teaching_graph(course_id, course["slides"], next_version)
        await teaching_graphs_collection.insert_one(graph.model_dump())
        return graph

    @app.get("/trainium/admin/courses/{course_id}/teaching-graph")
    async def get_teaching_graph(
        course_id: str, version: int | None = None, user: User = Depends(get_current_admin)
    ):
        query = {"course_id": course_id}
        if version is not None:
            query["version"] = version
            graph = await teaching_graphs_collection.find_one(query, {"_id": 0})
        else:
            graph = await teaching_graphs_collection.find_one(
                query, {"_id": 0}, sort=[("version", -1)]
            )
        if graph is None:
            raise HTTPException(status_code=404, detail="Teaching graph not found")
        return graph

    @app.patch("/trainium/admin/courses/{course_id}/teaching-graph")
    async def edit_teaching_graph(
        course_id: str, body: dict, user: User = Depends(get_current_admin)
    ):
        latest = await teaching_graphs_collection.find_one(
            {"course_id": course_id}, sort=[("version", -1)]
        )
        if latest is None:
            raise HTTPException(status_code=404, detail="Teaching graph not found")

        next_version = latest["version"] + 1
        new_graph = {**latest, **body}
        new_graph.pop("_id", None)
        new_graph["version"] = next_version
        new_graph["approved_by"] = None
        new_graph["approved_at"] = None
        await teaching_graphs_collection.insert_one(new_graph)
        new_graph.pop("_id", None)
        return new_graph

    @app.post("/trainium/admin/courses/{course_id}/teaching-graph/approve")
    async def approve_teaching_graph(
        course_id: str, user: User = Depends(get_current_admin)
    ):
        latest = await teaching_graphs_collection.find_one(
            {"course_id": course_id}, sort=[("version", -1)]
        )
        if latest is None:
            raise HTTPException(status_code=404, detail="Teaching graph not found")

        await teaching_graphs_collection.update_one(
            {"course_id": course_id, "version": latest["version"]},
            {
                "$set": {
                    "approved_by": user.id,
                    "approved_at": datetime.now(timezone.utc),
                }
            },
        )
        return await teaching_graphs_collection.find_one(
            {"course_id": course_id, "version": latest["version"]}, {"_id": 0}
        )

    @app.post("/trainium/admin/courses/{course_id}/publish")
    async def publish_course(course_id: str, user: User = Depends(get_current_admin)):
        course = await courses_collection.find_one({"id": course_id, "org_id": user.org_id})
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")

        latest_graph = await teaching_graphs_collection.find_one(
            {"course_id": course_id}, sort=[("version", -1)]
        )
        if latest_graph is None or not latest_graph.get("approved_by"):
            raise HTTPException(
                status_code=400,
                detail="Course requires an approved teaching graph before publishing",
            )

        await courses_collection.update_one(
            {"id": course_id},
            {"$set": {"status": "published", "updated_at": datetime.now(timezone.utc)}},
        )
        return await courses_collection.find_one({"id": course_id}, {"_id": 0})


async def _ingest_pptx(course_id: str, pptx_bytes: bytes) -> list[SlideContent]:
    return await _store_slides(
        course_id, extract_slide_text(pptx_bytes), await render_slides_to_png(pptx_bytes)
    )


async def _ingest_pdf(course_id: str, pdf_bytes: bytes) -> list[SlideContent]:
    """One page becomes one slide.

    The PPTX path already converts to PDF before rasterising, so this is the
    same pipeline with the conversion step skipped. It also means a PDF needs
    no LibreOffice, which is one less thing to have installed.
    """
    return await _store_slides(
        course_id, extract_pdf_text(pdf_bytes), render_pdf_to_png(pdf_bytes)
    )


async def _store_slides(
    course_id: str, text_slides: list[dict], images: list[bytes]
) -> list[SlideContent]:
    """Pair extracted text with rendered images and put the images in GridFS."""
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
