import unittest
from unittest.mock import MagicMock, patch

import speedtest

from ovos_utils.fakebus import FakeBus
from ovos_skill_speedtest import SpeedTestSkill

DOWNLOAD_BPS = 50_000_000.0
UPLOAD_BPS = 10_000_000.0


class _FakeSpeedtest:
    """Offline stand-in for ``speedtest.Speedtest`` with fixed speeds."""

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


class TestResultDialogSlots(unittest.TestCase):
    """The result dialog must use lowercase 'down' and 'up' slot names."""

    def setUp(self):
        self.skill_id = "ovos-skill-speedtest.openvoiceos"
        bus = FakeBus()
        self.skill = SpeedTestSkill()
        self.skill._startup(bus, self.skill_id)
        self.skill.speak_dialog = MagicMock()

    def test_result_dialog_uses_lowercase_slot_names(self):
        """The speak_dialog call must use lowercase 'down' and 'up' keys."""
        with patch.object(speedtest, "Speedtest", _FakeSpeedtest):
            self.skill.handle_speedtest_intent(MagicMock())

        result_calls = [
            call for call in self.skill.speak_dialog.call_args_list
            if call.args and call.args[0] == "result"
        ]
        self.assertTrue(
            result_calls,
            f"expected a speak_dialog('result', ...) call, got "
            f"{self.skill.speak_dialog.call_args_list}",
        )
        # Check that the keys are lowercase 'down' and 'up'
        result_data = result_calls[0].args[1]
        self.assertIn("down", result_data,
                     f"expected 'down' key in {result_data}")
        self.assertIn("up", result_data,
                     f"expected 'up' key in {result_data}")
        self.assertNotIn("DOWN", result_data,
                        f"unexpected uppercase 'DOWN' key in {result_data}")
        self.assertNotIn("UP", result_data,
                        f"unexpected uppercase 'UP' key in {result_data}")

    def test_result_dialog_values_are_formatted_correctly(self):
        """The values passed to the dialog must be formatted with 2 decimals."""
        with patch.object(speedtest, "Speedtest", _FakeSpeedtest):
            self.skill.handle_speedtest_intent(MagicMock())

        result_calls = [
            call for call in self.skill.speak_dialog.call_args_list
            if call.args and call.args[0] == "result"
        ]
        result_data = result_calls[0].args[1]
        # Expected values: 50_000_000 / 1_000_000 = 50.00
        # Expected values: 10_000_000 / 1_000_000 = 10.00
        self.assertEqual(result_data["down"], "50.00")
        self.assertEqual(result_data["up"], "10.00")
