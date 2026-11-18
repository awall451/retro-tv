"""retro-tv-cec.py: reading cec-ctl's output (no CEC hardware needed).
Run: python3 -m unittest discover -s pi-image/tests"""
import importlib.util
import json
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


class BusTest(unittest.TestCase):
    """The monitor's lines, fed to Tv.see() as cec-ctl -m prints them; no cec-ctl runs."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = cec.STATE, cec.STATE_DIR, cec.AUTO
        cec.STATE_DIR = os.path.join(self.tmp.name, "cec")
        cec.STATE = os.path.join(cec.STATE_DIR, "state.json")
        cec.AUTO = True
        self.tv = cec.Tv("/dev/cec0")
        self.tv.write()                    # as main() does at start

    def tearDown(self):
        cec.STATE, cec.STATE_DIR, cec.AUTO = self.saved
        self.tmp.cleanup()

    def feed(self, text):
        for line in text.splitlines(keepends=True):
            self.tv.see(line)

    def published(self):
        with open(cec.STATE, encoding="utf-8") as f:
            return json.load(f)["power"]

    def test_tv_standby_and_report(self):
        self.feed("Received from TV to all (0 to 15): STANDBY (0x36)\n")
        self.assertEqual(self.published(), "standby")
        self.feed("Received from TV to Playback Device 1 (0 to 4): REPORT_POWER_STATUS (0x90):\n"
                  "\tpwr-state: on (0x00)\n")
        self.assertEqual(self.published(), "on")

    def test_power_report_does_not_start_a_poll(self):
        self.feed("Received from TV to Playback Device 1 (0 to 4): REPORT_POWER_STATUS (0x90):\n"
                  "\tpwr-state: on (0x00)\n")
        self.assertFalse(self.tv.poll_now.is_set())
        self.feed("Received from TV to all (0 to 15): REPORT_PHYSICAL_ADDR (0x84):\n"
                  "\tphys-addr: 0.0.0.0\n\tprim-devtype: tv (0x00)\n")
        self.assertTrue(self.tv.poll_now.is_set())

    def test_other_senders_power_is_ignored(self):
        self.feed("Received from TV to Playback Device 1 (0 to 4): REPORT_POWER_STATUS (0x90):\n"
                  "\tpwr-state: on (0x00)\n")
        self.feed("Received from Audio System to Playback Device 1 (5 to 4): REPORT_POWER_STATUS (0x90):\n"
                  "\tpwr-state: standby (0x01)\n")
        self.assertEqual(self.published(), "on")
        # A header of another kind in between also ends the TV's message.
        self.feed("Received from TV to Playback Device 1 (0 to 4): REPORT_POWER_STATUS (0x90):\n"
                  "Transmit from Playback Device 1 to Audio System (4 to 5):\n"
                  "\tpwr-state: standby (0x01)\n")
        self.assertEqual(self.published(), "on")

    def test_poll_older_than_bus_is_dropped(self):
        tv = self.tv
        def slow_cec(*args, **kw):        # the TV says "on", then sends <Standby> before we publish
            tv.see("Received from TV to all (0 to 15): STANDBY (0x36)\n")
            return REPLY_ON
        tv.cec = slow_cec
        tv.poll()
        self.assertEqual(self.published(), "standby")
        tv.cec = lambda *a, **k: REPLY_ON  # a later poll with nothing in between does count
        tv.poll()
        self.assertEqual(self.published(), "on")

    def test_silent_tv_slows_polling_until_it_talks(self):
        tv = self.tv
        tv.cec = lambda *a, **k: REPLY_NACK
        for _ in range(cec.QUIET_AFTER - 1):
            tv.poll()
        self.assertEqual(self.published(), "unknown")
        self.assertEqual(tv.interval(), cec.POLL_S)
        tv.poll()
        self.assertEqual(tv.interval(), cec.QUIET_POLL_S)
        cec.AUTO = False                   # CEC=1: the normal pace regardless
        self.assertEqual(tv.interval(), cec.POLL_S)
        cec.AUTO = True
        # The TV turns up on the bus: a fresh look at once, and the normal pace after.
        self.feed("Received from TV to Playback Device 1 (0 to 4): REPORT_POWER_STATUS (0x90):\n"
                  "\tpwr-state: standby (0x01)\n")
        self.assertTrue(tv.poll_now.is_set())
        self.assertEqual(tv.interval(), cec.POLL_S)
        self.assertEqual(self.published(), "standby")

    def test_any_tv_message_ends_the_quiet_pace(self):
        tv = self.tv
        tv.cec = lambda *a, **k: REPLY_NACK
        for _ in range(cec.QUIET_AFTER):
            tv.poll()
        self.assertEqual(tv.interval(), cec.QUIET_POLL_S)
        # Not a power report: the TV is starting up and announces itself.
        self.feed("Received from TV to all (0 to 15): REPORT_PHYSICAL_ADDR (0x84):\n"
                  "\tphys-addr: 0.0.0.0\n\tprim-devtype: tv (0x00)\n")
        self.assertTrue(tv.poll_now.is_set())
        tv.poll_now.clear()
        tv.poll()                          # the immediate query goes unanswered while it starts
        self.assertEqual(tv.interval(), cec.POLL_S)

    def test_tv_chatter_does_not_hold_off_unknown(self):
        tv = self.tv
        self.feed("Received from TV to Playback Device 1 (0 to 4): REPORT_POWER_STATUS (0x90):\n"
                  "\tpwr-state: on (0x00)\n")
        self.assertEqual(self.published(), "on")
        tv.cec = lambda *a, **k: REPLY_NACK
        # The TV talks before every query but never answers one: its power is not known.
        for i in range(cec.UNKNOWN_AFTER):
            self.feed("Received from TV to all (0 to 15): REPORT_PHYSICAL_ADDR (0x84):\n"
                      "\tphys-addr: 0.0.0.0\n\tprim-devtype: tv (0x00)\n")
            tv.poll()
            if i < cec.UNKNOWN_AFTER - 1:
                self.assertEqual(self.published(), "on")
        self.assertEqual(self.published(), "unknown")
        self.assertEqual(tv.interval(), cec.POLL_S)   # it talks, so the normal pace stays
        # An answer again resets both.
        tv.cec = lambda *a, **k: REPLY_STANDBY
        tv.poll()
        self.assertEqual(self.published(), "standby")
        self.assertEqual((tv.misses, tv.quiet), (0, 0))


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
