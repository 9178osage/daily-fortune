import hashlib
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts.build_release import build_release, read_version
from scripts.download_release import download_release
from scripts.verify_release import verify_release


class ReleaseTests(unittest.TestCase):
    def test_build_release_has_checksum_and_version_guard(self):
        with tempfile.TemporaryDirectory(prefix="fortune-release-") as directory:
            dist = Path(directory)
            tag = f"v{read_version()}"
            archive, checksum_file = build_release(tag, dist)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(checksum_file.read_text(encoding="ascii"),
                             f"{digest}  {archive.name}\n")
            self.assertEqual(verify_release(archive, checksum_file), digest)
            with zipfile.ZipFile(archive) as package:
                names = package.namelist()
                self.assertIn("daily-fortune-{}/main.py".format(read_version()), names)
                self.assertIn("daily-fortune-{}/daily_fortune/engine.py".format(read_version()), names)
            with self.assertRaisesRegex(ValueError, "标签版本"):
                build_release("v0.0.0", dist)

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
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
