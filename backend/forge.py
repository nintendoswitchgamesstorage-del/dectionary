"""A transparent, local word-making engine.

This module transforms *supplied strings*, not verified historical morphemes.
Every result describes the actual string operation and remains a proposal even
when its spelling happens to coincide with a word already in use. No network,
model, or dictionary access is implied by generation.

The broad technique families study bodily/comic exaggeration associated with
Rabelais, multilingual collision associated with Joyce, and conceptual reversal
associated with Nietzsche. They are analytical inspirations, not quotations,
authorial attributions, or instructions to reproduce a writer's voice.
"""

from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import itertools
import json
import math
import random
import re
import unicodedata
from typing import Any


LEVELS = ("conservative", "inventive", "abrasive", "surreal", "radical")
MAX_COUNT = 30
MAX_ROOTS = 12
_FICTIONAL_DOMAINS = frozenset(name.casefold() for name in (
    "Minecraft", "Slime Rancher", "Subnautica", "The Eternal Cylinder", "Clay Jam",
))
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "their them there these this to was which who with without would describe "
    "word words concept name someone something".split()
)
_TONES = {
    "conservative": "restrained / descriptive",
    "inventive": "playful / exploratory",
    "abrasive": "polemical / deliberately sharp",
    "surreal": "dreamlike / estranging",
    "radical": "fragmentary / deliberately unstable",
}


def _clean(value: Any, limit: int) -> str:
    """Keep Unicode letters and marks while discarding invisible controls."""
    if value is None:
        return ""
    value = unicodedata.normalize("NFC", str(value)[: max(limit * 8, 64)])
    value = "".join(
        char if not unicodedata.category(char).startswith("C") else " "
        for char in value
    )
    return re.sub(r"\s+", " ", value).strip()[:limit].rstrip()


def _clusters(text: str) -> list[str]:
    """Group base characters with their combining marks before clipping."""
    clusters: list[str] = []
    for char in text:
        if unicodedata.combining(char) and clusters:
            clusters[-1] += char
        else:
            clusters.append(char)
    return clusters


def _fragment(text: str, side: str, fraction: float = 0.6) -> str:
    clusters = _clusters(text)
    size = max(1, math.ceil(len(clusters) * fraction))
    return "".join(clusters[:size] if side == "front" else clusters[-size:])


def _helper(text: str, meaning: str) -> dict[str, str]:
    return {"text": text, "language": "English", "meaning": meaning}


