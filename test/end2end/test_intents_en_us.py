"""End-to-end intent-routing tests for ovos-skill-speedtest (en-US).

These assert *per-utterance* that the Padatious pipeline routes an utterance to the
``SpeedtestIntent`` handler and that the skill speaks the measured result back.
They deliberately use subset assertions over the captured message stream rather
than a strict full-sequence match: the exact ordered sequence drifts across
ovos-core / ovoscope releases (e.g. an extra ``ovos.intent.matched`` message,
or ``speak`` vs ``ovos.utterance.speak``), which is orthogonal to what this
skill is responsible for.

The handler runs a live network ``speedtest``. The suite patches
``speedtest.Speedtest`` with a deterministic stub *before* the MiniCroft loads
the skill, so the tests exercise pure intent routing with fixed, offline
results and stay fast and reproducible.

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

from unittest import TestCase  # noqa: E402

from ovos_bus_client.message import Message  # noqa: E402
from ovos_bus_client.session import Session  # noqa: E402
from ovoscope import get_minicroft, CaptureSession, PADACIOSO_PIPELINE  # noqa: E402

SKILL_ID = "ovos-skill-speedtest.openvoiceos"
LANG = "en-US"
SPEEDTEST_INTENT = f"{SKILL_ID}:SpeedtestIntent"


def _session(tag: str) -> Session:
    session = Session(f"e2e-en_us-speedtest-{tag}")
    session.lang = LANG
    session.pipeline = PADACIOSO_PIPELINE
    return session


def _utterance(utt: str, session: Session) -> Message:
    return Message(
        "recognizer_loop:utterance",
        {"utterances": [utt], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )


class _SpeedtestRoutingMixin:
    """Shared MiniCroft wiring for the speedtest skill."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _capture(self, utterance: str):
        session = _session(str(hash(utterance)))
        capture = CaptureSession(self.minicroft)
        capture.capture(_utterance(utterance, session), timeout=30)
        return capture.finish()

    def _spoken(self, messages):
        return [
            m.data.get("utterance", "")
            for m in messages
            if m.msg_type in ("speak", "ovos.utterance.speak")
        ]

    def assertRoutesToSpeedtest(self, utterance: str):
        messages = self._capture(utterance)
        types = [m.msg_type for m in messages]
        self.assertIn(
            SPEEDTEST_INTENT, types,
            f"expected {SPEEDTEST_INTENT!r} to be matched for {utterance!r}, "
            f"got {types}",
        )
        spoken = self._spoken(messages)
        self.assertTrue(
            any("50.00" in utt for utt in spoken),
            f"expected a spoken result reporting the measured download speed "
            f"for {utterance!r}, got {spoken}",
        )


class TestSpeedtestIntent(_SpeedtestRoutingMixin, TestCase):
    """SpeedtestIntent routes across the SpeedtestIntent.intent phrasings."""

    def test_run_speed_test(self):
        self.assertRoutesToSpeedtest("run speed test")

    def test_start_internet_speed_test(self):
        self.assertRoutesToSpeedtest("start internet speed test")
