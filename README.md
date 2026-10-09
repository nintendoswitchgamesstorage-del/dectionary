# Lexical Alchemy

A working language laboratory for meanings that existing vocabulary does not quite hold. Explore a concept across source documents and dictionaries, then deliberately bend roots into new constructions. Inspired by the supplied design guide and the linguistic techniques discussed around Rabelais, Joyce, and Nietzsche.

The interface has four connected spaces:

- **Concept workspace:** editable interpretation, language and document selection, weighted comparison dimensions, evidence filters, sorting, source details, and side-by-side comparison.
- **Neologism forge:** compounds, portmanteaus, affixation, hybrid roots, inversion, and unconventional collocations, across five deformation levels. Roots, meanings, languages, alternate spellings, and word families can be edited and saved.
- **PDF library:** multiple uploads, local extraction, page citations, excerpts, search, duplicate detection, reprocessing, and removal.
- **Word cabinet:** pinned candidates, annotations, saved projects, reopening, and Markdown, CSV, or PDF export.

## Run it

Requirements: Python 3.12+, Node.js 20.19+ or 22.12+, and npm. Chromium is needed only for the browser tests.

```bash
cd /workspace/dectionary
bash scripts/setup.sh
bash scripts/dev.sh
```

The Python API uses port **8000**; the Vite frontend uses **5173** and proxies `/api` to Python. Stop the development script with Ctrl+C. On another machine, use your checkout directory instead of `/workspace/dectionary`. For a production frontend bundle, run `npm run build`; `npm run preview` serves it on port 4173 while the API is running separately. This is a local research application without multi-user authentication.

Stop the development services before rerunning setup. Dependency reinstallation replaces Vite's optimization cache, so a running frontend must restart afterward.

Use the existing checkout in cloud tasks. A task already has its own isolated environment; no additional Git worktree is needed.

The two supplied vocabulary PDFs are already indexed in this cloud instance: **35 + 603 = 638 searchable pages**. First startup imports those named files from `/workspace/attachments` when available. The implementation-guide PDF guides the application rather than appearing as vocabulary evidence. Source PDFs are not committed to the repository. On a fresh clone outside this cloud snapshot, upload them in the library or import your own:

```bash
.venv/bin/python -m backend.import_sources /path/to/first.pdf /path/to/second.pdf
```

## Evidence, retrieval, and limits

Every candidate carries an evidence label and a source type. PDF citations use actual **physical PDF page numbers**, rather than internal page references printed in a dictionary entry. An attestation in a secondary compilation verifies what appears there; it does not independently authenticate the primary author's text. Excerpts are short and copied from the actual indexed page.

The starter vocabulary includes 40 curated entries from the two PDFs, retrieved dictionaries, and game-world research leads. The ancient lexicon is also indexed for additional dictionary entries and passages. [SOURCES.md](SOURCES.md) records inspected sources, licenses, retrieval dates, and caveats.

Enable **Try live dictionary lookup** in research settings to retrieve/cache real public dictionary snapshots from permitted GitHub sources. Integrations include Webster English, Chinese characters through Make Me a Hanzi, and FreeDict Latin, French, and Modern Greek equivalents. The backend also supports German spelling evidence when its Hunspell mirror is available; spelling evidence is distinct from meaning evidence. Dictionary snapshots are cached locally with source/retrieval metadata. A first download is larger than a per-word lookup (the Webster mirror is approximately 23 MB). These mirrors require no API key, have no paid API cost, and remain subject to GitHub availability and rate limits. TLS verification remains enabled.

German, Ancient Greek, Persian, Russian, and Azerbaijani coverage depends on PDF contents, dictionary coverage, and labeled leads. A translation candidate is a possible rendering, rather than an exact equivalent. Game concepts from **Minecraft, Slime Rancher, Subnautica, The Eternal Cylinder, and Clay Jam** are usable as creative components; their starter descriptions are marked **unverified** where direct source access was refused. No successful web research is simulated.

Local concept interpretation, ranking, and passage search use explicit keywords, a small theme map, and word-form rules. They provide useful starting points but are not unrestricted semantic web research. Custom dimensions influence textual ranking, not an objective judgment of word quality. The local forge constructs forms from chosen components and explains its operations. “Coined” means proposed in this session, rather than a promise of historical originality. Cross-language hybrids require grammatical or native-speaker review.

## Optional model assistance

No model account or secret is needed for the default workflow. The UI enables model assistance when a provider credential is configured. Opting in sends the concept and the selected editable forge roots to OpenAI; the full PDF library and index are not automatically sent. Roots selected from source results can include source-derived text. Usage is billed by the provider, subject to its model access, quota, and rate limits.

Configure credentials securely as environment variables, never in source files:

