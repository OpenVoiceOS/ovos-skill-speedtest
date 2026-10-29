"""End-to-end proof that ``speedtest_intent`` is an ``.intent`` file
match, not an Adapt keyword match.

The session pipeline has no Adapt stage, so this request can only route if
``speedtest_intent.intent`` carries it rather than the ``run``/``speedtest``
Adapt vocabulary.

The handler runs a live network ``speedtest``; ``speedtest.Speedtest`` is
patched with a deterministic offline stub *before* MiniCroft loads the
skill (same technique as ``test_intents_en_us.py``).

Run:
    uv run pytest test/end2end/test_intent_file_migration.py -v
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
from ovoscope import CaptureSession  # noqa: E402
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft  # noqa: E402

SKILL_ID = "ovos-skill-speedtest.openvoiceos"
LANG = "en-US"
SPEEDTEST_INTENT = f"{SKILL_ID}:speedtest_intent"


def _session(tag: str) -> Session:
    session = Session(f"e2e-en_us-speedtest-intentfile-{tag}")
    session.lang = LANG
    session.pipeline = PIPELINE
    return session


def _utterance(utt: str, session: Session) -> Message:
    return Message(
        "recognizer_loop:utterance",
        {"utterances": [utt], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )


class TestSpeedtestIntentFile(TestCase):
    """speedtest_intent must route via its .intent file alone."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_prototype_minicroft([SKILL_ID], lang=LANG)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def test_run_a_speed_test_intent_file_only(self):
        session = _session("run-a-speed-test")
        capture = CaptureSession(self.minicroft)
        capture.capture(_utterance("run a speed test", session), timeout=30)
        messages = capture.finish()
        types = [m.msg_type for m in messages]
        TALLY.assert_routed("run a speed test", SPEEDTEST_INTENT, types)
        spoken = [
            m.data.get("utterance", "")
            for m in messages
            if m.msg_type in ("speak", "ovos.utterance.speak")
        ]
        self.assertTrue(
            any("50.00" in utt for utt in spoken),
            f"expected a spoken result reporting the measured download "
            f"speed, got {spoken}",
        )
