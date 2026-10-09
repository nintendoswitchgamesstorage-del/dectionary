"""Create portable downloads, source archive, checksums, and build notes."""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def create_release():
    directory = ROOT / "releases"
    executable = directory / "LexicalAlchemy.exe"
    if not executable.is_file() or executable.read_bytes()[:2] != b"MZ":
        raise RuntimeError("Build the native Windows executable first.")
    shutil.copyfile(ROOT / "desktop" / "README-Windows.txt", directory / "README-Windows.txt")
    shutil.copyfile(ROOT / "SOURCES.md", directory / "SOURCES.md")
    licenses = ROOT / ".packaging" / "resources" / "licenses"
    if licenses.is_dir():
        shutil.copytree(licenses, directory / "licenses", dirs_exist_ok=True)
    verification = ROOT / ".packaging" / "windows-verification.json"
    if not verification.is_file():
        raise RuntimeError("Run desktop/verify_windows.py against the executable before releasing.")
    checks = json.loads(verification.read_text(encoding="utf-8"))
    if checks.get("status") != "passed":
        raise RuntimeError("The executable verification has not passed.")
    if checks.get("sha256") != hashlib.sha256(executable.read_bytes()).hexdigest():
        raise RuntimeError("Verification does not belong to the current executable. Rerun its checks.")
    notes = {"name": "Lexical Alchemy", "version": "0.1.0", "target": "Windows 10/11 x64", "format": "single-file GUI executable; native control window and default browser interface", "signed": False, "build_runtime": "Windows Python 3.12.7 + PyInstaller 6.16.0 via Wine64", "build_image": "tobix/pywine:3.12@sha256:e1c1d41a8b64616ac838aed8908a75b8f6838337533fe2484a7bb6871a8403cc", "tested_on_native_windows_hardware": False, "python_test_results": {"Linux": 23, "Windows Python via Wine64": 23}, "frozen_executable_checks": checks, "bundled_starter_pdf_pages": 638, "data_location": "%LOCALAPPDATA%\\LexicalAlchemy", "bundled_private_projects_or_credentials": False}
    (directory / "BUILD-INFO.json").write_text(json.dumps(notes, indent=2), encoding="utf-8")
    source_zip = directory / "LexicalAlchemy-Source.zip"
    excluded_names = {"__pycache__", ".pytest_cache"}
    source_files = [ROOT / name for name in ("README.md", "SOURCES.md", ".gitignore", "package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts", "playwright.config.ts")]
    for name in ("src", "backend", "desktop", "scripts", "tests"):
        source_files.extend(p for p in (ROOT / name).rglob("*") if p.is_file() and not any(part in excluded_names for part in p.parts) and p.suffix != ".pyc")
    with zipfile.ZipFile(source_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(set(source_files)):
            archive.write(path, str(Path("LexicalAlchemy") / path.relative_to(ROOT)))
    hash_lines = []
    for path in (executable, source_zip):
        hash_lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (directory / "SHA256SUMS.txt").write_text("\n".join(hash_lines) + "\n", encoding="ascii")
    bundle = directory / "LexicalAlchemy-Windows-x64.zip"
    content = [executable, source_zip, *(directory / name for name in ("README-Windows.txt", "SOURCES.md", "BUILD-INFO.json", "SHA256SUMS.txt"))]
    if (directory / "licenses").exists():
        content.extend(path for path in (directory / "licenses").rglob("*") if path.is_file())
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in content:
            archive.write(path, str(path.relative_to(directory)))
    with (directory / "SHA256SUMS.txt").open("a", encoding="ascii") as stream:
        stream.write(f"{hashlib.sha256(bundle.read_bytes()).hexdigest()}  {bundle.name}\n")
    print(f"Ready: {executable.name} ({executable.stat().st_size / 1024 / 1024:.1f} MiB)")
    print(f"Portable download: {bundle.name} ({bundle.stat().st_size / 1024 / 1024:.1f} MiB)")
    print("Source archive, attribution, licenses, build evidence, and SHA-256 checksums included.")


if __name__ == "__main__":
    create_release()