| Variable | Purpose |
| --- | --- |
| `LEXICAL_MODEL_API_KEY` | Optional OpenAI credential. Standard `OPENAI_API_KEY` is also accepted for local installations. |
| `LEXICAL_MODEL_NAME` | Optional model name; defaults to `gpt-4.1-mini`. `OPENAI_MODEL` is also accepted. |
| `LEXICAL_DATA_DIR` | Optional absolute local data directory; defaults to `.data` in the checkout. |
| `LEXICAL_BOOTSTRAP_PDFS` | Set to `0` to disable the first-run attachment import. |

For cloud proxy credentials, configure the non-reserved `LEXICAL_MODEL_API_KEY` binding for `api.openai.com` in environment settings and allow that destination. Do not paste credentials into chat. Restart Python after changing environment bindings. A configured credential is not a claim that the provider was successfully tested. Missing credentials, denied access, invalid responses, and exhausted quotas produce explicit errors. Research evidence still comes from retrieval; model interpretation never creates a citation.

## PDFs, storage, and privacy

Original PDFs live in `.data/sources/`; extracted pages, parsed entries, projects, and source metadata live in `.data/lexical.sqlite3`. Dictionary downloads and retrieval metadata live in `.data/dictionaries/`. A current draft is autosaved in browser local storage; named projects are persisted by Python in SQLite. Back up `.data` if you need to preserve the library and saved projects. Removing a document deletes its local file and index; earlier exported or saved citations may refer to a document that is no longer available.

Default research, text extraction, and generation stay on the machine. Public dictionary retrieval downloads data and sends no uploaded PDF contents. Model requests require explicit opt-in. Source links open the original PDF at its cited page or the actual external reference.

Uploads are limited to **20 PDFs per batch, 32 MiB each, and 1,500 pages per document**. Password-protected, corrupt, image-only, and partially extracted PDFs display recoverable errors or warnings. OCR is optional and not bundled. To index a scanned PDF, install a trusted local OCR tool and process it first, for example:

```bash
ocrmypdf input.pdf searchable.pdf
```

Upload the resulting searchable PDF. OCRmyPDF requires Tesseract and its selected language packs; poor OCR needs human review. Empty or unextracted pages are never silently claimed to be searchable. Only short source excerpts are included in research results and exports.

## Test

```bash
bash scripts/test.sh
# With both development services running:
bash scripts/test.sh --browser
```

Python tests exercise PDF ingestion, actual citations, duplicate handling, scanned/corrupt files, persistence, provider failures, dictionary parsing, exports, and the Unicode forge. Browser tests use the real API to research, compare, upload/search multiple PDFs, create/revise coinages, pin/annotate them, save/reopen projects, and download all three export formats. Browser fixtures are removed after the run. The browser configuration uses `/usr/bin/chromium`; set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` for another installed Chromium path.

The optional paid model's live success path is not tested without a configured account. Missing-credential and malformed-provider responses are tested. OCR and blocked direct dictionary/game-wiki access are reported limitations, not passing tests.

## Windows executable

The portable Windows edition bundles Python, the built interface, the two starter PDFs, and attributed public dictionary snapshots in one `LexicalAlchemy.exe`. Double-click it on 64-bit Windows 10/11. A small control window starts a private loopback server and opens your existing browser. No Python, Node.js, API account, installer, or administrator access is needed by the user. Exit through the control window when finished.

The Windows edition stores its library and projects in `%LOCALAPPDATA%\LexicalAlchemy`, outside the executable and temporary extraction folder. Moving or replacing the executable preserves your saved work. No existing project database, annotations, credential bindings, or unrelated uploaded documents are included in a build. The two originally supplied vocabulary PDFs are bundled as requested source material. Named projects persist across restarts; the browser's automatic draft may be tied to a particular local server URL, so use **Save project** to keep an experiment.

For a native rebuild on a Windows build machine with Python 3.12 and Node installed:

```powershell
.\desktop\build-windows.ps1 -StarterPdf @('C:\path\Language_in_Mutation_Rabelais_Joyce_Nietzsche.pdf', 'C:\path\Comparative_Ancient_Language_Lexicon.pdf')
```

This builds `releases/LexicalAlchemy.exe` and a portable ZIP with instructions, source attribution, and a SHA-256 checksum. Build prerequisites are separate from end-user requirements. PyInstaller freezes the Windows runtime; the executable is unsigned. The current cloud build uses Wine64 with Windows Python and Windows wheels, and its runtime checks are documented with the release. This is not a claim of native Windows hardware testing or code signing. See [desktop/README-Windows.txt](desktop/README-Windows.txt).

Backend endpoint contracts and response shapes are documented in [backend/API.md](backend/API.md).
