"""Local, page-aware source storage. Nothing here sends documents to a provider."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import fitz

ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
MAX_PAGES = 1500


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\x00", "")).strip()


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text.casefold(), re.UNICODE) if len(w) > 1]


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn")


def excerpt(text: str, query: str = "", limit: int = 380) -> str:
    text = clean(text)
    needles = tokens(query)
    at = next((text.casefold().find(w) for w in needles if w in text.casefold()), 0)
    start = max(0, at - 95)
    end = min(len(text), start + limit)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


class Library:
    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory or os.getenv("LEXICAL_DATA_DIR", ROOT / ".data"))
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "sources").mkdir(exist_ok=True)
        self.db_path = self.directory / "lexical.sqlite3"
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL, page_count INTEGER DEFAULT 0,
                    indexed_pages INTEGER DEFAULT 0, warning TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pages (
                    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    page INTEGER NOT NULL, text TEXT NOT NULL,
                    PRIMARY KEY(source_id,page)
                );
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    page INTEGER NOT NULL, term TEXT NOT NULL, language TEXT NOT NULL,
                    definition TEXT NOT NULL, excerpt TEXT NOT NULL, evidence_status TEXT NOT NULL,
                    caveat TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, updated_at TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def sources(self) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT id,filename,status,page_count,indexed_pages,warning,created_at FROM sources ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def get_source(self, source_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        return dict(row) if row else None

    def file_path(self, source_id: str) -> Path:
        # Storage names come from our UUIDs, never from client filenames.
        if not re.fullmatch(r"[a-f0-9]{32}", source_id):
            raise ValueError("Invalid document identifier.")
        return self.directory / "sources" / f"{source_id}.pdf"

    def ingest(self, filename: str, content: bytes) -> dict:
        filename = clean(Path(filename.replace("\\", "/")).name)[:200] or "untitled.pdf"
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("Each PDF must be 32 MiB or smaller.")
        if b"%PDF-" not in content[:1024]:
            raise ValueError(f"{filename}: the file is not a PDF.")
        digest = hashlib.sha256(content).hexdigest()
        with self.lock, self.connection() as db:
            previous = db.execute("SELECT id FROM sources WHERE sha256=?", (digest,)).fetchone()
            if previous:
                result = self.get_source(previous["id"])
                result["duplicate"] = True
                return result
            source_id = uuid4().hex
            self.file_path(source_id).write_bytes(content)
            db.execute("INSERT INTO sources(id,filename,sha256,status,created_at) VALUES(?,?,?,?,?)", (source_id, filename, digest, "processing", now()))
        return self.reprocess(source_id)

    def reprocess(self, source_id: str) -> dict:
        source = self.get_source(source_id)
        if not source:
            raise KeyError(source_id)
        pages: list[tuple[int, str]] = []
        entries: list[dict] = []
        page_count = 0
        warning = None
        status = "error"
        try:
            with fitz.open(self.file_path(source_id)) as document:
                page_count = len(document)
                if document.needs_pass:
                    raise ValueError("Password-protected PDF: upload a decrypted copy.")
                if page_count > MAX_PAGES:
                    raise ValueError(f"This local index supports at most {MAX_PAGES} pages per PDF.")
                section = "Unknown"
                for index, page in enumerate(document):
                    try:
                        text = page.get_text("text", sort=True).replace("\x00", "")
                    except Exception:
                        text = ""
                    pages.append((index + 1, text))
                    if "PART I · OLD TURKIC" in text:
                        section = "Old Turkic"
                    elif "PART II · OLD AVESTAN" in text:
                        section = "Old Avestan"
                    elif "PART III · ENGLISH TO OLD NORSE" in text or "Inverse Old Norse" in text:
                        section = "Old Norse"
                    entries.extend(self._extract_entries(source_id, source["filename"], index + 1, text, section))
            indexed = sum(len(clean(text)) >= 10 for _, text in pages)
            if not indexed:
                status = "scanned"
                warning = "No searchable text was extracted. This may be an image-only or scanned PDF. OCR is not enabled; run local OCR (for example, ocrmypdf input.pdf output.pdf) and upload the searchable output."
            elif indexed < page_count:
                status = "partial"
                warning = f"Text extracted from {indexed} of {page_count} pages. Other pages may be blank, scanned, or unreadable; local OCR may be needed."
            else:
                status = "ready"
        except Exception as error:
            indexed = 0
            pages = []
            entries = []
            warning = str(error)[:500]
        with self.lock, self.connection() as db:
            db.execute("DELETE FROM pages WHERE source_id=?", (source_id,))
            db.execute("DELETE FROM entries WHERE source_id=?", (source_id,))
            db.executemany("INSERT INTO pages(source_id,page,text) VALUES(?,?,?)", [(source_id, page, text) for page, text in pages])
            db.executemany("INSERT OR IGNORE INTO entries(id,source_id,page,term,language,definition,excerpt,evidence_status,caveat) VALUES(?,?,?,?,?,?,?,?,?)", [tuple(entry[k] for k in ("id", "source_id", "page", "term", "language", "definition", "excerpt", "evidence_status", "caveat")) for entry in entries])
            db.execute("UPDATE sources SET status=?,page_count=?,indexed_pages=?,warning=? WHERE id=?", (status, page_count, indexed, warning, source_id))
        return self.get_source(source_id)

    @staticmethod
    def _extract_entries(source_id: str, filename: str, page: int, text: str, section: str) -> list[dict]:
        """Recognize supplied lexicon layouts, with provenance in the uploaded PDF itself."""
        items: list[dict] = []

        def add(term: str, definition: str, body: str, language: str, status: str, caveat: str):
            term = clean(term)
            if not term or len(term) > 100 or len(clean(definition)) < 3:
                return
            items.append({"id": "pdf-" + hashlib.sha256(f"{source_id}:{page}:{term}".encode()).hexdigest()[:18], "source_id": source_id, "page": page, "term": term, "language": language, "definition": clean(definition)[:500], "excerpt": excerpt(body), "evidence_status": status, "caveat": caveat})

        if filename == "Language_in_Mutation_Rabelais_Joyce_Nietzsche.pdf":
            headings = list(re.finditer(r"(?m)^([RJN]\d{2})\s+([^\n]+)$", text))
            for i, match in enumerate(headings):
                body = text[match.start():headings[i + 1].start() if i + 1 < len(headings) else len(text)]
                meaning = re.search(r"MEANING\s+(.*?)(?:WHAT MUTATES|NEW ILLUSTRATIVE|IN THE UPLOADED|$)", body, re.S)
                if meaning:
                    language = "French" if match[1][0] == "R" else "English"
                    if match[1][0] == "N" and re.search(r"[äöüß]|Über|Hinter", match[2]):
                        language = "German"
                    add(match[2], meaning[1], body, language, "attested", "Attested in the supplied secondary guide. Its historical attribution, roots, and translator choices have not been independently checked against the primary editions. Its illustrative sentences are newly written examples.")
        elif filename == "Comparative_Ancient_Language_Lexicon.pdf":
            if section in ("Old Turkic", "Old Avestan"):
                headings = list(re.finditer(r"(?m)^([^\n]+?)\s*·\s*source PDF p\.\s*\d+\s*$", text))
                for i, match in enumerate(headings):
                    body = text[match.end():headings[i + 1].start() if i + 1 < len(headings) else len(text)]
                    fields = [clean(part) for part in match[1].split("·")]
                    categories = {"verb", "verbs", "pronoun", "nominal", "noun", "adjective", "adverb", "etymology", "cross-reference", "particle", "preposition", "conjunction"}
                    term = fields[1] if fields[0].casefold() in categories and len(fields) > 1 else fields[0]
                    if term.casefold() in categories:
                        continue
                    quote = re.search(r"[‘']([^’']{3,220})[’']", body)
                    definition = quote[1] if quote else clean(body)[:240]
                    if definition.startswith("see ") or definition == "(?)":
                        continue
                    add(term, definition, match[0] + "\n" + body, section, "attested", "Attested as an entry in the supplied dictionary compilation; original edition and ancient-language usage have not been independently checked. Page links refer to this uploaded compilation, not the source-PDF page printed inside the entry.")
            if section == "Old Norse":
                for line in text.splitlines():
                    match = re.fullmatch(r"\s*([^—\n]{1,75})\s+—\s+(.{3,250})", line)
                    if match:
                        add(match[1], match[2], line, "Old Norse", "translation_candidate", "The supplied dictionary provides English–Old Norse equivalents, without an attested usage example or etymology for each pair. Native-speaker or specialist review is needed; equivalence is contextual.")
        return items

    def delete(self, source_id: str):
        if not self.get_source(source_id):
            raise KeyError(source_id)
        with self.lock, self.connection() as db:
            db.execute("DELETE FROM sources WHERE id=?", (source_id,))
            self.file_path(source_id).unlink(missing_ok=True)

    def search(self, query: str, source_ids: list[str] | None = None, limit: int = 30, terms: list[str] | None = None) -> list[dict]:
        if not query.strip():
            return []
        needles = list(dict.fromkeys([query.casefold().strip(), *(terms if terms is not None else tokens(query))]))[:24]
        clause, args = "", []
        if source_ids:
            clause = " WHERE p.source_id IN (" + ",".join("?" for _ in source_ids) + ")"
            args = source_ids
        with self.connection() as db:
            rows = db.execute("SELECT p.*,s.filename FROM pages p JOIN sources s ON s.id=p.source_id" + clause, args).fetchall()
        matches = []
        for row in rows:
            text = row["text"]
            folded = text.casefold()
            hits = [(needle, folded.count(needle)) for needle in needles if needle in folded]
            if not hits:
                continue
            score = sum(min(count, 8) for _, count in hits) + (7 if query.casefold().strip() in folded else 0)
            matches.append({"document_id": row["source_id"], "filename": row["filename"], "page": row["page"], "excerpt": excerpt(text, query if query.casefold() in folded else hits[0][0]), "score": score})
        return sorted(matches, key=lambda m: (-m["score"], m["filename"], m["page"]))[:limit]

    def entries(self, source_ids: list[str] | None = None) -> list[dict]:
        clause, args = "", []
        if source_ids:
            clause = " WHERE e.source_id IN (" + ",".join("?" for _ in source_ids) + ")"
            args = source_ids
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT e.*,s.filename FROM entries e JOIN sources s ON s.id=e.source_id" + clause, args).fetchall()]

    def bootstrap(self):
        if os.getenv("LEXICAL_BOOTSTRAP_PDFS", "1") != "1":
            return
        names = ("Language_in_Mutation_Rabelais_Joyce_Nietzsche.pdf", "Comparative_Ancient_Language_Lexicon.pdf")
        for name in names:
            key = "bootstrap:" + name
            with self.connection() as db:
                if db.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone():
                    continue
            path = next(Path("/workspace/attachments").rglob(name), None) if Path("/workspace/attachments").exists() else None
            if path:
                self.ingest(name, path.read_bytes())
                with self.connection() as db:
                    db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, "imported"))

    def save_project(self, project: dict) -> dict:
        data = dict(project)
        data["id"] = data.get("id") or uuid4().hex
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", data["id"]):
            raise ValueError("Invalid project identifier.")
        data["name"] = clean(str(data.get("name") or "Untitled experiment"))[:200]
        data["updated_at"] = now()
        serialized = json.dumps(data, ensure_ascii=False)
        if len(serialized.encode()) > 8 * 1024 * 1024:
            raise ValueError("Project is too large (8 MiB maximum).")
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO projects(id,name,updated_at,data) VALUES(?,?,?,?)", (data["id"], data["name"], data["updated_at"], serialized))
        return data

    def projects(self) -> list[dict]:
        with self.connection() as db:
            return [json.loads(row["data"]) for row in db.execute("SELECT data FROM projects ORDER BY updated_at DESC")]

    def project(self, project_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT data FROM projects WHERE id=?", (project_id,)).fetchone()
        return json.loads(row["data"]) if row else None

    def delete_project(self, project_id: str):
        with self.connection() as db:
            cursor = db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            if not cursor.rowcount:
                raise KeyError(project_id)
