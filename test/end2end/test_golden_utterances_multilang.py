"""Multilingual golden-utterance end-to-end coverage for
ovos-skill-speedtest.

test_intents_en_us.py / test_golden_utterances.py only exercised en-US.
This skill registers one Padatious/Padacioso file-intent
(speedtest_intent.intent); every locale under locale/ ships real .intent
content for it. Each golden row is a literal resolution of that locale's
own .intent template lines -- (a|b) alternatives and [a|b]/[x] optional
groups resolve to one concrete choice -- no translated or invented prose
is introduced.

The handler runs a live network ``speedtest``; ``speedtest.Speedtest`` is
patched with a deterministic offline stub *before* MiniCroft loads the
skill (same technique as ``test_golden_utterances.py`` and
``test_intents_en_us.py``) so the suite stays fast, reproducible, and
network-free.

Unlike ovos-skill-alerts' shared-MiniCroft-with-secondary-langs approach
(blocked by ovoscope#179 at multi-locale scale), this suite follows the
ovos-skill-date-time per-locale pattern (test/end2end/test_intents_it_it.py
on that repo's dev branch): one MiniCroft is booted per locale, in turn,
torn down when the module's tests finish. Only the pure-Python, swig-free
padacioso template engine is booted (no padatious training phase, so no
"mycroft.skills.trained" wait across many locales).
"""
import speedtest

DOWNLOAD_BPS = 50_000_000.0
UPLOAD_BPS = 10_000_000.0


class _FakeSpeedtest:
    """Offline stand-in for ``speedtest.Speedtest`` with fixed results."""

    def __init__(self, *args, **kwargs):
        self.results = self

    def get_servers(self, *args, **kwargs):
        return {}

    def get_best_server(self, *args, **kwargs):
        return {}

    def download(self, *args, **kwargs):
        return DOWNLOAD_BPS

    def upload(self, *args, **kwargs):
        return UPLOAD_BPS

    def share(self, *args, **kwargs):
        return "http://example.invalid/result.png"

    def dict(self, *args, **kwargs):
        return {"download": DOWNLOAD_BPS, "upload": UPLOAD_BPS}


speedtest.Speedtest = _FakeSpeedtest

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from ovos_bus_client.message import Message  # noqa: E402
from ovos_bus_client.session import Session  # noqa: E402
from ovoscope import CaptureSession, get_minicroft  # noqa: E402

SKILL_ID = "ovos-skill-speedtest.openvoiceos"

PIPELINE = [
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-low",
]

END2END_DIR = Path(__file__).parent

LANGS = [
    "ca-ES", "da-DK", "de-DE", "el-GR", "en-US", "es-ES", "eu-ES", "fa-IR",
    "fr-FR", "gl-ES", "it-IT", "kab", "nl-NL", "oc-FR", "pt-BR", "pt-PT",
    "ru-RU", "sv-SE", "tr-TR",
]

# utterances lifted verbatim from OTHER skills' golden-utterance slices,
# picked for lexical overlap with speedtest's "test"/"run"/"speed"/
# "internet" vocabulary, fired in a non-English session each.
CROSS_LANG_NEGATIVES = [
    ("run a timer for 5 minutes", "de-DE", "other-skill (alerts) phrasing, german session"),
    ("what's the weather", "fr-FR", "other-skill (weather) phrasing, french session"),
    ("play some music", "es-ES", "other-skill (music) phrasing, spanish session"),
    ("tell me a joke", "it-IT", "other-skill (jokes) phrasing, italian session"),
]


def _candidates(skill_id: str, intent_label: str) -> set:
    base = intent_label[:-len(".intent")] if intent_label.endswith(".intent") else intent_label
    return {f"{skill_id}:{intent_label}", f"{skill_id}:{base}"}


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


ALL_ROWS = []
for _lang in LANGS:
    for _row in _load_rows(_lang):
        ALL_ROWS.append(_row)


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


GOLDEN_ROWS = [pytest.param(r, id=_golden_id(r)) for r in ALL_ROWS]

_MINICROFTS = {}


def _get_minicroft(lang):
    mc = _MINICROFTS.get(lang)
    if mc is None:
        mc = get_minicroft([SKILL_ID], max_wait=150, lang=lang,
                            default_pipeline=PIPELINE)
        _MINICROFTS[lang] = mc
    return mc


@pytest.fixture(scope="module", autouse=True)
def _stop_all_minicrofts():
    yield
    for mc in _MINICROFTS.values():
        mc.stop()
    _MINICROFTS.clear()


def _types(mc, text, lang, session_id):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(PIPELINE)
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc, eof_msgs=["mycroft.skill.handler.start"])
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


@pytest.mark.timeout(180)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance_multilang(row):
    mc = _get_minicroft(row["lang"])
    candidates = _candidates(SKILL_ID, row["intent_label"])
    types = _types(mc, row["utterance"], row["lang"], f"golden-{_golden_id(row)}")
    assert any(t in candidates for t in types), (
        f"[{row['lang']}] {row['utterance']!r}: expected one of {sorted(candidates)!r}, got {types!r}"
    )


@pytest.mark.timeout(180)
@pytest.mark.parametrize("negative", CROSS_LANG_NEGATIVES, ids=lambda n: f"{n[1]}-{n[0]}")
def test_cross_language_negative(negative):
    text, lang, _why = negative
    mc = _get_minicroft(lang)
    types = _types(mc, text, lang, f"negative-{lang}-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"[{lang}] {text!r} was incorrectly claimed by {SKILL_ID}"
