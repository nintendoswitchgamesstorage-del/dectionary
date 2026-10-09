"""Checks for the same-origin desktop server and persistent starter resources."""
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from desktop.launcher import make_app, prepare_library
from desktop.prepare import FILENAMES, prepare


def test_desktop_serves_built_interface_and_api(tmp_path, monkeypatch):
    root = tmp_path / "bundle"
    (root / "dist").mkdir(parents=True)
    (root / "dist" / "index.html").write_text('<div id="root">Desktop interface</div>')
    (root / "dist" / "assets").mkdir()
    (root / "dist" / "assets" / "sample.js").write_text("console.log('bundled')")
    with patch("desktop.launcher.bundle_root", return_value=root):
        app = make_app(tmp_path / "user-data", root / "resources")
    with TestClient(app) as client:
        assert "Desktop interface" in client.get("/").text
        assert client.get("/assets/sample.js").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"
        result = client.post("/api/forge", json={"concept": "Hungry flowers", "roots": [{"text": "hunger", "language": "English", "meaning": "appetite"}, {"text": "bloom", "language": "English", "meaning": "flowering"}], "count": 3}).json()
        assert len(result["candidates"]) == 3
        assert all(c["evidence_status"] == "coined" for c in result["candidates"])
        assert client.get("/../backend/models.py").status_code == 404


def test_starter_import_is_repeatable_and_respects_user_removal(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXICAL_BOOTSTRAP_PDFS", "0")
    from backend.app import create_app
    resources = tmp_path / "resources"
    (resources / "starter-pdfs").mkdir(parents=True)
    for name in FILENAMES:
        with fitz.open() as pdf:
            pdf.new_page().insert_text((40, 60), f"Actual starter text: {name}")
            pdf.save(resources / "starter-pdfs" / name)
    (resources / "dictionaries").mkdir()
    (resources / "dictionaries" / "example.json").write_text('{"term":"a real cache"}')
    app = create_app(tmp_path / "persistent")
    prepare_library(app, resources)
    assert len(app.state.library.sources()) == 2
    prepare_library(app, resources)
    assert len(app.state.library.sources()) == 2
    source_id = app.state.library.sources()[0]["id"]
    app.state.library.delete(source_id)
    prepare_library(app, resources)
    assert len(app.state.library.sources()) == 1
    assert (tmp_path / "persistent" / "dictionaries" / "example.json").exists()


def test_packaging_excludes_projects_other_uploads_and_secret_files(tmp_path):
    data = tmp_path / "existing"
    (data / "dictionaries").mkdir(parents=True)
    (data / "lexical.sqlite3").write_text("private project notes")
    (data / "dictionaries" / "credential.env").write_text("do not package")
    (data / "dictionaries" / "webster.json").write_text('{"word":"test definition"}')
    paths = []
    for name in FILENAMES:
        path = tmp_path / name
        path.write_bytes(b"%PDF test starter")
        paths.append(path)
    destination = tmp_path / "staged"
    manifest = prepare(paths, data, destination)
    assert len(manifest) == 4
    assert not any("credential" in str(p) or "sqlite" in str(p) for p in destination.rglob("*"))
    assert all(len(record["sha256"]) == 64 for record in manifest)
