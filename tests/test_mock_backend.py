import unittest

from dp4500.reader import UareU4500
from dp4500.backends.mock import MockBackend
from dp4500.backends.base import LEDMode


class TestMockBackend(unittest.TestCase):
    def setUp(self):
        self.backend = MockBackend(simulate_latency=False)

    def test_list_devices(self):
        devs = self.backend.list_devices()
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0].vendor_id, 0x05BA)
        self.assertEqual(devs[0].product_id, 0x000A)

    def test_capture(self):
        with UareU4500(backend=self.backend) as reader:
            self.assertTrue(reader.is_open)
            img = reader.capture(wait_for_finger=True)
            self.assertEqual(img.width, 290)
            self.assertEqual(img.height, 384)
            self.assertEqual(img.dpi, 500)
        self.assertFalse(reader.is_open)

    def test_enrollment_progress(self):
        progress_events = []

        def on_progress(completed, total):
            progress_events.append((completed, total))

        with UareU4500(backend=self.backend) as reader:
            tpl = reader.enroll(
                stages=4,
                on_stage_progress=on_progress,
                username="alice",
                finger_name="right_index",
            )
            self.assertEqual(tpl.username, "alice")
            self.assertEqual(tpl.finger_name, "right_index")
            self.assertEqual(len(progress_events), 4)
            self.assertEqual(progress_events[-1], (4, 4))

    def test_verify_success_and_failure(self):
        with UareU4500(backend=self.backend) as reader:
            # Enrolled with default seed 42
            tpl = reader.enroll(stages=2, username="alice")
            res_match = reader.verify(tpl)
            self.assertTrue(res_match.matched)
            self.assertGreaterEqual(res_match.score, 0.8)

            # Change simulated finger seed on the handle
            reader._handle.simulated_finger_seed = 9999
            res_nomatch = reader.verify(tpl)
            self.assertFalse(res_nomatch.matched)

    def test_identify(self):
        with UareU4500(backend=self.backend) as reader:
            reader._handle.simulated_finger_seed = 100
            tpl1 = reader.enroll(stages=1, username="user_100")

            reader._handle.simulated_finger_seed = 200
            tpl2 = reader.enroll(stages=1, username="user_200")

            reader._handle.simulated_finger_seed = 300
            tpl3 = reader.enroll(stages=1, username="user_300")

            # Test identifying user_200
            reader._handle.simulated_finger_seed = 200
            id_res = reader.identify([tpl1, tpl2, tpl3])
            self.assertTrue(id_res.matched)
            self.assertEqual(id_res.index, 1)
            self.assertEqual(id_res.template.username, "user_200")

    def test_led_control(self):
        with UareU4500(backend=self.backend) as reader:
            self.assertTrue(reader.set_led(LEDMode.ON))
            self.assertTrue(reader.set_led(LEDMode.OFF))


if __name__ == "__main__":
    unittest.main()
