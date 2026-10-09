"""Repeatable local import: python -m backend.import_sources one.pdf two.pdf."""
import argparse
from pathlib import Path

from .storage import Library


def main():
    parser = argparse.ArgumentParser(description="Import PDFs into Lexical Alchemy's local persistent library.")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    library = Library(args.data_dir)
    for path in args.pdfs:
        source = library.ingest(path.name, path.read_bytes())
        print(f"{source['filename']}: {source['status']} · {source['indexed_pages']}/{source['page_count']} pages" + (" · duplicate reused" if source.get("duplicate") else ""))
        if source.get("warning"):
            print(source["warning"])


if __name__ == "__main__":
    main()
