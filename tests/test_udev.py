import unittest

from dp4500.utils.udev import check_usb_permissions, get_udev_rule_content


class TestUdevUtils(unittest.TestCase):
    def test_udev_rule_content(self):
        content = get_udev_rule_content()
        self.assertIn("05ba", content.lower())
        self.assertIn("000a", content.lower())
        self.assertIn("MODE=\"0666\"", content)

    def test_check_usb_permissions_returns_dict(self):
        report = check_usb_permissions()
        self.assertIsInstance(report, dict)
        self.assertIn("is_linux", report)
        self.assertIn("device_found", report)
        self.assertIn("can_read", report)
        self.assertIn("can_write", report)
        self.assertIn("advice", report)


if __name__ == "__main__":
    unittest.main()
