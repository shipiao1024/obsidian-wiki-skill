from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import install_video_cookies  # noqa: E402


class InstallVideoCookiesTests(unittest.TestCase):
    def test_install_cookie_file_copies_netscape_cookie_file(self) -> None:
        source = ROOT / ".tmp-tests" / "cookie-install-source.txt"
        destination = ROOT / ".tmp-tests" / "cookie-install-dest.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tname\tvalue\n", encoding="utf-8")
        self.addCleanup(lambda: source.unlink(missing_ok=True))
        self.addCleanup(lambda: destination.unlink(missing_ok=True))

        result = install_video_cookies.install_cookie_file(source, destination=destination)

        self.assertEqual(result, destination.resolve())
        self.assertEqual(destination.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))

    def test_install_cookie_text_rejects_non_netscape_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "Netscape"):
            install_video_cookies.install_cookie_text("not cookie text", destination=ROOT / ".tmp-tests" / "bad-cookie.txt")


if __name__ == "__main__":
    unittest.main()
