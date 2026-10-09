"""Integration checks for page provenance, persistence, failures, and portable exports."""
import csv
import io
import asyncio

import fitz
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.research import Researcher
from backend.storage import Library
from backend import models


def pdf(*pages: str) -> bytes:
    document = fitz.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((50, 80), text)
        else:
            page.draw_rect(fitz.Rect(30, 30, 200, 200), color=(0.2, 0.3, 0.4), fill=(0.3, 0.3, 0.3))
    result = document.tobytes()
    document.close()
    return result


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXICAL_BOOTSTRAP_PDFS", "0")
    with TestClient(create_app(tmp_path)) as client:
        yield client


def test_multi_upload_duplicate_detection_actual_pages_and_selection(client):
    first = pdf("Opening unrelated page.", "Tatterbright: a strange beauty that survives ruin.")
    second = pdf("Tatterbright has another meaning in this document.")
    response = client.post("/api/sources", files=[("files", ("first.pdf", first, "application/pdf")), ("files", ("second.pdf", second, "application/pdf"))])
    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 2 and sources[0]["indexed_pages"] == 2
    matches = client.get("/api/sources/search", params={"q": "Tatterbright", "source_ids": sources[0]["id"]}).json()["matches"]
    assert len(matches) == 1
    assert matches[0]["page"] == 2 and matches[0]["document_id"] == sources[0]["id"]
    assert "strange beauty" in matches[0]["excerpt"]
    duplicate = client.post("/api/sources", files={"files": ("renamed.pdf", first, "application/pdf")}).json()
    assert len(duplicate["sources"]) == 2 and duplicate["uploaded"][0]["duplicate"] is True
    assert client.post(f"/api/sources/{sources[0]['id']}/reprocess").json()["source"]["indexed_pages"] == 2
    assert client.get(f"/api/sources/{sources[0]['id']}/file").content == first
    research = client.post("/api/research", json={"concept": "Tatterbright", "source_ids": [sources[0]["id"]], "include_web": False}).json()
    found = next(c for c in research["candidates"] if c["source_type"] == "pdf")
    assert found["source"]["page"] == 2
    assert found["source"]["document_id"] == sources[0]["id"]
    assert "Tatterbright" in found["source"]["excerpt"]
    assert found["evidence_status"] == "attested"
    assert client.delete(f"/api/sources/{sources[0]['id']}").status_code == 200
    assert client.get(f"/api/sources/{sources[0]['id']}/file").status_code == 404


def test_scanned_partial_corrupt_and_non_pdf_feedback(client):
    uploaded = client.post("/api/sources", files=[("files", ("scanned.pdf", pdf(""), "application/pdf")), ("files", ("partial.pdf", pdf("A page with searchable text.", ""), "application/pdf")), ("files", ("broken.pdf", b"%PDF-1.4\nbroken", "application/pdf"))]).json()
    states = {s["filename"]: s for s in uploaded["sources"]}
    assert states["scanned.pdf"]["status"] == "scanned" and "OCR" in states["scanned.pdf"]["warning"]
    assert states["partial.pdf"]["status"] == "partial" and states["partial.pdf"]["indexed_pages"] == 1
    assert states["broken.pdf"]["status"] == "error" and states["broken.pdf"]["warning"]
    assert client.post("/api/sources", files={"files": ("text.pdf", b"not a PDF", "application/pdf")}).status_code == 422


def test_local_analysis_forge_and_missing_model_configuration(client, monkeypatch):
    response = client.post("/api/analyze", json={"concept": "Familiar words made strange by contradictions"})
    assert response.status_code == 200 and response.json()["method"] == "local heuristic"
    forged = client.post("/api/forge", json={"concept": "Joy and grief together", "roots": [{"text": "joy", "language": "English", "meaning": "delight"}, {"text": "grief", "language": "English", "meaning": "sorrow"}], "level": "inventive", "count": 6}).json()["candidates"]
    assert len(forged) == 6
    assert all(c["evidence_status"] == "coined" and c["source_type"] == "coined" and c["components"] for c in forged)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LEXICAL_MODEL_API_KEY", raising=False)
    model = client.post("/api/analyze", json={"concept": "Power without contribution", "use_model": True})
    assert model.status_code == 503 and "OPENAI_API_KEY" in model.json()["detail"]
    assert client.post("/api/analyze", json={"concept": "   "}).status_code == 422


