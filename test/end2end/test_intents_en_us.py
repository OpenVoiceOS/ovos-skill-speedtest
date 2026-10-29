"""End-to-end intent and effect tests for ovos-skill-speedtest (en-US).

Each test routes an utterance to the ``speedtest_intent`` handler on the m2v
prototype pipeline, then asserts what the handler speaks. The expected lines
are rendered from the shipped en-US ``.dialog`` files with the values the
stub reports, so a handler that speaks the wrong dialog, or a number it did
not measure, fails even when it still emits a ``speak`` message.

The handler runs a live network ``speedtest``. The suite patches
``speedtest.Speedtest`` with an offline stub *before* the MiniCroft loads the
skill. The stub can also raise at a named stage, which drives the handler's
failure path.

Run:
    uv run pytest test/end2end/ -v
"""
from pathlib import Path

import speedtest

DOWNLOAD_BPS = 50_000_000.0
UPLOAD_BPS = 10_000_000.0
PING_MS = 23.456

# Each test picks the outcome the stub produces without a new MiniCroft;
# tearDown resets it.
_STUB_STATE = {"fail_at": None, "include_ping": False}


class _StubMeasurementError(RuntimeError):
    """Raised by the stub to simulate a failed measurement."""


class _FakeSpeedtest:
    """Offline stand-in for ``speedtest.Speedtest``.

    Reports fixed results. ``_STUB_STATE["fail_at"]`` names a method that
    raises instead.
    """

    def __init__(self, *args, **kwargs):
        self.results = self

    def _maybe_fail(self, name):
        if _STUB_STATE["fail_at"] == name:
            raise _StubMeasurementError(f"stubbed failure at {name}")

    def get_servers(self, *args, **kwargs):
        self._maybe_fail("get_servers")
        return {}

    def get_best_server(self, *args, **kwargs):
        self._maybe_fail("get_best_server")
        return {}

    def download(self, *args, **kwargs):
        self._maybe_fail("download")
        return DOWNLOAD_BPS

    def upload(self, *args, **kwargs):
        self._maybe_fail("upload")
        return UPLOAD_BPS

    def share(self, *args, **kwargs):
        return "http://example.invalid/result.png"

    def dict(self, *args, **kwargs):
        result = {"download": DOWNLOAD_BPS, "upload": UPLOAD_BPS}
        if _STUB_STATE["include_ping"]:
            result["ping"] = PING_MS
        return result


speedtest.Speedtest = _FakeSpeedtest

from unittest import TestCase  # noqa: E402

from ovos_bus_client.message import Message  # noqa: E402
from ovos_bus_client.session import Session  # noqa: E402
from ovos_spec_tools.dialog import render  # noqa: E402
from ovos_spec_tools.resources import LocaleResources  # noqa: E402
from ovoscope import CaptureSession  # noqa: E402
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft  # noqa: E402

SKILL_ID = "ovos-skill-speedtest.openvoiceos"
LANG = "en-US"
SPEEDTEST_INTENT = f"{SKILL_ID}:speedtest_intent"
LOCALE = LocaleResources(str(Path(__file__).parents[2] / "locale"))

# The strings the handler's '%.2f' formatting gives for the stub's results,
# computed from the stub's own constants.
DOWNLOAD_MBPS = "%.2f" % (DOWNLOAD_BPS / 1_000_000)
UPLOAD_MBPS = "%.2f" % (UPLOAD_BPS / 1_000_000)
PING_STR = "%.2f" % PING_MS


def _dialog(name: str, **slots) -> str:
    """The one line of a shipped en-US dialog, rendered with ``slots``.

    A second line would be a variant these tests do not handle, so it fails.
    """
    phrases = LOCALE.load_dialog(name, LANG)
    assert len(phrases) == 1, f"{name}.dialog has {len(phrases)} lines, the tests expect one"
    return render(phrases, slots=slots)


RUNNING_LINE = _dialog("running")
RESULT_LINE = _dialog("result", down=DOWNLOAD_MBPS, up=UPLOAD_MBPS)
PING_LINE = _dialog("ping", ping=PING_STR)
ERROR_LINE = _dialog("error")
DIALOG_LINES = {"running": RUNNING_LINE, "result": RESULT_LINE,
                "ping": PING_LINE, "error": ERROR_LINE}


def _session(tag: str) -> Session:
    session = Session(f"e2e-en_us-speedtest-{tag}")
    session.lang = LANG
    session.pipeline = PIPELINE
    return session


def _utterance(utt: str, session: Session) -> Message:
    return Message(
        "recognizer_loop:utterance",
        {"utterances": [utt], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )


class TestDialogLinesAreDistinct(TestCase):
    """The effect tests below tell outcomes apart by their spoken line, which
    only works when no two dialogs share a line."""

    def test_running_result_ping_error_share_no_line(self):
        lines = list(DIALOG_LINES.values())
        self.assertEqual(len(set(lines)), len(lines), DIALOG_LINES)


class _SpeedtestRoutingMixin:
    """Shared MiniCroft wiring for the speedtest skill."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_prototype_minicroft([SKILL_ID], lang=LANG)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def tearDown(self):
        _STUB_STATE["fail_at"] = None
        _STUB_STATE["include_ping"] = False

    def _capture(self, utterance: str):
        # Every module in test/end2end patches speedtest.Speedtest at import,
        # and the last one imported wins for the whole session. Put this
        # module's stub back so its failure switch takes effect.
        speedtest.Speedtest = _FakeSpeedtest
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

    def spoken_after_routing(self, utterance: str):
        messages = self._capture(utterance)
        TALLY.assert_routed(utterance, SPEEDTEST_INTENT, [m.msg_type for m in messages])
        return self._spoken(messages)

    def assertSpokeOnly(self, spoken, expected, forbidden):
        """Each ``expected`` dialog line was spoken and no ``forbidden`` one was."""
        for name in expected:
            self.assertIn(DIALOG_LINES[name], spoken, f"{name}.dialog not spoken")
        for name in forbidden:
            self.assertNotIn(DIALOG_LINES[name], spoken, f"{name}.dialog spoken")


class TestSpeedtestIntent(_SpeedtestRoutingMixin, TestCase):
    """speedtest_intent routes and speaks the measured result."""

    def test_run_speed_test(self):
        spoken = self.spoken_after_routing("run speed test")
        self.assertSpokeOnly(spoken, ("running", "result"), ("ping", "error"))

    def test_start_internet_speed_test(self):
        spoken = self.spoken_after_routing("start internet speed test")
        self.assertSpokeOnly(spoken, ("running", "result"), ("ping", "error"))

    def test_reports_ping_when_the_measurement_includes_it(self):
        _STUB_STATE["include_ping"] = True
        spoken = self.spoken_after_routing("run speed test")
        self.assertSpokeOnly(spoken, ("running", "result", "ping"), ("error",))

    def test_failed_download_speaks_the_error_and_no_speed(self):
        _STUB_STATE["fail_at"] = "download"
        spoken = self.spoken_after_routing("run speed test")
        self.assertSpokeOnly(spoken, ("running", "error"), ("result", "ping"))
        self.assertFalse(
            any(DOWNLOAD_MBPS in utt or UPLOAD_MBPS in utt for utt in spoken),
            f"a speed was spoken although the measurement failed: {spoken}",
        )

    def test_failed_server_selection_speaks_the_error(self):
        _STUB_STATE["fail_at"] = "get_best_server"
        spoken = self.spoken_after_routing("run speed test")
        self.assertSpokeOnly(spoken, ("running", "error"), ("result", "ping"))
