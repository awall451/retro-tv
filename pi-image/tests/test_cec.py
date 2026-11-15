"""retro-tv-cec.py: reading cec-ctl's output (no CEC hardware needed).
Run: python3 -m unittest discover -s pi-image/tests"""
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("cec", os.path.join(HERE, "..", "config", "retro-tv-cec.py"))
cec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cec)

# What cec-ctl prints for "-t 0 --give-device-power-status" (v4l-utils 1.2x/1.30).
REPLY_ON = """Transmit from Playback Device 1 to TV (4 to 0):
GIVE_DEVICE_POWER_STATUS (0x8f)
\tSequence: 6 Tx Timestamp: 4521.316s
    Received from TV (0):
REPORT_POWER_STATUS (0x90):
\t\tpwr-state: on (0x00)
\tSequence: 9 Rx Timestamp: 4521.364s
"""
REPLY_STANDBY = REPLY_ON.replace("pwr-state: on (0x00)", "pwr-state: standby (0x01)")
REPLY_NACK = """Transmit from Playback Device 1 to TV (4 to 0):
GIVE_DEVICE_POWER_STATUS (0x8f)
\tSequence: 7 Tx Timestamp: 4531.320s
\tTx, Not Acknowledged (4), Max Retries
"""


class PowerTest(unittest.TestCase):
    def test_on_standby_and_no_answer(self):
        self.assertEqual(cec.parse_power(REPLY_ON), "on")
        self.assertEqual(cec.parse_power(REPLY_STANDBY), "standby")
        self.assertIsNone(cec.parse_power(REPLY_NACK))
        self.assertIsNone(cec.parse_power(""))

    def test_transitions_and_other_spellings(self):
        self.assertEqual(cec.parse_power("pwr-state: to-on (0x02)"), "on")
        self.assertEqual(cec.parse_power("pwr-state: to-standby (0x03)"), "standby")
        self.assertEqual(cec.parse_power("pwr-state: in-transition-standby-to-on (0x02)"), "on")
        self.assertEqual(cec.parse_power("pwr-state: in-transition-on-to-standby (0x03)"), "standby")
        # A name this does not know: the code decides.
        self.assertEqual(cec.parse_power("pwr-state: Standby-Mode (0x01)"), "standby")
        self.assertIsNone(cec.parse_power("pwr-state: weird (0x07)"))

    def test_last_report_wins(self):
        self.assertEqual(cec.parse_power(REPLY_ON + REPLY_STANDBY), "standby")


class MonitorTest(unittest.TestCase):
    def test_messages(self):
        self.assertEqual(cec.parse_message("Received from TV to all (0 to 15): STANDBY (0x36)"), (0, "STANDBY"))
        self.assertEqual(cec.parse_message("Received from TV to Playback Device 1 (0 to 4): USER_CONTROL_PRESSED (0x44):"),
                         (0, "USER_CONTROL_PRESSED"))
        self.assertEqual(cec.parse_message("Received from Audio System to all (5 to 15): SET_SYSTEM_AUDIO_MODE (0x72):"),
                         (5, "SET_SYSTEM_AUDIO_MODE"))
        self.assertIsNone(cec.parse_message("\tpwr-state: on (0x00)"))
        self.assertIsNone(cec.parse_message("Transmit from Playback Device 1 to TV (4 to 0):"))


class AddressTest(unittest.TestCase):
    def test_phys_addr(self):
        self.assertEqual(cec.parse_phys_addr("Physical Address           : 3.0.0.0\n"), "3.0.0.0")
        self.assertEqual(cec.parse_phys_addr("\tPhysical Address: 1.2.0.0"), "1.2.0.0")
        self.assertIsNone(cec.parse_phys_addr("Physical Address           : f.f.f.f"))
        self.assertIsNone(cec.parse_phys_addr("no adapter"))


class DeviceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.drm = os.path.join(self.tmp.name, "drm")
        self.dev = os.path.join(self.tmp.name, "dev")
        os.makedirs(self.dev)
        for n in (0, 1):
            open(os.path.join(self.dev, f"cec{n}"), "w").close()

    def tearDown(self):
        self.tmp.cleanup()

    def port(self, n, status):
        d = os.path.join(self.drm, f"card1-HDMI-A-{n}")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "status"), "w") as f:
            f.write(status + "\n")

    def test_connected_port_wins(self):
        self.port(1, "disconnected")
        self.port(2, "connected")
        self.assertEqual(cec.pick_device({}, self.drm, self.dev), os.path.join(self.dev, "cec1"))

    def test_setting_and_fallback(self):
        self.assertEqual(cec.pick_device({"CEC_DEVICE": "/dev/cec7"}, self.drm, self.dev), "/dev/cec7")
        self.assertEqual(cec.pick_device({}, self.drm, self.dev), os.path.join(self.dev, "cec0"))
        self.assertIsNone(cec.pick_device({}, self.drm, os.path.join(self.tmp.name, "none")))


if __name__ == "__main__":
    unittest.main()
