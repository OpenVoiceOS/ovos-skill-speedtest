import unittest
from unittest.mock import MagicMock, patch

import speedtest

from ovos_utils.fakebus import FakeBus
from ovos_skill_speedtest import SpeedTestSkill

DOWNLOAD_BPS = 50_000_000.0
UPLOAD_BPS = 10_000_000.0
PING_MS = 12.345


class _FakeSpeedtest:
    """Offline stand-in for ``speedtest.Speedtest`` with a fixed ping."""

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
        return {"download": DOWNLOAD_BPS, "upload": UPLOAD_BPS, "ping": PING_MS}


class TestPingIsSpoken(unittest.TestCase):
    """The measured ``ping`` latency must be spoken back to the user."""

    def setUp(self):
        self.skill_id = "ovos-skill-speedtest.openvoiceos"
        bus = FakeBus()
        self.skill = SpeedTestSkill()
        self.skill._startup(bus, self.skill_id)
        self.skill.speak_dialog = MagicMock()

    def test_ping_spoken_after_speedtest(self):
        with patch.object(speedtest, "Speedtest", _FakeSpeedtest):
            self.skill.handle_speedtest_intent(MagicMock())

        ping_calls = [
            call for call in self.skill.speak_dialog.call_args_list
            if call.args and call.args[0] == "ping"
        ]
        self.assertTrue(
            ping_calls,
            f"expected a speak_dialog('ping', ...) call, got "
            f"{self.skill.speak_dialog.call_args_list}",
        )
        self.assertEqual(ping_calls[0].args[1], {"ping": "12.35"})
