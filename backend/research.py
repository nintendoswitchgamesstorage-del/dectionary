"""Transparent lexical matching plus real, optional public dictionary retrieval."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from .storage import Library, clean, excerpt, normalize, now, tokens

STOP = set("a an and are as at be but by can could for from has have how i in is it its like make me of on or person someone that the their then these they this to was were what when where which who with without would you your ordinary".split())
THEMES = [
    {"signals": "power authority institution institutions bureaucracy political control hierarchy king rule domination wealth reputation expert parasite parasitic extraction exploitation exploit dependence dependency contribution opportunist rent", "related": "power authority institutional domination exploitation parasitism dependency extraction contribution cunning bureaucratic", "tension": "Power held by position versus power earned through contribution.", "qualities": "Competence, resourcefulness, integrity, dependence, or their absence.", "power": "Look for expertise, office, wealth, force, reputation, and control over access.", "relation": "Distinguish reciprocity and productive contribution from one-sided extraction.", "setting": "Institutions, markets, political life, or interpersonal hierarchies.", "distinction": "Influence is not identical to competence; dependence is not necessarily exploitation."},
    {"signals": "strange uncanny familiar alien eerie unfamiliar wonder sublime beauty beautiful terrifying fear awe horror mysterious mystery", "related": "strange uncanny eerie familiar estrangement awe wonder sublime beauty fear ambiguity", "tension": "Recognition and attraction coexist with unease or estrangement.", "qualities": "Curiosity, sensitivity, vulnerability, and tolerance of ambiguity.", "power": "Aesthetic, emotional, or perceptual force rather than necessarily social authority.", "relation": "The relation between an observer and what both attracts and unsettles them.", "setting": "Art, perception, landscape, dream, or encounters with the unfamiliar.", "distinction": "The uncanny, the marvelous, and the sublime emphasize different kinds of unfamiliarity."},
    {"signals": "word words language meaning meanings vocabulary thought knowledge knowing mind intelligent intellect naming speech nonsense absurd contradiction chaotic chaos order creation invent invention", "related": "language meaning naming knowledge thought transformation chaos order invention creation contradiction", "tension": "A name stabilizes meaning while experimentation opens it again.", "qualities": "Ingenuity, judgment, interpretive flexibility, or deliberate nonsense.", "power": "The authority to name, explain, classify, or make an interpretation seem natural.", "relation": "Shared understanding can enable cooperation or exclude other readings.", "setting": "Literature, philosophy, scholarship, conversation, and experimental language.", "distinction": "A new word, a new sense of an old word, and an unusual collocation are different operations."},
    {"signals": "memory memories forgetting forgotten past time temporal history historical ruin ruins ruined decay loss nostalgia ephemeral impermanence change mutation becoming transformation", "related": "memory time history loss decay change transformation becoming impermanence trace", "tension": "Persistence and continuity coexist with change, loss, or disappearance.", "qualities": "Attention, longing, resilience, or acceptance of change.", "power": "Control over remembrance, preservation, or the story told about the past.", "relation": "The present depends on and reworks what remains of the past.", "setting": "Personal memory, ruins, archives, history, and changing worlds.", "distinction": "Memory, nostalgia, a surviving trace, and active transformation are not interchangeable."},
    {"signals": "nature natural world worlds ecology ecological ecosystem symbiosis symbiotic life living grow growth plant forest ocean sea creature creatures animal survival adapt adaptation evolution slime monster game games play playful imagination fictional dream dreams", "related": "nature ecology world life growth symbiosis creature adaptation survival play dream transformation", "tension": "Growth and survival may coexist with consumption, dependence, or destruction.", "qualities": "Adaptability, curiosity, resilience, and imaginative openness.", "power": "Resources, environmental constraints, scale, and capacity to adapt.", "relation": "Compare predation, parasitism, symbiosis, and mutual support.", "setting": "Ecologies, fictional worlds, games, material processes, or metaphorical social worlds.", "distinction": "A fictional species or game mechanic is an analogy, not automatically a dictionary meaning."},
]


def concept_terms(concept: str) -> tuple[list[str], list[str]]:
    direct = list(dict.fromkeys(t for t in tokens(concept) if t not in STOP))[:24]
    related = []
    for theme in THEMES:
        if set(direct) & set(theme["signals"].split()):
            related.extend(theme["related"].split())
    # Modest English morphology handling, presented as lexical rather than semantic search.
    for term in direct:
        if len(term) > 5 and term.endswith("ing"):
            related.append(term[:-3])
        elif len(term) > 4 and term.endswith("s"):
            related.append(term[:-1])
    return direct, list(dict.fromkeys(t for t in related if t not in direct))[:35]


def analyze_local(concept: str) -> dict:
    direct, _ = concept_terms(concept)
    themes = [t for t in THEMES if set(direct) & set(t["signals"].split())][:3]
    if not themes:
        themes = [{"tension": "Check whether the concept names an observable condition, a judgment, or a metaphor.", "qualities": "Specify the relevant human qualities if people are involved.", "power": "No mechanism of power was identified by the local keyword rules.", "relation": "Specify whether any dependence or exchange is essential to the concept.", "setting": "The setting remains open; add context to narrow the search.", "distinction": "Separate the central meaning from nearby synonyms, causes, and consequences."}]
    return {"central_meaning": clean(concept), "tensions": [t["tension"] for t in themes], "qualities": [t["qualities"] for t in themes], "power": [t["power"] for t in themes], "relations": [t["relation"] for t in themes], "settings": [t["setting"] for t in themes], "distinctions": [t["distinction"] for t in themes], "method": "local heuristic"}


def rank(candidate: dict, direct: list[str], related: list[str], dimensions: list[dict]) -> dict:
    candidate = copy.deepcopy(candidate)
    haystack = normalize(" ".join([candidate.get("term", ""), candidate.get("definition", ""), " ".join(candidate.get("tags", [])), candidate.get("captures", "") if isinstance(candidate.get("captures", ""), str) else " ".join(candidate.get("captures", []))]))
    direct_hits = [t for t in direct if normalize(t) in haystack]
    related_hits = [t for t in related if normalize(t) in haystack]
    score = 27 + min(45, 10 * len(direct_hits)) + min(18, 3 * len(related_hits))
    if normalize(candidate.get("term", "")) in [normalize(t) for t in direct]:
        score += 8
    dimension_hits = []
    for dimension in dimensions:
        name = clean(str(dimension.get("name", "")))[:80]
        try:
            weight = max(0, min(10, float(dimension.get("weight", 1))))
        except (TypeError, ValueError):
            weight = 1
        if any(normalize(t) in haystack for t in tokens(name) if t not in STOP):
            score += min(7, weight)
            dimension_hits.append(name)
    candidate["fit"] = round(min(98, score))
    signals = direct_hits[:4] + related_hits[:3]
    candidate["fit_reason"] = ("Local lexical signals: " + ", ".join(signals) + ". " if signals else "Exploratory lead with no direct lexical overlap. ") + ("Weighted dimensions matched: " + ", ".join(dimension_hits) + ". " if dimension_hits else "") + "This score is a reading aid from keyword overlap, not an objective linguistic measure."
    candidate.setdefault("captures", "Shares " + ", ".join(signals[:4]) if signals else "A related perspective to inspect.")
    candidate.setdefault("misses", "A lexical match cannot establish an exact equivalent or intended context.")
    candidate.setdefault("tone", "context-dependent")
    candidate.setdefault("tags", signals)
    return candidate


def canonical_language(language: str) -> str:
    for name in ("Old Turkic", "Old Avestan", "Old Norse", "Ancient Greek", "Modern Greek", "English", "Chinese", "German", "Greek", "Latin", "French", "Persian", "Russian", "Azerbaijani"):
        if name.casefold() in language.casefold():
            return "Greek" if name == "Modern Greek" else name
    return language


class Researcher:
    MIRRORS = {
        "English": {"url": "https://raw.githubusercontent.com/matthewreagan/WebstersEnglishDictionary/master/dictionary.json", "file": "webster.json", "format": "json", "title": "Webster's Unabridged Dictionary · public GitHub mirror", "license": "Project Gutenberg terms; mirror README includes GPL notices", "caveat": "Historical Webster/Gutenberg transcription; the mirror's README warns of parsing defects. Modern usage and exact conceptual equivalence need review."},
        "Chinese": {"url": "https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt", "file": "makemeahanzi.jsonl", "format": "jsonl", "title": "Make Me a Hanzi · character dictionary", "license": "LGPL-3.0-or-later; Unihan/CJKlib-derived dictionary data", "caveat": "A Mandarin character-level learning dictionary, not an exhaustive dictionary of Chinese words. Pinyin and semantic equivalence require context."},
        "Latin": {"url": "https://raw.githubusercontent.com/freedict/fd-dictionaries/master/lat-eng/lat-eng.tei", "file": "lat-eng.tei", "format": "tei", "title": "FreeDict Latin–English dictionary", "license": "GPL-2.0-or-later", "caveat": "Bilingual dictionary equivalents, not proof that a word captures every part of the concept. Historical register and specialist review may matter."},
        "French": {"url": "https://raw.githubusercontent.com/freedict/fd-dictionaries/master/fra-eng/fra-eng.tei", "file": "fra-eng.tei", "format": "tei", "title": "FreeDict French–English dictionary", "license": "GPL-2.0-or-later", "caveat": "Bilingual dictionary equivalents. Context, register, and native-speaker review are needed for a precise rendering."},
        "Greek": {"url": "https://raw.githubusercontent.com/freedict/fd-dictionaries/master/eng-ell/eng-ell.tei", "file": "eng-ell.tei", "format": "tei-reverse", "title": "FreeDict English–Modern Greek dictionary", "license": "GPL-2.0-or-later OR CC-BY-SA-3.0", "caveat": "Reverse lookup of an English–Modern Greek bilingual dictionary. This is not an Ancient Greek attestation or an exact conceptual equivalence."},
        "German": {"url": "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/de/index.dic", "file": "german-hunspell.dic", "format": "hunspell", "title": "German Hunspell dictionary · igerman98 spelling list", "license": "GPL-2.0 OR GPL-3.0 (see source license)", "caveat": "Attests the listed German spelling or stem only. Some entries are compound parts with Hunspell flags, not necessarily standalone words. This spell-checking dictionary supplies no definition, translation, etymology, or usage evidence; editorial senses remain separately unverified."},
    }

    def __init__(self, library: Library):
        self.library = library
        self.cache_dir = library.directory / "dictionaries"
        self.cache_dir.mkdir(exist_ok=True)
        self.cache: dict[str, tuple[object, str]] = {}
        self.locks = {name: asyncio.Lock() for name in self.MIRRORS}
        self.last_errors: dict[str, str] = {}

    def seeds(self) -> list[dict]:
        path = Path(__file__).parent / "data" / "seeds.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        data = data.get("candidates", []) if isinstance(data, dict) else data
        sources = self.library.sources()
        resolved = []
        for seed in data:
            seed = copy.deepcopy(seed)
            if seed.get("source_type") == "pdf":
                source = seed.get("source", {})
                name = source.get("filename", source.get("title", ""))
                document = next((d for d in sources if d["filename"] == name or d["filename"] == source.get("title")), None)
                if not document:
                    continue
                page = source.get("page")
                if not isinstance(page, int) or not 1 <= page <= document["page_count"]:
                    continue
                with self.library.connection() as db:
                    row = db.execute("SELECT text FROM pages WHERE source_id=? AND page=?", (document["id"], page)).fetchone()
                if not row or normalize(seed["term"]) not in normalize(row["text"]):
                    continue
                source["document_id"] = document["id"]
                source["title"] = document["filename"]
                # Quotes in the bundled metadata are checked against the actual page.
                quoted = source.get("excerpt", "")
                if not quoted or normalize(clean(quoted)) not in normalize(clean(row["text"])):
                    source["excerpt"] = excerpt(row["text"], seed["term"])
            resolved.append(seed)
        return resolved

    async def dictionary(self, language: str) -> tuple[object, str]:
        async with self.locks[language]:
            if language in self.cache:
                return self.cache[language]
            mirror = self.MIRRORS[language]
            cache_file = self.cache_dir / mirror["file"]
            metadata_file = cache_file.with_suffix(cache_file.suffix + ".metadata.json")
            if not (cache_file.exists() and metadata_file.exists()):
                async with httpx.AsyncClient(timeout=httpx.Timeout(35, connect=8), follow_redirects=True) as client:
                    response = await client.get(mirror["url"])
                    response.raise_for_status()
                if len(response.content) > 32 * 1024 * 1024:
                    raise ValueError("Dictionary mirror exceeds the 32 MiB download limit.")
                # Parse before keeping the download; malformed responses never become results.
                parsed = self.parse_dictionary(language, response.text)
                retrieved_at = now()
                temporary = cache_file.with_suffix(cache_file.suffix + ".part")
                temporary.write_bytes(response.content)
                temporary.replace(cache_file)
                metadata_file.write_text(json.dumps({"url": mirror["url"], "accessed_at": retrieved_at}), encoding="utf-8")
            else:
                content = cache_file.read_text(encoding="utf-8")
                parsed = self.parse_dictionary(language, content)
                retrieved_at = json.loads(metadata_file.read_text(encoding="utf-8"))["accessed_at"]
            self.cache[language] = (parsed, retrieved_at)
            self.last_errors.pop(language, None)
            return self.cache[language]

    def parse_dictionary(self, language: str, content: str):
        format = self.MIRRORS[language]["format"]
        if format == "json":
            return json.loads(content)
        if format == "jsonl":
            return [json.loads(line) for line in content.splitlines() if line.strip()]
        if format == "hunspell":
            records = {}
            for line in content.splitlines():
                if not line or line[0].isspace() or line.startswith("#") or line.isdigit():
                    continue
                term = line.split("/", 1)[0]
                if term and len(term) <= 100:
                    records[term.casefold()] = {"term": term, "excerpt": line}
            return records
        root = ET.fromstring(content)
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        records = []
        for entry in root.findall(".//tei:entry", ns):
            headwords = [clean("".join(node.itertext())) for node in entry.findall("tei:form/tei:orth", ns)]
            if format == "tei-reverse":
                translations = [clean("".join(node.itertext())) for node in entry.findall(".//tei:sense/tei:def", ns)]
                for headword in headwords:
                    for translation in translations:
                        records.append({"term": translation, "definition": "Possible Modern Greek equivalent of English “" + headword + "”.", "matching_text": headword + " " + translation, "excerpt": translation})
            else:
                definitions = [clean("".join(node.itertext())) for node in entry.findall(".//tei:cit[@type='trans']/tei:quote", ns)]
                for headword in headwords:
                    if definitions:
                        records.append({"term": headword, "definition": "; ".join(definitions), "matching_text": headword + " " + " ".join(definitions), "excerpt": definitions[0]})
        return records

    async def web_candidates(self, concept: str, languages: list[str], seeds: list[dict]) -> tuple[list[dict], list[str]]:
        direct, related = concept_terms(concept)
        results, warnings = [], []
        selected = [canonical_language(l) for l in languages]
        wanted = [language for language in self.MIRRORS if not selected or language in selected or (language == "Chinese" and "Mandarin" in selected)]

        async def retrieve(language: str):
            try:
                data, accessed_at = await self.dictionary(language)
                mirror = self.MIRRORS[language]
                found = []
                if language == "English":
                    words = list(dict.fromkeys(direct + related + [s["term"].casefold() for s in seeds if s.get("language") == "English"]))
                    for term in words:
                        definition = data.get(term)
                        if isinstance(definition, str) and len(definition) > 8:
                            found.append((term, definition, None, clean(definition)[:360]))
                elif language == "Chinese":
                    for entry in data:
                        definition = entry.get("definition", "")
                        if not isinstance(definition, str):
                            continue
                        if any(t in definition.casefold() for t in direct) or entry.get("character", "") in concept:
                            found.append((entry["character"], definition, " / ".join(entry.get("pinyin", [])), definition))
                    found.sort(key=lambda row: -sum(t in row[1].casefold() for t in direct))
                elif language == "German":
                    matching_seeds = [s for s in seeds if canonical_language(s.get("language", "")) == "German" and rank(s, direct, related, [])["fit"] > 27]
                    words = list(dict.fromkeys(direct + [s["term"].casefold() for s in matching_seeds]))
                    for word in words:
                        entry = data.get(word)
                        if entry:
                            found.append((entry["term"], "Spelling listed in the German Hunspell dictionary; no meaning is provided by this source.", None, entry["excerpt"]))
                else:
                    for entry in data:
                        if any(t in entry["matching_text"].casefold() for t in direct + related[:12]):
                            found.append((entry["term"], entry["definition"], None, entry["excerpt"]))
                    found.sort(key=lambda row: -sum(t in row[1].casefold() for t in direct))
                candidates = []
                for term, definition, transliteration, source_excerpt in found[:20]:
                    candidate = {"id": "web-" + hashlib.sha256(f"{language}:{term}".encode()).hexdigest()[:16], "term": term, "language": "Modern Greek" if language == "Greek" else language, "definition": clean(definition)[:700], "tone": "historical / dictionary" if language == "English" else "context-dependent", "evidence_status": "attested" if language in ("English", "Chinese", "German") else "translation_candidate", "source_type": "dictionary", "source": {"title": mirror["title"], "url": mirror["url"], "accessed_at": accessed_at, "excerpt": clean(source_excerpt)[:360], "license": mirror["license"]}, "caveat": mirror["caveat"], "captures": "A directly retrieved dictionary definition or translation; inspect the relevant sense.", "misses": "Dictionary attestation does not make this an exact equivalent of the full concept."}
                    if language == "German":
                        seed = next((s for s in matching_seeds if s["term"].casefold() == term.casefold()), None)
                        candidate.update({"spelling_only": True, "tags": ["spelling-only", *(seed.get("tags", []) if seed else [])], "captures": "Confirms that this spelling occurs in the downloaded German dictionary.", "misses": "No semantic or usage evidence is provided. Conceptual connection, if any, comes from an unverified editorial lead."})
                    if transliteration:
                        candidate["transliteration"] = transliteration
                    candidates.append(candidate)
                return candidates, None
            except (httpx.HTTPError, ValueError, KeyError, OSError, ET.ParseError) as error:
                message = f"{language} dictionary retrieval unavailable: {type(error).__name__}. Local sources and clearly labeled editorial leads are still usable."
                self.last_errors[language] = message
                return [], message

        outcomes = await asyncio.gather(*(retrieve(language) for language in wanted))
        for candidates, warning in outcomes:
            results.extend(candidates)
            if warning:
                warnings.append(warning)
        unsupported = [l for l in languages if canonical_language(l) not in (*self.MIRRORS, "Mandarin", "Old Turkic", "Old Avestan", "Old Norse")]
        if unsupported:
            warnings.append("Live dictionary integration currently covers English, Chinese characters, Latin, French, Modern Greek, and German spellings (without definitions). Other selected languages use imported PDFs and labeled editorial leads: " + ", ".join(unsupported) + ".")
        return results, warnings

    async def research(self, payload: dict) -> dict:
        concept = clean(payload["concept"])
        interpretation = payload.get("interpretation") or ""
        if isinstance(interpretation, dict):
            interpretation = interpretation.get("central_meaning", "")
        query = concept + " " + str(interpretation)
        direct, related = concept_terms(query)
        languages = payload.get("languages") or []
        source_ids = payload.get("source_ids") or []
        dimensions = payload.get("dimensions") or []
        candidates = self.seeds()
        warnings = ["Local ranking uses keyword overlap and a small explicit theme map. It does not perform model-based semantic research."]
        candidates = [c for c in candidates if (payload.get("include_games", True) or c.get("source_type") != "game") and (not source_ids or c.get("source_type") != "pdf" or c["source"].get("document_id") in source_ids)]
        for row in self.library.entries(source_ids):
            candidates.append({"id": row["id"], "term": row["term"], "language": row["language"], "definition": row["definition"], "tone": "literary" if "Mutation" in row["filename"] else "historical / dictionary", "evidence_status": row["evidence_status"], "source_type": "pdf", "source": {"title": row["filename"], "document_id": row["source_id"], "page": row["page"], "excerpt": row["excerpt"]}, "caveat": row["caveat"]})
        # Local matching is intentionally independent of external provider availability.
        if payload.get("include_web"):
            online, web_warnings = await self.web_candidates(query, languages, candidates)
            candidates.extend(online)
            warnings.extend(web_warnings)
        else:
            warnings.append("Live dictionary retrieval is off. Bundled dictionary and game leads retain their recorded evidence status.")
        accepted_languages = {canonical_language(l).casefold() for l in languages}
        ranked = []
        for candidate in candidates:
            language = candidate.get("language", "")
            if accepted_languages and candidate.get("source_type") != "game" and not any(l in language.casefold() for l in accepted_languages):
                continue
            candidate = rank(candidate, direct, related, dimensions)
            if candidate["fit"] > 27:
                ranked.append(candidate)
        ranked.sort(key=lambda c: (-c["fit"], c.get("evidence_status") == "unverified", c.get("source_type") != "pdf"))
        # Prefer real retrieved dictionary definitions over unverified editorial entries.
        unique: dict[tuple[str, str, str], dict] = {}
        for candidate in ranked:
            key = (candidate["term"].casefold(), canonical_language(candidate["language"]).casefold(), "spelling" if candidate.get("spelling_only") else "sense")
            previous = unique.get(key)
            if previous is None or (previous["evidence_status"] == "unverified" and candidate["evidence_status"] != "unverified"):
                unique[key] = candidate
        ordered = sorted(unique.values(), key=lambda c: -c["fit"])
        ranked = ordered[:60]
        selected_ids = {candidate["id"] for candidate in ranked}
        # Reserve space for different evidence domains and languages rather than let
        # a large dictionary crowd out the user's PDFs or relevant fictional leads.
        for kind in ("pdf", "dictionary", "game"):
            for candidate in [c for c in ordered if c.get("source_type") == kind][:4]:
                if candidate["id"] not in selected_ids:
                    ranked.append(candidate)
                    selected_ids.add(candidate["id"])
        for language in languages[:20]:
            candidate = next((c for c in ordered if canonical_language(c["language"]).casefold() == canonical_language(language).casefold()), None)
            if candidate and candidate["id"] not in selected_ids:
                ranked.append(candidate)
                selected_ids.add(candidate["id"])
        # Any uploaded PDF remains searchable even when its layout is not a dictionary.
        known_documents = {c.get("source", {}).get("document_id") for c in ranked if c.get("source_type") == "pdf"}
        for match in self.library.search(concept, source_ids, limit=12, terms=direct + related[:8]):
            if match["document_id"] in known_documents:
                continue
            in_excerpt = next((t for t in direct + related if t.casefold() in match["excerpt"].casefold()), None)
            if not in_excerpt:
                continue
            # Preserve the actual observed spelling, rather than generating a headword.
            observed = re.search(re.escape(in_excerpt), match["excerpt"], re.I)
            term = observed[0] if observed else in_excerpt
            candidate = {"id": f"passage-{match['document_id']}-{match['page']}", "term": term, "language": "Document context", "definition": "Contextual passage lead: " + match["excerpt"], "tone": "source-dependent", "evidence_status": "attested", "source_type": "pdf", "source": {"title": match["filename"], "document_id": match["document_id"], "page": match["page"], "excerpt": match["excerpt"]}, "captures": "A word actually present in a potentially relevant passage.", "misses": "This passage lead is not a dictionary definition or proof of exact conceptual equivalence.", "caveat": "Review the original page; local lexical retrieval can match incidental mentions."}
            ranked.append(rank(candidate, direct, related, dimensions))
            known_documents.add(match["document_id"])
        if any(c.get("evidence_status") == "unverified" for c in ranked):
            warnings.append("Unverified dictionary and game leads are editorial suggestions. Their reference links are not evidence that this session retrieved or confirmed them.")
        if any(c.get("source_type") == "pdf" for c in ranked):
            warnings.append("PDF citations identify the uploaded compilation and its actual PDF page. A secondary lexicon entry does not independently verify the author's primary text or an etymology.")
        if not ranked:
            warnings.append("No lexical matches were found. Add descriptive keywords, broaden the selected languages, or import relevant PDFs.")
        return {"candidates": sorted(ranked, key=lambda c: -c["fit"]), "warnings": warnings, "method": "local lexical matching + retrieved/cached public dictionaries" if payload.get("include_web") else "local lexical matching"}

    def providers(self) -> list[dict]:
        return [{"name": mirror["title"], "language": language, "configured": True, "status": "cached" if language in self.cache or (self.cache_dir / mirror["file"]).exists() else "unavailable" if language in self.last_errors else "not checked", "url": mirror["url"], "warning": self.last_errors.get(language), "privacy": "Downloads a public dictionary snapshot. Uploaded PDF contents are never sent."} for language, mirror in self.MIRRORS.items()]