def test_network_failure_returns_partial_local_results(client, monkeypatch):
    async def unavailable(_language):
        raise httpx.ConnectError("A controlled connectivity failure")
    monkeypatch.setattr(client.app.state.researcher, "dictionary", unavailable)
    client.post("/api/sources", files={"files": ("local.pdf", pdf("Uncanny: the strange within the familiar."), "application/pdf")})
    response = client.post("/api/research", json={"concept": "uncanny strange familiar", "languages": ["English"], "include_web": True})
    assert response.status_code == 200
    assert any("retrieval unavailable" in warning for warning in response.json()["warnings"])
    assert any(c["source_type"] == "pdf" for c in response.json()["candidates"])


def test_projects_and_sources_persist_across_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXICAL_BOOTSTRAP_PDFS", "0")
    with TestClient(create_app(tmp_path)) as first:
        uploaded = first.post("/api/sources", files={"files": ("persistent.pdf", pdf("Remembering is an act of transformation."), "application/pdf")}).json()["sources"][0]
        project = first.post("/api/projects", json={"name": "Memory laboratory", "concept": "Memory as transformation", "shortlist": ["candidate-one"], "notes": {"candidate-one": "Review sense"}}).json()
    with TestClient(create_app(tmp_path)) as second:
        assert second.get("/api/sources").json()["sources"][0]["id"] == uploaded["id"]
        restored = second.get("/api/projects/" + project["id"]).json()
        assert restored["shortlist"] == ["candidate-one"] and restored["notes"]["candidate-one"] == "Review sense"
        assert len(second.get("/api/projects").json()["projects"]) == 1
        assert second.delete("/api/projects/" + project["id"]).status_code == 200
        assert second.get("/api/projects/" + project["id"]).status_code == 404


