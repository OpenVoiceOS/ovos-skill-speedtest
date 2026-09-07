"""End-to-end proof that the verb/query phrasings added for issue #62 route
to ``SpeedtestIntent`` and that a generic "check my X" phrase from a sibling
skill's domain is not claimed.

The handler runs a live network ``speedtest``. ``speedtest.Speedtest`` is
patched with a deterministic stub *before* MiniCroft loads the skill (same
technique as the other end2end suites), so this stays fast, offline, and
reproducible.

Run:
    uv run pytest test/end2end/test_new_phrasings.py -v
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

NEW_PHRASINGS = [
    "check my internet speed",
    "test my wifi speed",
    "what's my download speed",
    "what's my upload speed",
]

# lexically close to speedtest's vocabulary ("check", "my") but out of
# domain -- must never be claimed by SpeedtestIntent.
NEGATIVE_UTTERANCES = [
    "check my email",
]


def _session(tag: str) -> Session:
    session = Session(f"e2e-en_us-speedtest-newphrasing-{tag}")
    session.lang = LANG
    session.pipeline = PADACIOSO_PIPELINE
    return session


def _utterance(utt: str, session: Session) -> Message:
    return Message(
        "recognizer_loop:utterance",
        {"utterances": [utt], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )


class TestNewPhrasingsRouteToSpeedtest(TestCase):
    """Verbs/query-forms added for issue #62 must route to SpeedtestIntent."""

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

    def test_check_my_internet_speed(self):
        messages = self._capture("check my internet speed")
        types = [m.msg_type for m in messages]
        self.assertIn(SPEEDTEST_INTENT, types, types)

    def test_test_my_wifi_speed(self):
        messages = self._capture("test my wifi speed")
        types = [m.msg_type for m in messages]
        self.assertIn(SPEEDTEST_INTENT, types, types)

    def test_whats_my_download_speed(self):
        messages = self._capture("what's my download speed")
        types = [m.msg_type for m in messages]
        self.assertIn(SPEEDTEST_INTENT, types, types)

    def test_whats_my_upload_speed(self):
        messages = self._capture("what's my upload speed")
        types = [m.msg_type for m in messages]
        self.assertIn(SPEEDTEST_INTENT, types, types)

    def test_check_my_email_not_claimed(self):
        messages = self._capture("check my email")
        types = [m.msg_type for m in messages]
        self.assertNotIn(
            SPEEDTEST_INTENT, types,
            f"'check my email' must not be claimed by {SPEEDTEST_INTENT!r}, "
            f"got {types}",
        )
