"""End-to-end intent-routing and effect tests for ovos-skill-speedtest (en-US).

These assert *per-utterance* that the Padatious pipeline routes an utterance to the
``SpeedtestIntent`` handler AND that the handler speaks a line drawn from the
correct ``.dialog`` file for the outcome it measured. The expected line sets
are read directly from the locale files on disk, independent of the skill
handler under test, and asserted pairwise disjoint: if two dialog files
shared a line, speaking the wrong one would still pass a membership check,
so a shared line would silently degrade this into a routing test. Because
they are disjoint, a handler that speaks the wrong dialog -- or a fabricated
number instead of the measured one -- fails here even though it still emits
a ``speak`` message and still matches the correct intent name.

The handler runs a live network ``speedtest``. The suite patches
``speedtest.Speedtest`` with a deterministic stub *before* the MiniCroft loads
the skill, so the tests exercise pure intent routing plus the handler's own
formatting logic, with fixed, offline results, and stay fast and reproducible.
The stub can also be told to raise, to exercise the skill's failure-recovery
path, which a routing-only suite never reaches.

Run:
    uv run pytest test/end2end/ -v
"""
from pathlib import Path

import speedtest

DOWNLOAD_BPS = 50_000_000.0
UPLOAD_BPS = 10_000_000.0
PING_MS = 23.456

# Mutable so each test can pick the outcome the stub produces without
# rebuilding the (expensive) shared MiniCroft. Reset after every test.
_STUB_STATE = {"fail_at": None, "include_ping": False}


class _StubMeasurementError(RuntimeError):
    """Raised by the stub to simulate a failed measurement."""


class _FakeSpeedtest:
    """Offline stand-in for ``speedtest.Speedtest``.

    Reports fixed results by default. Set ``_STUB_STATE["fail_at"]`` to the
    name of a method to make that method raise instead, simulating a failed
    measurement at that stage.
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
from ovoscope import get_minicroft, CaptureSession, PADACIOSO_PIPELINE  # noqa: E402

SKILL_ID = "ovos-skill-speedtest.openvoiceos"
LANG = "en-US"
SPEEDTEST_INTENT = f"{SKILL_ID}:SpeedtestIntent"
LOCALE_EN_US = Path(__file__).parent.parent.parent / "locale" / "en-US"

# The measured-value strings the handler's own '%.2f' formatting produces
# for the stub's fixed results. Computed here from the same constants the
# stub returns, independent of the handler's internal variable names.
DOWNLOAD_MBPS = "%.2f" % (DOWNLOAD_BPS / 1_000_000)
UPLOAD_MBPS = "%.2f" % (UPLOAD_BPS / 1_000_000)
PING_STR = "%.2f" % PING_MS


def _dialog_template(name: str) -> str:
    """Read a shipped ``.dialog`` file and return its single template line.

    Every dialog this skill ships has exactly one line; a second line
    would mean a real dialog variant the tests below do not yet account
    for, so that case fails loudly instead of silently picking one.
    """
    path = LOCALE_EN_US / f"{name}.dialog"
    with open(path, encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]
    assert len(lines) == 1, (
        f"{name}.dialog has {len(lines)} lines; the effect tests assume "
        f"exactly one and must be updated to handle variants"
    )
    return lines[0]


RUNNING_TEMPLATE = _dialog_template("running")
RESULT_TEMPLATE = _dialog_template("result")
ERROR_TEMPLATE = _dialog_template("error")
PING_TEMPLATE = _dialog_template("ping")

# Raw (unrendered) templates, asserted pairwise disjoint below. Rendering
# result/ping with real values only ever narrows a template to one of its
# own instances, so disjoint templates guarantee disjoint rendered lines.
_ALL_DIALOG_TEMPLATES = {
    "running": RUNNING_TEMPLATE,
    "result": RESULT_TEMPLATE,
    "error": ERROR_TEMPLATE,
    "ping": PING_TEMPLATE,
}

EXPECTED_RESULT_LINE = RESULT_TEMPLATE.format(DOWN=DOWNLOAD_MBPS, UP=UPLOAD_MBPS)
EXPECTED_PING_LINE = PING_TEMPLATE.format(ping=PING_STR)


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


class TestDialogLinesArePairwiseDisjoint(TestCase):
    """A guard for the effect assertions below, not for the skill itself.

    If any two of these dialogs shared a line, a handler that spoke the
    wrong one for a given outcome would still pass a membership check
    against that shared line, so the effect tests would silently degrade
    into routing tests. This must hold before those tests are trusted.
    """

    def test_running_result_error_ping_share_no_line(self):
        names = list(_ALL_DIALOG_TEMPLATES)
        for i, name_a in enumerate(names):
            for name_b in names[i + 1:]:
                self.assertNotEqual(
                    _ALL_DIALOG_TEMPLATES[name_a], _ALL_DIALOG_TEMPLATES[name_b],
                    f"{name_a}.dialog and {name_b}.dialog share a line: "
                    f"{_ALL_DIALOG_TEMPLATES[name_a]!r}",
                )


class _SpeedtestEffectMixin:
    """Shared MiniCroft wiring for the speedtest skill."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def tearDown(self):
        _STUB_STATE["fail_at"] = None
        _STUB_STATE["include_ping"] = False

    def _capture(self, utterance: str):
        # pytest imports every sibling test module in this directory during
        # collection, and each one monkey-patches the same module-level
        # ``speedtest.Speedtest`` attribute at import time, so whichever
        # file happens to import last silently wins for every test in the
        # session. Re-apply this file's stub immediately before capturing
        # so the failure-toggling behaviour below is actually exercised.
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

    def assertRoutesToSpeedtest(self, utterance: str, messages=None):
        messages = messages if messages is not None else self._capture(utterance)
        types = [m.msg_type for m in messages]
        self.assertIn(
            SPEEDTEST_INTENT, types,
            f"expected {SPEEDTEST_INTENT!r} to be matched for {utterance!r}, "
            f"got {types}",
        )
        return messages

    def assertSpokeExactly(self, spoken, expected_line, other_than):
        """The expected line was spoken, and none of the other outcomes'
        dialog lines were -- catching a handler that speaks the right
        *kind* of thing (some ``speak`` message) but the wrong dialog."""
        self.assertIn(
            expected_line, spoken,
            f"expected {expected_line!r} to be spoken, got {spoken}",
        )
        for name in other_than:
            other_line = _ALL_DIALOG_TEMPLATES[name]
            self.assertNotIn(
                other_line, spoken,
                f"{name}.dialog's line was spoken alongside the expected "
                f"outcome: {spoken}",
            )


