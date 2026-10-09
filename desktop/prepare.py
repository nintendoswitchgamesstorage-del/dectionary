"""Stage only the two starter PDFs and public dictionary data for packaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILENAMES = ("Language_in_Mutation_Rabelais_Joyce_Nietzsche.pdf", "Comparative_Ancient_Language_Lexicon.pdf")
DICTIONARIES = ("webster.json", "webster-README", "makemeahanzi.jsonl", "makemeahanzi-COPYING", "lat-eng.tei", "fra-eng.tei", "eng-ell.tei", "german-hunspell.dic", "german-hunspell-index.aff", "german-hunspell-license")


def prepare(starter_paths: list[Path], data_dir: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    starter = destination / "starter-pdfs"
    starter.mkdir(exist_ok=True)
    copied = []
    for filename in FILENAMES:
        source = next((p for p in starter_paths if p.name == filename), None)
        if source is None:
            from backend.storage import Library
            library = Library(data_dir)
            record = next((s for s in library.sources() if s["filename"] == filename), None)
            if record:
                source = library.file_path(record["id"])
        if source is None or not source.is_file():
            raise FileNotFoundError(f"The starter PDF {filename} is missing. Pass its path with --starter-pdf.")
        target = starter / filename
        shutil.copyfile(source, target)
        copied.append(target)
    dictionary_dir = destination / "dictionaries"
    dictionary_dir.mkdir(exist_ok=True)
    for filename in DICTIONARIES:
        source = data_dir / "dictionaries" / filename
        if source.is_file():
            target = dictionary_dir / filename
            shutil.copyfile(source, target)
            copied.append(target)
            metadata = source.with_suffix(source.suffix + ".metadata.json")
            if metadata.is_file():
                target_metadata = dictionary_dir / metadata.name
                shutil.copyfile(metadata, target_metadata)
                copied.append(target_metadata)
    # Attribution is bundled alongside cache data. No arbitrary data-directory
    # traversal is used: SQLite, other uploads, notes, logs and secrets are excluded.
    shutil.copyfile(ROOT / "SOURCES.md", destination / "SOURCES.md")
    copied.append(destination / "SOURCES.md")
    manifest = [{"path": str(path.relative_to(destination)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in copied]
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--starter-pdf", type=Path, action="append", default=[])
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".data")
    parser.add_argument("--destination", type=Path, default=ROOT / ".packaging" / "resources")
    args = parser.parse_args()
    manifest = prepare(args.starter_pdf, args.data_dir, args.destination)
    print(f"Staged {len(manifest)} source/data files ({sum(item['bytes'] for item in manifest):,} bytes). No projects, credentials, or personal uploads included.")


if __name__ == "__main__":
    main()