def test_exports_preserve_unicode_evidence_citations_notes_and_components(client):
    candidate = {"id": "c1", "term": "中文 κόσμος", "language": "Chinese / Greek", "definition": "An experimental collision.", "evidence_status": "coined", "source_type": "coined", "source": {"title": "Fixture source", "document_id": "actual-id", "page": 7, "excerpt": "Only this observed excerpt.", "url": "https://example.org/source", "accessed_at": "2026-10-09"}, "components": [{"text": "κόσμος", "language": "Greek", "meaning": "world / order"}], "caveat": "A test fixture, not a claimed attestation."}
    project = {"name": "Unicode workshop", "concept": "Familiarity and strangeness", "candidates": [candidate], "shortlist": ["c1"], "notes": {"c1": "Keep the caveat."}}
    markdown = client.post("/api/export", json={"format": "markdown", "project": project})
    assert markdown.status_code == 200 and "中文 κόσμος" in markdown.text
    assert "PDF page 7" in markdown.text and "coined" in markdown.text and "Keep the caveat." in markdown.text
    csv_response = client.post("/api/export", json={"format": "csv", "project": project})
    row = next(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert row["evidence_status"] == "coined" and row["page"] == "7" and row["document_id"] == "actual-id"
    assert row["annotation"] == "Keep the caveat." and row["shortlisted"] == "True"
    rendered = client.post("/api/export", json={"format": "pdf", "project": project})
    assert rendered.headers["content-type"] == "application/pdf"
    with fitz.open(stream=rendered.content, filetype="pdf") as document:
        text = " ".join(page.get_text() for page in document)
    assert "中文 κόσμος" in text and "PDF page 7" in text and "coined" in text and "Keep the caveat." in text


def test_freedict_parsing_retains_dictionary_direction_and_evidence(tmp_path):
    researcher = Researcher(Library(tmp_path))
    normal = '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><entry><form><orth>limen</orth></form><sense><cit type="trans"><quote>threshold</quote></cit></sense></entry></text></TEI>'
    assert researcher.parse_dictionary("Latin", normal)[0]["definition"] == "threshold"
    reverse = '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><entry><form><orth>transformation</orth></form><sense><def>μεταμόρφωση</def></sense></entry></text></TEI>'
    entry = researcher.parse_dictionary("Greek", reverse)[0]
    assert entry["term"] == "μεταμόρφωση" and "transformation" in entry["definition"]
    assert entry["excerpt"] == "μεταμόρφωση"
    spellings = researcher.parse_dictionary("German", "2\nSchadenfreude/Nm\nFremdheit/Pm\n")
    assert spellings["schadenfreude"] == {"term": "Schadenfreude", "excerpt": "Schadenfreude/Nm"}


def test_pdf_entry_parser_does_not_promote_grammatical_headings_to_words():
    text = "Verb · root-toil · source PDF p. 27\nroot-toil 'to work and suffer'\nNominal · source PDF p. 29\nA grammatical heading only."
    entries = Library._extract_entries("fixture", "Comparative_Ancient_Language_Lexicon.pdf", 3, text, "Old Avestan")
    assert [entry["term"] for entry in entries] == ["root-toil"]
    assert entries[0]["evidence_status"] == "attested"


def test_optional_model_rejects_malformed_output_and_forces_coined_provenance(monkeypatch):
    async def invalid(*_):
        return {"candidates": "not a list"}
    monkeypatch.setattr(models, "completion", invalid)
    with pytest.raises(models.ModelUnavailable):
        asyncio.run(models.forge({"concept": "Curious language", "count": 3, "roots": []}))
    async def proposal(*_):
        return {"candidates": [
            {"term": "   ", "definition": "Empty term", "components": []},
            {"term": "Curiositymud", "definition": "Curiosity made material.", "evidence_status": "historically_attested", "source": {"url": "https://fake.example/author"}, "components": [{"text": "curiosity", "language": "English", "meaning": "desire to know"}, {"text": "mud", "language": "English", "meaning": "wet earth"}], "tone": {"wrong": "type"}},
            {"term": "Badcomponents", "definition": "Invalid construction explanation", "components": "wrong type"},
        ]}
    monkeypatch.setattr(models, "completion", proposal)
    candidates = asyncio.run(models.forge({"concept": "Curious language", "count": 3, "roots": []}))
    assert len(candidates) == 1 and candidates[0]["evidence_status"] == "coined"
    assert "url" not in candidates[0]["source"] and isinstance(candidates[0]["tone"], str)
    assert candidates[0]["components"][0]["text"] == "curiosity"


def test_ancient_greek_selection_never_relabels_modern_greek(client, monkeypatch):
    called = []
    async def dictionary(language):
        called.append(language)
        return [], "test-date"
    monkeypatch.setattr(client.app.state.researcher, "dictionary", dictionary)
    result = client.post("/api/research", json={"concept": "transformation", "languages": ["Ancient Greek"], "include_web": True}).json()
    assert "Greek" not in called
    assert not any(candidate["language"] == "Modern Greek" for candidate in result["candidates"])


def test_german_spelling_does_not_verify_an_editorial_definition(client, monkeypatch):
    researcher = client.app.state.researcher
    seed = {"id": "editorial-schuld", "term": "Schuld", "language": "German", "definition": "An editorial proposed connection to guilt and debt.", "tone": "philosophical", "evidence_status": "unverified", "source_type": "dictionary", "source": {"title": "Unverified test lead"}, "tags": ["guilt", "debt"], "captures": "An interpretation to inspect.", "misses": "No verified source for this test sense."}
    monkeypatch.setattr(researcher, "seeds", lambda: [seed])
    async def dictionary(language):
        assert language == "German"
        return {"schuld": {"term": "Schuld", "excerpt": "Schuld/ijm"}}, "test-date"
    monkeypatch.setattr(researcher, "dictionary", dictionary)
    result = client.post("/api/research", json={"concept": "guilt and debt", "languages": ["German"], "include_web": True}).json()
    candidates = [c for c in result["candidates"] if c["term"] == "Schuld"]
    assert len(candidates) == 2
    spelling = next(c for c in candidates if c.get("spelling_only"))
    editorial = next(c for c in candidates if not c.get("spelling_only"))
    assert spelling["evidence_status"] == "attested" and "no meaning" in spelling["definition"]
    assert editorial["evidence_status"] == "unverified"