class TestSpeedtestIntent(_SpeedtestEffectMixin, TestCase):
    """SpeedtestIntent routes across the SpeedtestIntent.intent phrasings
    and speaks the measured result -- read from result.dialog -- back."""

    def test_run_speed_test_reports_measured_speed(self):
        messages = self.assertRoutesToSpeedtest("run speed test")
        spoken = self._spoken(messages)
        self.assertSpokeExactly(
            spoken, EXPECTED_RESULT_LINE, other_than=("error", "ping"),
        )

    def test_start_internet_speed_test_reports_measured_speed(self):
        messages = self.assertRoutesToSpeedtest("start internet speed test")
        spoken = self._spoken(messages)
        self.assertSpokeExactly(
            spoken, EXPECTED_RESULT_LINE, other_than=("error", "ping"),
        )

    def test_speaks_running_dialog_while_measuring(self):
        messages = self.assertRoutesToSpeedtest("run speed test")
        spoken = self._spoken(messages)
        self.assertIn(
            RUNNING_TEMPLATE, spoken,
            f"expected the in-progress line from running.dialog to be "
            f"spoken while the measurement is under way, got {spoken}",
        )

    def test_reports_ping_when_the_measurement_includes_it(self):
        _STUB_STATE["include_ping"] = True
        messages = self.assertRoutesToSpeedtest("run speed test")
        spoken = self._spoken(messages)
        self.assertSpokeExactly(
            spoken, EXPECTED_RESULT_LINE, other_than=("error",),
        )
        self.assertIn(
            EXPECTED_PING_LINE, spoken,
            f"expected the measured ping to be reported via ping.dialog, "
            f"got {spoken}",
        )

    def test_failed_measurement_speaks_recovery_line_not_a_fabricated_speed(self):
        _STUB_STATE["fail_at"] = "download"
        messages = self.assertRoutesToSpeedtest("run speed test")
        spoken = self._spoken(messages)
        self.assertSpokeExactly(
            spoken, ERROR_TEMPLATE, other_than=("result", "ping"),
        )
        # A handler that swallows the exception and reports a stale or
        # default number would still pass a routing-only check; assert no
        # measured value reaches the user when the measurement failed.
        self.assertFalse(
            any(DOWNLOAD_MBPS in utt or UPLOAD_MBPS in utt for utt in spoken),
            f"a speed value was spoken despite the measurement failing: {spoken}",
        )

    def test_failed_server_selection_speaks_recovery_line(self):
        _STUB_STATE["fail_at"] = "get_best_server"
        messages = self.assertRoutesToSpeedtest("run speed test")
        spoken = self._spoken(messages)
        self.assertSpokeExactly(
            spoken, ERROR_TEMPLATE, other_than=("result", "ping"),
        )
