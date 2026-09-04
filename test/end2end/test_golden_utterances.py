"""Golden-utterance end-to-end coverage for ovos-skill-speedtest (en-US).

The golden corpus (``golden_utterances.jsonl``) is a vendored slice of the
shared ovoscope golden-utterance dataset, keyed by
``skill_id == "ovos-skill-speedtest.openvoiceos"``. One shared ``MiniCroft``
(module-scoped fixture) is booted for the whole suite.

The handler runs a live network ``speedtest``; ``speedtest.Speedtest`` is
patched with a deterministic offline stub *before* MiniCroft loads the
skill (same technique as ``test_intents_en_us.py``) so the suite stays
fast, reproducible, and network-free.

Run:
    uv run pytest test/end2end/ -v
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
from ovoscope import CaptureSession, get_minicroft, PADACIOSO_PIPELINE  # noqa: E402

SKILL_ID = "ovos-skill-speedtest.openvoiceos"
LANG = "en-US"

GOLDEN_PATH = Path(__file__).parent / "golden_utterances.jsonl"

# utterances lifted verbatim from OTHER skills' golden-utterance slices,
# picked for lexical overlap with speedtest's "test"/"run"/"speed"/"internet"
# vocabulary.
NEGATIVE_UTTERANCES = [
    ("run a timer for 5 minutes", "ovos-skill-alerts.openvoiceos"),
    ("what's the weather", "ovos-skill-weather.openvoiceos"),
    ("play some music", "ovos-skill-music.openvoiceos"),
    ("turn off the wifi", "ovos-skill-homeassistant.openvoiceos"),
    ("perform a system update", "ovos-skill-os-updates.openvoiceos"),
    ("tell me a joke", "ovos-skill-icanhazdadjokes.openvoiceos"),
    ("check my email", "ovos-skill-email.openvoiceos"),
    ("what's my ip address", "ovos-skill-network-info.openvoiceos"),
    ("how fast is my computer", "ovos-skill-system-info.openvoiceos"),
    ("download this file", "ovos-skill-downloads.openvoiceos"),
    ("upload a photo", "ovos-skill-photos.openvoiceos"),
    ("run a diagnostic", "ovos-skill-diagnostics.openvoiceos"),
]


def _candidates(skill_id: str, intent_label: str) -> set:
    """padatious/padacioso plugin versions register the matched-intent bus
    event under different normalizations of the ``.intent`` filename
    basename -- candidates cover both the suffixed and unsuffixed forms.
    Adapt intent names (eg. "SpeedtestIntent") have no ``.intent`` suffix
    to strip."""
    base = intent_label[:-len(".intent")] if intent_label.endswith(".intent") else intent_label
    return {f"{skill_id}:{intent_label}", f"{skill_id}:{base}"}


def _load_golden_rows():
    # "internet connection test benchmark" is flagged needs_manual: the old
    # Adapt intent matched it via keyword presence regardless of word order
    # (Run="benchmark" at the end, Speedtest="internet connection test" at
    # the start); SpeedtestIntent.intent is a fixed Padatious template and
    # does not model that ordering.
    rows = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


GOLDEN_ROWS = [pytest.param(r, id=r["utterance"]) for r in _load_golden_rows()]


@pytest.fixture(scope="module")
def minicroft():
    mc = get_minicroft([SKILL_ID])
    yield mc
    mc.stop()


def _types(mc, text, session_id):
    session = Session(session_id)
    session.lang = LANG
    session.pipeline = PADACIOSO_PIPELINE
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc)
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


def _golden_id(row):
    return row["utterance"]


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance(minicroft, row):
    candidates = _candidates(SKILL_ID, row["intent_label"])
    types = _types(minicroft, row["utterance"], f"golden-{_golden_id(row)}")
    assert any(t in candidates for t in types), (
        f"{row['utterance']!r}: expected one of {sorted(candidates)!r}, got {types!r}"
    )


@pytest.mark.timeout(60)
@pytest.mark.parametrize("negative", NEGATIVE_UTTERANCES, ids=lambda n: n[0])
def test_negative_confusable_not_claimed(minicroft, negative):
    text, source_skill = negative
    types = _types(minicroft, text, f"negative-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"{text!r} (from {source_skill}) was incorrectly claimed by {SKILL_ID}"
