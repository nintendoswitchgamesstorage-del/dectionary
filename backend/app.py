"""FastAPI entry point: uvicorn backend.app:app --host 0.0.0.0 --port 8000."""
from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import exports, models
from .research import Researcher, analyze_local
from .storage import MAX_UPLOAD_BYTES, Library


class ConceptRequest(BaseModel):
    concept: str = Field(min_length=1, max_length=6000)
    use_model: bool = False


class ResearchRequest(ConceptRequest):
    interpretation: str | dict[str, Any] | None = None
    languages: list[str] = Field(default_factory=list, max_length=60)
    source_ids: list[str] = Field(default_factory=list, max_length=200)
    include_web: bool = False
    include_games: bool = True
    dimensions: list[dict[str, Any]] = Field(default_factory=list, max_length=30)


class ForgeRequest(ConceptRequest):
    roots: list[dict[str, Any] | str] = Field(default_factory=list, max_length=20)
    level: str = "inventive"
    count: int = Field(default=8, ge=1, le=30)
    seed: int | str | None = None


class ProjectRequest(BaseModel):
    model_config = {"extra": "allow"}
    id: str | None = None
    name: str = Field(default="Untitled experiment", max_length=200)
    concept: str = Field(default="", max_length=6000)
    analysis: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    shortlist: list[Any] = Field(default_factory=list)
    notes: str | dict[str, Any] = ""
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    forge_history: list[Any] = Field(default_factory=list)


class ExportRequest(BaseModel):
    format: str
    project: dict[str, Any]


def create_app(directory: Path | str | None = None) -> FastAPI:
    library = Library(directory)
    researcher = Researcher(library)

    @asynccontextmanager
    async def lifespan(_app):
        await asyncio.to_thread(library.bootstrap)
        yield

    app = FastAPI(title="Lexical Alchemy", version="0.1.0", lifespan=lifespan)
    app.state.library = library
    app.state.researcher = researcher
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"], allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local", "source_count": len(library.sources()), "privacy": "PDF extraction, indexing, and default research stay on this machine."}

    @app.get("/api/providers")
    def providers():
        model = models.provider_status()
        dictionaries = researcher.providers()
        return {"model": model, "dictionary": dictionaries, "providers": [model, *dictionaries], "ocr": {"available": False, "warning": "OCR is not bundled. Run a local OCR tool and upload the searchable output."}}

    @app.get("/api/sources")
    def sources():
        return {"sources": library.sources()}

    @app.post("/api/sources")
    async def upload(files: Annotated[list[UploadFile], File()]):
        if len(files) > 20:
            raise HTTPException(413, "Upload at most 20 PDFs at a time.")
        uploaded, warnings = [], []
        for file in files:
            try:
                content = await file.read(MAX_UPLOAD_BYTES + 1)
                result = await asyncio.to_thread(library.ingest, file.filename or "untitled.pdf", content)
                uploaded.append(result)
                if result.get("duplicate"):
                    warnings.append(f"{file.filename}: an identical PDF is already in the library; the existing document was reused.")
                elif result.get("warning"):
                    warnings.append(f"{file.filename}: {result['warning']}")
            except ValueError as error:
                warnings.append(str(error))
            finally:
                await file.close()
        if not uploaded and warnings:
            raise HTTPException(422, " ".join(warnings))
        return {"sources": library.sources(), "uploaded": uploaded, "warnings": warnings}

    @app.get("/api/sources/search")
    def search(q: str = Query(max_length=1500), source_ids: str = Query(default="", max_length=7000)):
        ids = [part for part in source_ids.split(",") if part]
        return {"matches": library.search(q, ids)}

    @app.delete("/api/sources/{source_id}")
    def remove_source(source_id: str):
        try:
            library.delete(source_id)
        except (KeyError, ValueError):
            raise HTTPException(404, "Document not found.")
        return {"deleted": source_id}

    @app.post("/api/sources/{source_id}/reprocess")
    def reprocess(source_id: str):
        try:
            source = library.reprocess(source_id)
        except KeyError:
            raise HTTPException(404, "Document not found.")
        return {"source": source, "sources": library.sources()}

    @app.get("/api/sources/{source_id}/file")
    def download_source(source_id: str):
        source = library.get_source(source_id)
        if not source:
            raise HTTPException(404, "Document not found.")
        path = library.file_path(source_id)
        if not path.exists():
            raise HTTPException(404, "The stored PDF is missing. Upload it again.")
        return FileResponse(path, media_type="application/pdf", filename=source["filename"], content_disposition_type="inline")

    @app.post("/api/analyze")
    async def analyze(request: ConceptRequest):
        if not request.concept.strip():
            raise HTTPException(422, "Describe a concept before analyzing it.")
        if request.use_model:
            try:
                return await models.analyze(request.concept)
            except models.ModelUnavailable as error:
                raise HTTPException(503, str(error))
        return analyze_local(request.concept)

    @app.post("/api/research")
    async def research(request: ResearchRequest):
        if not request.concept.strip():
            raise HTTPException(422, "Describe a concept before researching it.")
        if request.use_model:
            raise HTTPException(422, "Research retrieval and scoring currently use the local lexical engine. Model mode is available for concept interpretation and the forge; no document content is sent to a model.")
        return await researcher.research(request.model_dump())

    @app.post("/api/forge")
    async def forge(request: ForgeRequest):
        if not request.concept.strip():
            raise HTTPException(422, "Describe a concept before making words.")
        if request.use_model:
            try:
                return {"candidates": await models.forge(request.model_dump()), "method": "OpenAI coinage proposals"}
            except models.ModelUnavailable as error:
                raise HTTPException(503, str(error))
        from .forge import generate
        try:
            return {"candidates": generate(request.model_dump()), "method": "local rule-based transformations"}
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.get("/api/projects")
    def projects():
        return {"projects": library.projects()}

    @app.post("/api/projects")
    def save_project(request: ProjectRequest):
        try:
            return library.save_project(request.model_dump())
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.get("/api/projects/{project_id}")
    def project(project_id: str):
        value = library.project(project_id)
        if value is None:
            raise HTTPException(404, "Project not found.")
        return value

    @app.delete("/api/projects/{project_id}")
    def remove_project(project_id: str):
        try:
            library.delete_project(project_id)
        except KeyError:
            raise HTTPException(404, "Project not found.")
        return {"deleted": project_id}

    @app.post("/api/export")
    def export(request: ExportRequest):
        formats = {"markdown": (exports.markdown, "text/markdown; charset=utf-8", "md"), "csv": (exports.csv_export, "text/csv; charset=utf-8", "csv"), "pdf": (exports.pdf_export, "application/pdf", "pdf")}
        if request.format not in formats:
            raise HTTPException(422, "Choose markdown, csv, or pdf export.")
        render, mime, extension = formats[request.format]
        name = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(request.project.get("name") or "lexical-alchemy")).strip("-")[:70] or "lexical-alchemy"
        return Response(render(request.project), media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}.{extension}"'})

    return app


app = create_app()
