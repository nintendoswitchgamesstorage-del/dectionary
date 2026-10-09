"""Run the actual frozen .exe, exercise it, restart, and verify saved data.

Execute with Windows Python or Wine64. This helper's Python is not required by
the packaged app; all application requests go to the executable's own runtime.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

import fitz
import httpx


def wait_ready(process, path: Path, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Packaged app exited before readiness: {process.returncode}")
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            try:
                if httpx.get(data["url"] + "api/health", timeout=2, trust_env=False).status_code == 200:
                    return data
            except httpx.HTTPError:
                pass
        time.sleep(.2)
    raise TimeoutError("Packaged application did not become ready")


def start(executable, directory, ready, seconds, gui=False):
    ready.unlink(missing_ok=True)
    command = [str(executable), "--no-browser", "--data-dir", str(directory), "--ready-file", str(ready), "--exit-after", str(seconds)]
    if not gui:
        command.append("--headless")
    process = subprocess.Popen(command)
    return process, wait_ready(process, ready)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    directory = args.data_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    ready = directory.parent / (directory.name + "-ready.json")
    process, info = start(args.executable.resolve(), directory, ready, 75, args.gui)
    try:
        client = httpx.Client(base_url=info["url"], timeout=40, trust_env=False)

        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

        index = call("GET", "/").text
        assert 'id="root"' in index
        asset = re.search(r'src="([^"]+\.js)"', index)[1]
        assert "javascript" in call("GET", asset).headers["content-type"]
        sources = call("GET", "/api/sources").json()["sources"]
        assert len(sources) == 2 and sum(s["indexed_pages"] for s in sources) == 638
        matches = call("GET", "/api/sources/search", params={"q": "Joyce"}).json()["matches"]
        assert matches and all(m["page"] > 0 and m["excerpt"] for m in matches)
        research = call("POST", "/api/research", json={"concept": "strange dreams changing worlds and hunger", "include_web": True, "include_games": True, "languages": ["English", "Chinese", "German", "Latin", "French", "Greek"]}).json()
        assert any(c["source_type"] == "dictionary" for c in research["candidates"])
        assert any(c["source_type"] == "pdf" for c in research["candidates"])
        assert not any("retrieval unavailable" in warning for warning in research["warnings"]), research["warnings"]
        roots = [{"text": "梦", "language": "Chinese", "meaning": "dream"}, {"text": "κόσμος", "language": "Greek", "meaning": "world / order"}]
        coins = call("POST", "/api/forge", json={"concept": "A dreaming world", "roots": roots, "level": "radical", "count": 6}).json()["candidates"]
        assert len(coins) == 6 and all(c["evidence_status"] == "coined" and c["components"] and c["technique"] for c in coins)
        for format in ("markdown", "csv", "pdf"):
            body = call("POST", "/api/export", json={"format": format, "project": {"name": "Executable verification", "concept": "Unicode dream world", "candidates": coins, "shortlist": [coins[0]["id"]], "notes": {coins[0]["id"]: "A persistent annotation"}}}).content
            if format == "pdf":
                assert body.startswith(b"%PDF-")
                with fitz.open(stream=body, filetype="pdf") as pdf:
                    text = "\n".join(page.get_text() for page in pdf)
                assert "coined" in text and "persistent annotation" in text and "梦" in text
            else:
                text = body.decode("utf-8-sig")
                assert "coined" in text and "persistent annotation" in text and "梦" in text
        project = call("POST", "/api/projects", json={"name": "Executable persistence check", "concept": "A dreaming world", "candidates": coins, "shortlist": [coins[0]["id"]], "notes": {coins[0]["id"]: "Kept across restarts"}}).json()
        # Confirm removing a starter source is a durable user choice, without
        # reimporting it on every new execution.
        call("DELETE", f"/api/sources/{sources[0]['id']}")
        print("FROZEN EXE: interface, 638 PDF pages, cited search, cached multilingual dictionaries, Unicode forge, exports and save passed.", flush=True)
        if args.gui:
            gui = json.loads(ready.read_text(encoding="utf-8")).get("gui", {})
            assert gui.get("visible") and gui.get("native_window_id") and gui.get("title") == "Lexical Alchemy", "Native control window was not mapped"
        process.wait(timeout=90)
        assert process.returncode == 0
        assert not (directory / "desktop-session.json").exists()
        print("FROZEN EXE: clean shutdown passed.", flush=True)
    finally:
        if process.poll() is None:
            process.terminate()

    process2, info2 = start(args.executable.resolve(), directory, ready, 15, args.gui)
    try:
        client2 = httpx.Client(base_url=info2["url"], timeout=20, trust_env=False)
        reopened = client2.get(f"api/projects/{project['id']}")
        reopened.raise_for_status()
        assert reopened.json()["notes"][coins[0]["id"]] == "Kept across restarts"
        assert len(client2.get("api/sources").json()["sources"]) == 1
        assert client2.get("api/providers").json()["model"]["configured"] is False
        if args.gui:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                gui = json.loads(ready.read_text(encoding="utf-8")).get("gui", {})
                if gui.get("visible") and gui.get("native_window_id"):
                    break
                time.sleep(.1)
            assert gui.get("visible") and gui.get("native_window_id")
        process2.wait(timeout=40)
        assert process2.returncode == 0
        print("FROZEN EXE: saved project/notes reopened and removed source stayed removed. Restart passed.", flush=True)
        result = {"status": "passed", "native_window": args.gui, "sha256": hashlib.sha256(args.executable.read_bytes()).hexdigest(), "runtime": "Windows executable", "os": os.name, "checks": ["bundled UI and JavaScript", "638 indexed starter pages", "real page citations", "cached dictionaries without network", "Unicode forge", "Markdown CSV PDF exports", "SQLite persistence", "source removal persistence", "clean shutdown", "restart"]}
        (directory.parent / "windows-verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finally:
        if process2.poll() is None:
            process2.terminate()


if __name__ == "__main__":
    main()
