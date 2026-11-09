# -*- coding: utf-8 -*-
import hashlib
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

os.environ["IOSPR_LANG"] = "ru"   # тесты проверяют русский текст
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import updater  # noqa: E402


class TestVersions(unittest.TestCase):
    def test_compare(self):
        self.assertTrue(updater.is_newer("v0.4.0", "0.3.1"))
        self.assertTrue(updater.is_newer("0.10.0", "0.9.9"))
        self.assertFalse(updater.is_newer("0.3.1", "0.3.1"))
        self.assertFalse(updater.is_newer("0.3.0", "0.3.1"))

    def test_current_version_matches_file(self):
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
            self.assertEqual(updater.current_version(), f.read().strip())


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.src = os.path.join(self.dir, "src.bin")
        self.data = os.urandom(300_000)
        with open(self.src, "wb") as f:
            f.write(self.data)
        self.url = pathlib.Path(self.src).as_uri()

    def test_ok_with_digest(self):
        dest = os.path.join(self.dir, "out.bin")
        asset = {"url": self.url, "size": len(self.data),
                 "digest": "sha256:" + hashlib.sha256(self.data).hexdigest()}
        updater.download(asset, dest)
        with open(dest, "rb") as f:
            self.assertEqual(f.read(), self.data)

    def test_cancel_leaves_nothing(self):
        import threading
        dest = os.path.join(self.dir, "cancel.bin")
        ev = threading.Event()
        ev.set()
        with self.assertRaises(updater.Cancelled):
            updater.download({"url": self.url, "size": len(self.data)}, dest, cancel=ev)
        self.assertFalse(os.path.exists(dest))
        self.assertFalse(os.path.exists(dest + ".part"))

    def test_bad_digest_leaves_nothing(self):
        dest = os.path.join(self.dir, "bad.bin")
        asset = {"url": self.url, "size": len(self.data), "digest": "sha256:" + "0" * 64}
        with self.assertRaises(IOError):
            updater.download(asset, dest)
        self.assertFalse(os.path.exists(dest))
        self.assertFalse(os.path.exists(dest + ".part"))


class TestInstallScripts(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "скрипт для Mac запускается через bash")
    def test_mac_script_swaps_app_and_keeps_data(self):
        d = tempfile.mkdtemp()
        data = os.path.join(d, "Documents", "iOSPanicReader")
        os.makedirs(data)
        with open(os.path.join(data, "history.json"), "w") as f:
            f.write('{"phones": {"X": {}}}')
        app = os.path.join(d, "Apps", "iOSPanicReader.app")
        new = os.path.join(d, "new", "iOSPanicReader.app")
        for p, ver in ((app, "old"), (new, "new")):
            os.makedirs(os.path.join(p, "Contents", "MacOS"))
            with open(os.path.join(p, "Contents", "MacOS", "VERSION"), "w") as f:
                f.write(ver)
        with open(os.path.join(app, "Contents", "MacOS", "user_kb.json"), "w") as f:
            f.write("[]")
        backup = os.path.join(data, "previous", "iOSPanicReader.app")
        script = os.path.join(d, "u.sh")
        with open(script, "w", encoding="utf-8") as f:
            f.write(updater.mac_script(999999, app, new, backup, data, relaunch=False))
        subprocess.run(["/bin/bash", script], check=True, timeout=20)
        with open(os.path.join(app, "Contents", "MacOS", "VERSION")) as f:
            self.assertEqual(f.read(), "new")
        with open(os.path.join(backup, "Contents", "MacOS", "VERSION")) as f:
            self.assertEqual(f.read(), "old")
        self.assertTrue(os.path.isfile(os.path.join(data, "user_kb.json")))
        with open(os.path.join(data, "history.json")) as f:
            self.assertIn("X", f.read())
        self.assertFalse(os.path.exists(script))

    def test_windows_script_quotes_paths(self):
        s = updater.windows_script([1, 2], r"C:\Users\Иван O'Neil\iOSPanicReader.exe", r"C:\x\new.exe",
                                   r"C:\b\old.exe", True, r"C:\d\update.log")
        self.assertIn("Wait-Process -Id 2", s)
        self.assertIn("'C:\\Users\\Иван O''Neil\\iOSPanicReader.exe'", s)
        self.assertIn("if ($true)", s)

    def test_backup_user_data(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "history.json"), "w") as f:
            f.write("{}")
        updater.backup_user_data(d, "0.3.1")
        self.assertEqual(len(os.listdir(os.path.join(d, "backups"))), 1)


if __name__ == "__main__":
    unittest.main()
