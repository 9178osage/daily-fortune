import hashlib
import subprocess
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.build_release import build_release
from scripts.download_release import download_release
from scripts.verify_release import verify_release


class ReleaseTests(unittest.TestCase):
    def test_build_release_has_checksum_and_version_guard(self):
        with tempfile.TemporaryDirectory(prefix="fortune-release-") as directory:
            root = Path(directory)
            source = root / "source"
            (source / "daily_fortune").mkdir(parents=True)
            (source / "daily_fortune/__init__.py").write_text(
                '__version__ = "1.6.1"\n', encoding="utf-8"
            )
            (source / "main.py").write_text("tagged source\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            subprocess.run(
                ["git", "-C", str(source), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(source), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(source), "commit", "-qm", "tagged source"], check=True
            )
            subprocess.run(["git", "-C", str(source), "tag", "v1.6.1"], check=True)
            (source / "main.py").write_text("dirty worktree\n", encoding="utf-8")

            tag = "v1.6.1"
            dist = root / "dist"
            archive, checksum_file = build_release(tag, dist, source)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(archive.name, "daily-fortune-v1.6.1.zip")
            self.assertEqual(checksum_file.read_text(encoding="ascii"),
                             f"{digest}  {archive.name}\n")
            self.assertEqual(verify_release(archive, checksum_file), digest)
            with zipfile.ZipFile(archive) as package:
                names = package.namelist()
                self.assertIn("daily-fortune-v1.6.1/main.py", names)
                self.assertEqual(
                    package.read("daily-fortune-v1.6.1/main.py"), b"tagged source\n"
                )
                self.assertIn("daily-fortune-v1.6.1/daily_fortune/__init__.py", names)
            with self.assertRaisesRegex(ValueError, "版本标签"):
                build_release("not-a-version", dist, source)
            with self.assertRaisesRegex(ValueError, "未找到 Git 标签"):
                build_release("v0.0.0", dist, source)

    def test_download_release_resumes_and_verifies(self):
        payload = b"daily-fortune-resume-test-" * 128

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start = 0
                range_header = self.headers.get("Range")
                if range_header:
                    start = int(range_header.removeprefix("bytes=").split("-", 1)[0])
                    self.send_response(206)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Range",
                                     f"bytes {start}-{len(payload) - 1}/{len(payload)}")
                else:
                    self.send_response(200)
                body = payload[start:]
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix="fortune-download-") as directory:
                output = Path(directory) / "release.zip"
                part = output.with_name(output.name + ".part")
                part.write_bytes(payload[:32])
                sha256 = hashlib.sha256(payload).hexdigest()
                url = f"http://127.0.0.1:{server.server_port}/release.zip"
                downloaded = download_release(url, output, sha256)
                self.assertEqual(downloaded.read_bytes(), payload)
                self.assertFalse(part.exists())

                output.write_bytes(b"known-good-release")
                part.write_bytes(b"corrupt-resume-data")
                with self.assertRaisesRegex(ValueError, "校验失败"):
                    download_release(url, output, "0" * 64)
                self.assertEqual(output.read_bytes(), b"known-good-release")
                self.assertTrue(part.read_bytes().startswith(b"corrupt-resume-data"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
