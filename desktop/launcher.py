"""Self-contained desktop launcher; bundled with Windows Python by PyInstaller.

The native control window owns a loopback-only server and opens the bundled UI
in the user's existing browser. No Node, Python installation, or API key needed.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import shutil
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def default_data_dir() -> Path:
    if os.getenv("LEXICAL_DATA_DIR"):
        return Path(os.environ["LEXICAL_DATA_DIR"]).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "LexicalAlchemy"
    return Path.home() / ".local" / "share" / "LexicalAlchemy"


def configure_logging(directory: Path) -> None:
    (directory / "logs").mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(directory / "logs" / "desktop.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # A --windowed executable has no console streams. Uvicorn formatters and
    # unexpected dependency writes must have valid targets rather than None.
    if sys.stdout is None:
        sys.stdout = open(directory / "logs" / "console.log", "a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = sys.stdout


def prepare_library(app, resources: Path) -> None:
    library = app.state.library
    starter = resources / "starter-pdfs"
    for filename in ("Language_in_Mutation_Rabelais_Joyce_Nietzsche.pdf", "Comparative_Ancient_Language_Lexicon.pdf"):
        key = "desktop-starter:" + filename
        with library.connection() as db:
            already_imported = db.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone()
        if already_imported:
            continue
        source = starter / filename
        if source.is_file():
            result = library.ingest(filename, source.read_bytes())
            if result["status"] not in ("ready", "partial"):
                raise RuntimeError(f"The bundled document could not be indexed: {filename}")
            with library.connection() as db:
                db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, "1"))
    # Copy public dictionary snapshots only, never a pre-existing SQLite library,
    # uploaded user files, notes, provider credentials, or browser state.
    dictionaries = resources / "dictionaries"
    if dictionaries.is_dir():
        destination = library.directory / "dictionaries"
        destination.mkdir(exist_ok=True)
        for source in dictionaries.iterdir():
            if source.is_file() and not (destination / source.name).exists():
                temporary = destination / (source.name + ".desktop-part")
                shutil.copyfile(source, temporary)
                temporary.replace(destination / source.name)


def make_app(directory: Path, resources: Path | None = None):
    os.environ["LEXICAL_DATA_DIR"] = str(directory)
    os.environ["LEXICAL_BOOTSTRAP_PDFS"] = "0"
    from backend.app import create_app
    from fastapi.staticfiles import StaticFiles

    app = create_app(directory)
    prepare_library(app, resources or bundle_root() / "resources")
    frontend = bundle_root() / "dist"
    if not (frontend / "index.html").is_file():
        raise RuntimeError("The bundled interface is missing. Rebuild the frontend before packaging.")
    app.mount("/", StaticFiles(directory=frontend, html=True), name="interface")
    return app


def instance_guard(directory: Path, no_browser: bool) -> tuple[bool, int | None]:
    if os.name != "nt":
        return True, None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, "Local\\LexicalAlchemyDesktop")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        # First startup can be busy extracting/indexing the bundled books. Give
        # it time to write its ready URL rather than launch competing servers.
        for _ in range(60):
            try:
                session = json.loads((directory / "desktop-session.json").read_text(encoding="utf-8"))
                url = session["url"]
                if not url.startswith("http://127.0.0.1:"):
                    raise ValueError("Invalid local session URL")
                with urllib.request.urlopen(url + "api/health", timeout=1) as response:
                    if response.status == 200:
                        if not no_browser:
                            webbrowser.open(url)
                        kernel.CloseHandle(ctypes.c_void_p(handle))
                        return False, None
            except (OSError, ValueError, KeyError):
                time.sleep(.5)
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise RuntimeError("Lexical Alchemy is already starting. Please use its existing launcher window.")
    return True, handle


class Runner:
    def __init__(self, directory: Path, port: int, ready_file: Path | None):
        self.directory = directory
        self.port = port
        self.ready_file = ready_file
        self.server = None
        self.sock = None
        self.url = ""
        self.error = ""
        self.started = threading.Event()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            import uvicorn

            app = make_app(self.directory)
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.bind(("127.0.0.1", self.port))
            self.sock.listen(128)
            actual_port = self.sock.getsockname()[1]
            self.url = f"http://127.0.0.1:{actual_port}/"
            config = uvicorn.Config(app, host="127.0.0.1", port=actual_port, log_config=None, access_log=False, loop="asyncio", http="h11", lifespan="on", ws="none")
            self.server = uvicorn.Server(config)
            if self.stopping.is_set():
                return

            def publish_ready():
                for _ in range(600):
                    if self.stopping.is_set():
                        return
                    if self.server.started:
                        info = {"url": self.url, "pid": os.getpid(), "data_dir": str(self.directory)}
                        for path in [self.directory / "desktop-session.json", *([self.ready_file] if self.ready_file else [])]:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            temporary = path.with_suffix(path.suffix + ".tmp")
                            temporary.write_text(json.dumps(info), encoding="utf-8")
                            temporary.replace(path)
                        self.started.set()
                        logging.info("Desktop server ready at %s", self.url)
                        return
                    time.sleep(.1)
                self.error = "The local research service did not become ready. See the desktop log."
                self.stop()

            threading.Thread(target=publish_ready, daemon=True).start()
            self.server.run(sockets=[self.sock])
        except Exception:
            self.error = traceback.format_exc()
            logging.exception("Desktop startup failed")
        finally:
            if self.sock:
                self.sock.close()
            path = self.directory / "desktop-session.json"
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("pid") == os.getpid():
                    path.unlink()
            except (OSError, ValueError):
                pass

    def stop(self):
        self.stopping.set()
        if self.server:
            self.server.should_exit = True


def show_control_window(runner: Runner, no_browser: bool):
    import tkinter as tk

    root = tk.Tk()
    root.title("Lexical Alchemy")
    root.geometry("510x305")
    root.resizable(False, False)
    root.configure(background="#f6f4ef")
    tk.Label(root, text="LEXICAL ALCHEMY", font=("Segoe UI", 10), fg="#b8512e", bg="#f6f4ef").pack(pady=(25, 7))
    tk.Label(root, text="Make the familiar strange.", font=("Georgia", 22), fg="#30362f", bg="#f6f4ef").pack()
    status = tk.StringVar(value="Preparing your local library…")
    tk.Label(root, textvariable=status, font=("Segoe UI", 10), fg="#737968", bg="#f6f4ef", wraplength=460).pack(pady=(19, 15))
    buttons = tk.Frame(root, bg="#f6f4ef")
    buttons.pack()
    launch = tk.Button(buttons, text="Open laboratory", command=lambda: webbrowser.open(runner.url), state="disabled", bg="#b8512e", fg="white", activebackground="#a24627", activeforeground="white", font=("Segoe UI", 11), relief="flat", padx=22, pady=9)
    launch.pack(side="left", padx=6)

    def close():
        launch.configure(state="disabled")
        status.set("Closing the local research service…")
        runner.stop()
        root.after(100, finish_close)

    def finish_close():
        if runner.thread.is_alive():
            root.after(100, finish_close)
        else:
            root.destroy()

    tk.Button(buttons, text="Exit", command=close, bg="#e8e6db", fg="#5a6452", font=("Segoe UI", 11), relief="flat", padx=20, pady=9).pack(side="left", padx=6)
    tk.Label(root, text="Keep this window open while using the laboratory.\nYour PDFs and projects are saved in your Windows user profile.", font=("Segoe UI", 9), fg="#858b78", bg="#f6f4ef").pack(pady=(20, 0))
    root.protocol("WM_DELETE_WINDOW", close)
    opened = False

    def poll():
        nonlocal opened
        if runner.stopping.is_set():
            close()
            return
        if runner.error:
            status.set("Startup failed. Check logs in " + str(runner.directory / "logs"))
            from tkinter import messagebox
            messagebox.showerror("Lexical Alchemy", runner.error[-1800:])
            runner.stop()
            return
        if runner.started.is_set() and not opened:
            status.set("Ready. Private, local, and yours to experiment with.")
            launch.configure(state="normal")
            root.update_idletasks()
            gui = {"title": root.title(), "native_window_id": root.winfo_id(), "visible": bool(root.winfo_viewable())}
            for path in [runner.directory / "desktop-session.json", *([runner.ready_file] if runner.ready_file else [])]:
                try:
                    info = json.loads(path.read_text(encoding="utf-8"))
                    info["gui"] = gui
                    temporary = path.with_suffix(path.suffix + ".gui-tmp")
                    temporary.write_text(json.dumps(info), encoding="utf-8")
                    temporary.replace(path)
                except (OSError, ValueError):
                    logging.exception("Could not record launcher readiness")
            opened = True
            if not no_browser:
                webbrowser.open(runner.url)
        root.after(150, poll)

    runner.thread.start()
    root.after(150, poll)
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Lexical Alchemy desktop application")
    parser.add_argument("--headless", action="store_true", help="Run without a control window (for automated verification)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--exit-after", type=float, help="Stop after the specified number of seconds (test mode)")
    args = parser.parse_args()
    directory = (args.data_dir or default_data_dir()).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    configure_logging(directory)
    handle = None
    runner = Runner(directory, args.port, args.ready_file)
    try:
        if not args.headless:
            acquired, handle = instance_guard(directory, args.no_browser)
            if not acquired:
                return 0
        if args.exit_after is not None:
            timer = threading.Timer(args.exit_after, runner.stop)
            timer.daemon = True
            timer.start()
        if args.headless:
            runner.thread.start()
            runner.thread.join()
        else:
            show_control_window(runner, args.no_browser)
        return 1 if runner.error else 0
    except Exception:
        logging.exception("Launcher failed")
        if os.name == "nt" and not args.headless:
            ctypes.windll.user32.MessageBoxW(None, "Lexical Alchemy could not start. Details are in:\n" + str(directory / "logs" / "desktop.log"), "Lexical Alchemy", 0x10)
        return 1
    finally:
        runner.stop()
        runner.thread.join(timeout=5) if runner.thread.ident else None
        if handle and os.name == "nt":
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))


if __name__ == "__main__":
    raise SystemExit(main())
