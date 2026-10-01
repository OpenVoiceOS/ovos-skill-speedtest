"""Multilingual golden-utterance end-to-end coverage for ovos-skill-speedtest.

Every ``golden_utterances_<lang>.jsonl`` file in this directory runs, rows
marked ``needs_manual`` included. Each row's utterance is a mechanical
expansion of one line of that locale's own ``speedtest_intent.intent``.

One ``MiniCroft`` is booted per locale with only the padatious and padacioso
pipelines, so a row passes only when the ``.intent`` file of its locale
matches it. The test asserts the matched intent name equals the row's
``intent_label``.

The handler runs a live network speed test, so ``speedtest.Speedtest`` is
replaced with an offline stub before the skill loads.

Run:
    pytest test/end2end/test_golden_utterances_multilang.py -v
"""
import speedtest


class _FakeSpeedtest:
    """Offline stand-in for ``speedtest.Speedtest`` with fixed results."""

    def __init__(self, *args, **kwargs):
        self.results = self

    def get_servers(self, *args, **kwargs):
        return {}

    def get_best_server(self, *args, **kwargs):
        return {}

    def download(self, *args, **kwargs):
        return 50_000_000.0

    def upload(self, *args, **kwargs):
        return 10_000_000.0

    def share(self, *args, **kwargs):
        return "http://example.invalid/result.png"

    def dict(self, *args, **kwargs):
        return {"download": 50_000_000.0, "upload": 10_000_000.0}


speedtest.Speedtest = _FakeSpeedtest

import json  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import TestCase  # noqa: E402

from ovos_bus_client.message import Message  # noqa: E402
from ovos_bus_client.session import Session  # noqa: E402
from ovoscope import CaptureSession, get_minicroft  # noqa: E402

SKILL_ID = "ovos-skill-speedtest.openvoiceos"

PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-medium",
]

END2END_DIR = Path(__file__).parent

LANGS = sorted(
    p.stem.removeprefix("golden_utterances_")
    for p in END2END_DIR.glob("golden_utterances_*.jsonl")
)

NEGATIVE_UTTERANCES = [
    ("what's the weather like today", "en-US"),
    ("tell me a joke", "en-US"),
    ("check my email", "en-US"),
    ("set the volume to 50 percent", "en-US"),
]


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _matched_names(mc, text, lang, session_id):
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
    return [m.data.get("intent_name") for m in capture.finish()
            if m.msg_type == "ovos.intent.matched"]


def _make_locale_test_case(lang):
    rows = _load_rows(lang)
    negatives = [text for text, neg_lang in NEGATIVE_UTTERANCES if neg_lang == lang]

    class _LocaleGoldenCase(TestCase):
        @classmethod
        def setUpClass(cls):
            cls.minicroft = get_minicroft([SKILL_ID], max_wait=180, lang=lang)

        @classmethod
        def tearDownClass(cls):
            if getattr(cls, "minicroft", None):
                cls.minicroft.stop()

        def _check_row(self, row):
            self.assertEqual(row["lang"], lang)
            expected = f"{SKILL_ID}:{row['intent_label']}"
            names = _matched_names(self.minicroft, row["utterance"], lang,
                                   f"golden-{lang}-{row['utterance']}")
            self.assertEqual(
                names, [expected],
                f"[{lang}] {row['utterance']!r}: expected {expected!r}, got {names!r}",
            )

        def _check_negative(self, text):
            names = _matched_names(self.minicroft, text, lang, f"negative-{lang}-{text}")
            claimed = [n for n in names if (n or "").startswith(f"{SKILL_ID}:")]
            self.assertEqual(claimed, [], f"[{lang}] {text!r} was claimed by {SKILL_ID}")

    for i, row in enumerate(rows):
        def _test(self, row=row):
            self._check_row(row)
        _test.__name__ = f"test_golden_{i:03d}_{row['intent_label']}"
        setattr(_LocaleGoldenCase, _test.__name__, _test)

    for i, text in enumerate(negatives):
        def _neg_test(self, text=text):
            self._check_negative(text)
        _neg_test.__name__ = f"test_negative_{i:03d}"
        setattr(_LocaleGoldenCase, _neg_test.__name__, _neg_test)

    _LocaleGoldenCase.__name__ = f"TestGolden_{lang.replace('-', '_')}"
    _LocaleGoldenCase.__qualname__ = _LocaleGoldenCase.__name__
    return _LocaleGoldenCase


for _lang in LANGS:
    _case = _make_locale_test_case(_lang)
    globals()[_case.__name__] = _case
del _lang, _case
