# Native Windows build. Run with Windows Python/PyInstaller, or Wine64.
from pathlib import Path
import sys

ROOT = Path(SPECPATH).resolve().parent
runtime_files = {}
for folder in (Path(sys.base_prefix), Path(sys.base_prefix) / 'Scripts', Path(sys.prefix), Path(sys.prefix) / 'Scripts'):
    for pattern in ('msvcp140*.dll', 'concrt140.dll', 'vcomp140.dll', 'vcruntime140*.dll'):
        for path in folder.glob(pattern):
            runtime_files[path.name.lower()] = path
runtime_dlls = [(str(path), '.') for path in runtime_files.values()]
if not any(Path(path).name.lower() == 'msvcp140.dll' for path, _ in runtime_dlls):
    raise RuntimeError('Install desktop/requirements-build.txt to bundle authentic Microsoft runtime DLLs.')
analysis = Analysis(
    [str(ROOT / 'desktop' / 'launcher.py')],
    pathex=[str(ROOT)],
    binaries=runtime_dlls,
    datas=[
        (str(ROOT / 'dist'), 'dist'),
        (str(ROOT / 'backend' / 'data'), 'backend/data'),
        (str(ROOT / '.packaging' / 'resources'), 'resources'),
        (str(ROOT / 'SOURCES.md'), '.'),
    ],
    hiddenimports=[
        'uvicorn.logging', 'uvicorn.loops.asyncio',
        'uvicorn.protocols.http.h11_impl', 'uvicorn.lifespan.on',
        'tkinter', 'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'unittest', 'IPython', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, analysis.binaries, analysis.datas, [],
    name='LexicalAlchemy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    version=str(ROOT / 'desktop' / 'version.txt'),
)
