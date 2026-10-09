"""Portable research exports with evidence labels and unmodified provenance."""
from __future__ import annotations

import csv
import html
import io
import json

import fitz


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(as_text(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def records(project: dict) -> list[dict]:
    values = [c for c in project.get("candidates", []) if isinstance(c, dict)]
    seen = {c.get("id") for c in values}
    for candidate in project.get("shortlist", []):
        if isinstance(candidate, dict) and candidate.get("id") not in seen:
            values.append(candidate)
            seen.add(candidate.get("id"))
    return values


def pinned_ids(project: dict) -> set:
    return {c.get("id") if isinstance(c, dict) else c for c in project.get("shortlist", []) if isinstance(c, (str, dict))}


def citation(candidate: dict) -> str:
    source = candidate.get("source", {})
    pieces = [source.get("title", "Source not recorded")]
    if source.get("page") is not None:
        pieces.append("PDF page " + str(source["page"]))
    if source.get("document_id"):
        pieces.append("document " + source["document_id"])
    if source.get("url"):
        pieces.append(source["url"])
    if source.get("accessed_at"):
        pieces.append("retrieved " + source["accessed_at"])
    return " · ".join(pieces)


def markdown(project: dict) -> bytes:
    lines = ["# " + as_text(project.get("name", "Lexical Alchemy experiment")), "", "**Concept:** " + as_text(project.get("concept")), "", "Fit ratings are subjective local or model interpretations; evidence status and source records are separate.", ""]
    analysis = project.get("analysis", {})
    if isinstance(analysis, dict):
        lines.extend(["## Interpretation", ""])
        for key, value in analysis.items():
            lines.extend(["**" + key.replace("_", " ").title() + ":** " + as_text(value), ""])
    if project.get("dimensions"):
        lines.extend(["## Comparison dimensions", "", as_text(project["dimensions"]), ""])
    pinned = pinned_ids(project)
    notes = project.get("notes", "")
    lines.extend(["## Candidate ledger", ""])
    for c in records(project):
        lines.extend(["### " + c.get("term", "Untitled") + (" ★ Shortlisted" if c.get("id") in pinned else ""), "", "**Language:** " + c.get("language", ""), "", "**Evidence:** " + c.get("evidence_status", "unverified") + " · **Origin:** " + c.get("source_type", "user"), "", as_text(c.get("definition")), "", "**Source:** " + citation(c), ""])
        if c.get("source", {}).get("excerpt"):
            lines.extend(["> " + c["source"]["excerpt"].replace("\n", "\n> "), ""])
        for key in ("transliteration", "tone", "fit", "fit_reason", "captures", "misses", "technique", "components", "caveat"):
            if c.get(key) is not None:
                lines.extend(["**" + key.replace("_", " ").title() + ":** " + as_text(c[key]), ""])
        if isinstance(notes, dict) and notes.get(c.get("id")):
            lines.extend(["**Personal annotation:** " + as_text(notes[c["id"]]), ""])
    lines.extend(["## Notes", "", as_text(notes), ""])
    return "\n".join(lines).encode("utf-8")


def csv_export(project: dict) -> bytes:
    stream = io.StringIO(newline="")
    fields = ["term", "language", "transliteration", "definition", "tone", "evidence_status", "source_type", "fit", "fit_reason", "captures", "misses", "technique", "components", "caveat", "shortlisted", "source_title", "source_url", "document_id", "page", "excerpt", "accessed_at", "annotation", "concept"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    pinned, notes = pinned_ids(project), project.get("notes", {})
    for candidate in records(project):
        row = {key: as_text(candidate.get(key)) for key in fields if key in candidate}
        source = candidate.get("source", {})
        row.update({"source_title": source.get("title", ""), "source_url": source.get("url", ""), "document_id": source.get("document_id", ""), "page": source.get("page", ""), "excerpt": source.get("excerpt", ""), "accessed_at": source.get("accessed_at", ""), "shortlisted": candidate.get("id") in pinned, "annotation": as_text(notes.get(candidate.get("id"))) if isinstance(notes, dict) else as_text(notes), "concept": project.get("concept", "")})
        # Prevent spreadsheet formulas from executing when user-created words or notes are opened.
        row = {key: "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@") else value for key, value in row.items()}
        writer.writerow(row)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def pdf_export(project: dict) -> bytes:
    def e(value):
        return html.escape(as_text(value))

    sections = [f"<h1>{e(project.get('name', 'Lexical Alchemy experiment'))}</h1><p><b>Concept:</b> {e(project.get('concept'))}</p><p>Fit ratings are interpretations, not objective linguistic facts. Evidence labels and source citations are preserved below.</p>"]
    analysis = project.get("analysis", {})
    if isinstance(analysis, dict):
        sections.append("<h2>Interpretation</h2>")
        sections.extend(f"<p><b>{e(key.replace('_', ' ').title())}:</b> {e(value)}</p>" for key, value in analysis.items())
    if project.get("dimensions"):
        sections.append(f"<h2>Comparison dimensions</h2><p>{e(project['dimensions'])}</p>")
    pinned, notes = pinned_ids(project), project.get("notes", {})
    for candidate in records(project):
        sections.append(f"<h2>{e(candidate.get('term'))}{' · Shortlisted' if candidate.get('id') in pinned else ''}</h2><p><b>Language:</b> {e(candidate.get('language'))} · <b>Evidence:</b> {e(candidate.get('evidence_status', 'unverified'))} · <b>Origin:</b> {e(candidate.get('source_type', 'user'))}</p><p>{e(candidate.get('definition'))}</p><p><b>Source:</b> {e(citation(candidate))}</p>")
        if candidate.get("source", {}).get("excerpt"):
            sections.append(f"<blockquote>{e(candidate['source']['excerpt'])}</blockquote>")
        for key in ("transliteration", "tone", "fit", "fit_reason", "captures", "misses", "technique", "components", "caveat"):
            if candidate.get(key) is not None:
                sections.append(f"<p><b>{e(key.replace('_', ' ').title())}:</b> {e(candidate[key])}</p>")
        if isinstance(notes, dict) and notes.get(candidate.get("id")):
            sections.append(f"<p><b>Personal annotation:</b> {e(notes[candidate['id']])}</p>")
    sections.append(f"<h2>Notes</h2><p>{e(notes)}</p>")
    # MuPDF Story includes Unicode fallback fonts, including Greek, Cyrillic, and CJK.
    story = fitz.Story(html="".join(sections), user_css="body { font-family: sans-serif; font-size: 10pt; } h1 { font-size: 23pt; color: #28483b; } h2 { font-size: 14pt; color: #28483b; margin-top: 18pt; } p { margin-top: 6pt; } blockquote { color: #555; margin: 8pt 16pt; font-size: 9pt; }")
    stream = io.BytesIO()
    writer = fitz.DocumentWriter(stream)
    story.write(writer, lambda _page, _filled: (fitz.paper_rect("a4"), fitz.Rect(42, 42, 553, 800), None))
    writer.close()
    return stream.getvalue()