def _prepare_roots(payload: dict[str, Any], concept: str) -> list[dict[str, str]]:
    roots: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    supplied = payload.get("roots", [])
    if not isinstance(supplied, list):
        supplied = []
    for item in supplied[:MAX_ROOTS]:
        if not isinstance(item, dict):
            continue
        text = _clean(item.get("text"), 48)
        language = _clean(item.get("language"), 48) or "Unspecified"
        key = (text.casefold(), language.casefold())
        if not text or key in seen:
            continue
        seen.add(key)
        roots.append(
            {
                "text": text,
                "language": language,
                "meaning": _clean(item.get("meaning"), 180) or "Meaning not provided",
            }
        )
    if roots:
        return roots
    words = re.findall(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", concept, flags=re.UNICODE)
    for word in words:
        if word.casefold() in _STOPWORDS or word.casefold() in {r["text"].casefold() for r in roots}:
            continue
        roots.append(
            {"text": _clean(word, 48), "language": "Unspecified", "meaning": "A word taken from your concept; no dictionary sense inferred"}
        )
        if len(roots) >= 4:
            break
    return roots or [
        {"text": "meaning", "language": "English", "meaning": "Used here as the idea a word attempts to carry"},
        {"text": "gap", "language": "English", "meaning": "Used here as what familiar vocabulary leaves unresolved"},
    ]


def _unique_components(components: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for component in components:
        if component not in result:
            result.append(dict(component))
    return result


def _language(components: list[dict[str, str]]) -> str:
    languages = list(dict.fromkeys(c["language"] for c in components))
    return languages[0] if len(languages) == 1 else "Hybrid (" + " / ".join(languages) + ")"


def _score(concept: str, components: list[dict[str, str]], level: str) -> int:
    """An explicit lexical-overlap heuristic, not a linguistic fit measurement."""
    query = {x.casefold() for x in re.findall(r"[^\W\d_]+", concept)}
    values = " ".join(c["text"] + " " + c["meaning"] for c in components)
    content = {x.casefold() for x in re.findall(r"[^\W\d_]+", values)}
    overlap = len((query - _STOPWORDS) & content)
    penalty = {"conservative": 0, "inventive": 3, "abrasive": 6, "surreal": 9, "radical": 12}[level]
    return min(96, max(38, 68 + 6 * min(overlap, 4) - penalty))


def generate(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate 1–30 distinct, fully labeled proposals from editable roots.

    ``seed`` makes selection reproducible. In its absence the normalized input
    determines a stable seed. Unsupported levels use ``inventive``. Supplied
    roots and glosses are never promoted to attested vocabulary by this function.
    """
    if not isinstance(payload, dict):
        raise ValueError("The forge expects an object containing a concept and optional roots.")
    concept = _clean(payload.get("concept"), 360) or "a meaning that familiar vocabulary leaves unresolved"
    level = payload.get("level", "inventive")
    if level not in LEVELS:
        level = "inventive"
    try:
        count = max(1, min(MAX_COUNT, int(payload.get("count", 8))))
    except (TypeError, ValueError, OverflowError):
        count = 8
    roots = _prepare_roots(payload, concept)
    seed_input = payload.get("seed")
    if not isinstance(seed_input, (str, int, float)):
        seed_input = json.dumps([concept, level, roots], ensure_ascii=False, sort_keys=True)
    rng = random.Random(str(seed_input))
    proposals: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(
        term: str,
        technique: str,
        components: list[dict[str, str]],
        construction: str,
        intention: str,
        ambiguity: str,
    ) -> None:
        term = _clean(term, 120)
        normalized = term.casefold()
        if not term or normalized in seen:
            return
        seen.add(normalized)
        components = _unique_components(components)
        languages = list(dict.fromkeys(c["language"] for c in components))
        caveat = (
            "Coined means proposed in this session; prior use has not been checked. "
            "Supplied root glosses have not been independently verified. "
        )
        fictional = [name for name in languages if name.casefold() in _FICTIONAL_DOMAINS]
        review_languages = [name for name in languages if name != "Unspecified" and name not in fictional]
        if "Unspecified" in languages:
            caveat += "Some root languages are unspecified; their strings are not treated as verified morphemes. "
        if fictional:
            caveat += (
                "Fictional-world labels name source settings, not natural languages. "
                "These components and their game-world meanings have not been independently verified. "
            )
        if len(review_languages) > 1 or any(x != "English" for x in review_languages):
            caveat += (
                "This is an experimental string construction, not verified grammar. "
                "Native-speaker and grammar review (or specialist review for historical languages) is needed for " + ", ".join(review_languages) + ". "
            )
        caveat += ambiguity
        identity = json.dumps([level, concept, term, components, construction], ensure_ascii=False, sort_keys=True)
        proposals.append(
            {
                "id": "forge-" + sha256(identity.encode()).hexdigest()[:16],
                "term": term,
                "language": _language(components),
                "definition": "Proposed for “" + concept + "”. " + intention,
                "tone": _TONES[level],
                "evidence_status": "coined",
                "source_type": "coined",
                "source": {"title": "Local Neologism Forge"},
                "fit": _score(concept, components, level),
                "fit_reason": construction + " Fit is a local root-overlap heuristic, not a verified linguistic judgment.",
                "captures": intention,
                "misses": ambiguity,
                "tags": ["word-maker", level, technique.casefold().replace(" ", "-")],
                "components": components,
                "technique": technique,
                "caveat": caveat,
            }
        )

    pairs = list(itertools.permutations(roots, 2)) if len(roots) > 1 else [(roots[0], roots[0])]
    for a, b in pairs:
        x, y = a["text"], b["text"]
        pair = [a, b]
        ax, by = _fragment(x, "front"), _fragment(y, "back")
        if level == "conservative":
            add(x + "-" + y, "Compound", pair,
                f"Joins the full supplied strings “{x}” and “{y}” with a hyphen.",
                "Places the two supplied meanings in a single, readable relationship.",
                "The relation between the components remains open; an existing compound may have another sense.")
            add(x + " " + y, "Unusual collocation", pair,
                f"Places “{x}” before “{y}” as an open two-word expression.",
                "Lets the first component recast the second without hiding either spelling.",
                "The phrase can sound descriptive instead of naming a distinct concept.")
            add(x + "/" + y, "Semantic compression", pair,
                f"Separates the intact strings “{x}” and “{y}” with a slash.",
                "Keeps two competing interpretations visible inside one label.",
                "A slash does not explain whether the meanings overlap, conflict, or alternate.")
        elif level == "inventive":
            add(ax + by, "Portmanteau", pair,
                f"Takes the opening fragment “{ax}” from “{x}” and the ending fragment “{by}” from “{y}”, then joins them.",
                "Makes the two supplied meanings share a single sound-shape.",
                "Clipping can obscure the roots and does not establish pronunciation or real morphology.")
            if any(root["language"].casefold() in _FICTIONAL_DOMAINS for root in pair):
                name = "Fictional-concept splice"
            elif "Unspecified" in (a["language"], b["language"]):
                name = "Supplied-string splice"
            else:
                name = "Cross-language splice" if a["language"] != b["language"] else "Closed compound"
            add(x + y, name, pair,
                f"Concatenates the full supplied strings “{x}” ({a['language']}) and “{y}” ({b['language']}) without a separator.",
                "Compresses the supplied meanings into one visible lexical body.",
                "The result may be hard to segment and is not claimed to follow either language’s word-formation rules.")
            add(x + " of " + y, "Unusual collocation", pair + [_helper("of", "Used here to connect the two components")],
                f"Places the intact strings “{x}” and “{y}” around the English connector “of”.",
                "Recasts the first meaning as something belonging to, or made from, the second.",
                "The relation is deliberately open and may imply possession unintentionally.")
            add(x + "-within-" + y, "Semantic compression", pair + [_helper("within", "Used here as containment")],
                f"Joins “{x}”, the English connector “within”, and “{y}” with hyphens.",
                "Treats one meaning as concealed or nested inside the other.",
                "Containment is an interpretive metaphor rather than an observed property.")
        elif level == "abrasive":
            for word, meaning in (("tax", "an imposed cost"), ("rot", "decay from within"), ("gnash", "a harsh grinding tension")):
                add(x + "-" + y + "-" + word, "Polemical compound", pair + [_helper(word, "Used here to suggest " + meaning)],
                    f"Joins the intact strings “{x}”, “{y}”, and the English image “{word}” with hyphens.",
                    "Turns the concept toward " + meaning + ", making an implicit judgment audible.",
                    "The added image imposes a negative judgment that may distort a neutral concept.")
            add("anti-" + ax + by, "Adversarial portmanteau", pair + [_helper("anti-", "Used here to signal opposition")],
                f"Adds “anti-” to “{ax}” (the opening of “{x}”) plus “{by}” (the ending of “{y}”).",
                "Frames the merged concept as something that resists or undermines itself.",
                "Opposition is supplied by the forge; clipped fragments are not verified morphemes.")
            add(x + " eats " + y, "Metaphorical inversion", pair + [_helper("eats", "Used metaphorically for consumption or extraction")],
                f"Places the intact strings “{x}” and “{y}” around the English verb “eats”.",
                "Makes an abstract relation appear as appetite, consumption, or extraction.",
                "This personifies the components and may overstate antagonism.")
        elif level == "surreal":
            for image, meaning in (("ghost", "an absent presence"), ("lantern", "a light that exposes or distorts"), ("weather", "a shifting atmosphere")):
                add(x + " " + image + " of " + y, "Dream collocation", pair + [_helper(image, "Used here as " + meaning), _helper("of", "Used here to connect the images")],
                    f"Places “{x}”, the English image “{image}”, the connector “of”, and “{y}” in that order.",
                    "Turns the relation between the supplied meanings into " + meaning + ".",
                    "The image estranges the concept but may require explanation to communicate it.")
            add(y + " dreams " + x, "Metaphorical inversion", pair + [_helper("dreams", "Used here to give an abstract component an imagined inner life")],
                f"Reverses the supplied order: “{y}”, then the English verb “dreams”, then “{x}”.",
                "Treats the second meaning as a mind that imagines the first.",
                "Agency and consciousness are deliberately metaphorical, not factual claims.")
            add(ax + "echo" + by, "Imagistic portmanteau", pair + [_helper("echo", "Used here for repetition with a changed voice")],
                f"Joins “{ax}” (opening of “{x}”), the English image “echo”, and “{by}” (ending of “{y}”).",
                "Makes the merged meanings appear to repeat and deform one another.",
                "The visible splice may feel suggestive rather than pronounceable.")
        else:
            add(ax + "↯" + by, "Interrupted portmanteau", pair,
                f"Joins “{ax}” (opening of “{x}”) and “{by}” (ending of “{y}”) with the interruption mark ↯.",
                "Exposes the collision between the two supplied meanings instead of smoothing it away.",
                "The mark has no agreed pronunciation; the fragments are not verified morphemes.")
            add(x + "∴" + y, "Visual semantic compression", pair,
                f"Places the full strings “{x}” and “{y}” around ∴, conventionally read as ‘therefore’.",
                "Stresses a questionable inference from the first meaning to the second.",
                "The implied inference is a provocation, not a demonstrated logical relationship.")
            add("un(" + x + ")" + y, "Fractured affixation", pair + [_helper("un-", "Used here to suggest undoing or negation")],
                f"Writes “un”, puts the intact string “{x}” in parentheses, then appends “{y}”.",
                "Stages the first meaning as something undone while the second survives the operation.",
                "The parenthesis breaks ordinary morphology and leaves the scope of negation unstable.")
            add(y + " / not-" + x, "Contradictory collocation", pair + [_helper("not", "Used here to make a negation visible")],
                f"Writes “{y}”, then “ / not-”, then the intact string “{x}”.",
                "Holds an assertion and a negation in a single, unresolved label.",
                "The result names a tension rather than a stable category.")

    # Each root also has a family of explicitly described single-root operations.
    # This guarantees useful output even for a one-character, one-root input.
    families = {
        "conservative": [("-ness", "state or quality"), ("-work", "practice or labor"), ("-bound", "restriction"), ("-sense", "a way of noticing"), ("-field", "a setting"), ("-craft", "a practice"), ("-way", "a habitual path"), ("-frame", "an interpretive boundary")],
        "inventive": [("neo-", "renewal"), ("meta-", "reflection on itself"), ("counter-", "a competing relation"), ("-ling", "a smaller or familiar embodiment"), ("-scape", "an environment"), ("-fold", "layers"), ("-flux", "continuous change"), ("-craft", "an active practice")],
        "abrasive": [("-monger", "aggressive dealing"), ("-rust", "corrosion"), ("-famine", "an imposed lack"), ("-grind", "wearing pressure"), ("-leech", "one-sided extraction"), ("-snarl", "hostile entanglement"), ("-husk", "an emptied shell"), ("-fang", "a capacity to wound")],
        "surreal": [("-moon", "a remote reflection"), ("-stomach", "an impossible appetite"), ("-tide", "a recurring current"), ("-orchard", "unexpected growth"), ("-mirror", "an altered reflection"), ("-sleep", "a latent dream"), ("-moth", "a fragile attraction"), ("-rain", "a falling atmosphere")],
        "radical": [("un-", "undoing"), ("after-", "an aftermath"), ("pre-", "an unstable beginning"), ("-void", "an absence inside the idea"), ("-else", "an unresolved alternative"), ("-zero", "cancellation"), ("-break", "a rupture"), ("-almost", "a withheld completion")],
    }
    for root in roots:
        x = root["text"]
        for marker, intention in families[level]:
            prefix = marker.endswith("-")
            term = marker + x if prefix else x + marker
            technique = "Experimental affixation" if level in ("conservative", "inventive") else "Imagistic affixation"
            add(term, technique, [root, _helper(marker, "Used here to suggest " + intention)],
                f"{'Prefixes' if prefix else 'Appends'} the visible English element “{marker}” {'to' if prefix else 'after'} the intact supplied string “{x}”.",
                "Reframes the supplied meaning through " + intention + ".",
                "This is an experimental attachment; naturalness and grammatical category are not established.")

    # More than 30 variants are possible even with a single one-character root.
    # These are semantic constructions, not arbitrary numeric uniqueness suffixes.
    connectors = {
        "conservative": ["under", "through", "near", "around"],
        "inventive": ["against", "inside", "beyond", "between"],
        "abrasive": ["devours", "taxes", "splinters", "bleeds"],
        "surreal": ["dreams", "haunts", "sleeps beneath", "rains into"],
        "radical": ["≠", "↔", "?", "∕∕"],
    }
    images = [("silence", "what remains unsaid"), ("hunger", "an unmet demand"), ("memory", "a retained trace"), ("mirror", "a returned image"), ("time", "change or duration"), ("distance", "separation")]
    for root in roots:
        for connector in connectors[level]:
            for image, meaning in images:
                add(root["text"] + " " + connector + " " + image, "Unconventional collocation", [root, _helper(image, "Used here for " + meaning)] + ([_helper(connector, "Used here as an experimental relation")] if connector[0].isalpha() else []),
                    f"Places the intact supplied string “{root['text']}”, the connector “{connector}”, and the English image “{image}” in that order.",
                    "Tests the supplied meaning in relation to " + meaning + ".",
                    "The added relation is an interpretive experiment and may shift the original concept.")

    # Round-robin selection prevents many permutations of one recipe crowding
    # out the other techniques, while a seed changes which variants are shown.
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for proposal in proposals:
        grouped[proposal["technique"]].append(proposal)
    names = list(grouped)
    rng.shuffle(names)
    queues: dict[str, deque[dict[str, Any]]] = {}
    for name in names:
        rng.shuffle(grouped[name])
        queues[name] = deque(grouped[name])
    selected: list[dict[str, Any]] = []
    while len(selected) < count and queues:
        for name in list(queues):
            selected.append(queues[name].popleft())
            if not queues[name]:
                del queues[name]
            if len(selected) == count:
                break
    return selected
