import hashlib
import http.server
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import fetch_asset  # noqa: E402

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>'
OTHER = "localhost"  # same loopback, different hostname


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        port = self.server.server_address[1]
        if self.path == "/logo.svg":
            self._send(200, SVG, "image/svg+xml")
        elif self.path == "/page":
            self._send(200, b"<!DOCTYPE html><html><body>nope</body></html>", "text/html")
        elif self.path == "/big":
            self._send(200, SVG + b" " * 2000, "image/svg+xml")
        elif self.path == "/hop":
            self._redirect("/logo.svg")
        elif self.path == "/away":
            self._redirect(f"http://{OTHER}:{port}/logo.svg")
        elif self.path == "/chain":
            self._redirect("/away")
        else:
            self._send(404, b"missing", "text/plain")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, loc):
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        self.end_headers()


class FetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = Path(self.tmp.name) / "dl"

    def url(self, path, host="127.0.0.1"):
        return f"http://{host}:{self.port}{path}"

    def test_fetches_official_file_byte_for_byte(self):
        p = fetch_asset.fetch(self.url("/logo.svg"), self.dest, ["127.0.0.1"])
        self.assertEqual(p.read_bytes(), SVG)
        self.assertEqual(p.suffix, ".svg")

    def test_follows_same_host_redirect(self):
        p = fetch_asset.fetch(self.url("/hop"), self.dest, ["127.0.0.1"])
        self.assertEqual(p.read_bytes(), SVG)

    def test_refuses_nonofficial_host(self):
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.fetch(self.url("/logo.svg"), self.dest, ["example.org"])
        self.assertFalse(self.dest.exists() and any(self.dest.iterdir()))

    def test_refuses_banned_host_even_if_listed(self):
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.fetch("https://upload.wikimedia.org/x.svg", self.dest, ["wikimedia.org"])

    def test_refuses_redirect_to_other_host(self):
        for path in ("/away", "/chain"):
            with self.assertRaises(fetch_asset.FetchRefused, msg=path):
                fetch_asset.fetch(self.url(path), self.dest, ["127.0.0.1"])

    def test_refuses_html_body_with_200(self):
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.fetch(self.url("/page"), self.dest, ["127.0.0.1"])
        self.assertEqual(list(self.dest.iterdir()) if self.dest.exists() else [], [])

    def test_refuses_http_error(self):
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.fetch(self.url("/nothing"), self.dest, ["127.0.0.1"])

    def test_refuses_body_over_25_mb(self):
        self.assertEqual(fetch_asset.MAX_BYTES, 25 * 1024 * 1024)
        old = fetch_asset.MAX_BYTES
        fetch_asset.MAX_BYTES = 1000
        self.addCleanup(setattr, fetch_asset, "MAX_BYTES", old)
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.fetch(self.url("/big"), self.dest, ["127.0.0.1"])
        self.assertEqual(list(self.dest.iterdir()) if self.dest.exists() else [], [])

    def test_refuses_nonempty_dest(self):
        self.dest.mkdir()
        (self.dest / "x").write_bytes(b"1")
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.fetch(self.url("/logo.svg"), self.dest, ["127.0.0.1"])

    def test_refuses_non_http_scheme(self):
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.fetch("file:///etc/passwd", self.dest, ["127.0.0.1"])


class ZipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make_zip(self, members):
        zp = self.root / "a.zip"
        with zipfile.ZipFile(zp, "w") as z:
            for name, data in members:
                z.writestr(name, data)
        return zp

    def test_extracts_safe_members(self):
        zp = self.make_zip([("a/logo.svg", SVG)])
        out = fetch_asset.safe_extract_zip(zp, self.root / "out")
        self.assertEqual([p.read_bytes() for p in out], [SVG])

    def test_zip_slip_member_refused(self):
        zp = self.make_zip([("ok.svg", SVG), ("../evil.svg", SVG)])
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.safe_extract_zip(zp, self.root / "out")
        self.assertFalse((self.root / "evil.svg").exists())
        self.assertFalse((self.root / "out" / "ok.svg").exists())

    def test_absolute_member_refused(self):
        zp = self.make_zip([("/abs.svg", SVG)])
        with self.assertRaises(fetch_asset.FetchRefused):
            fetch_asset.safe_extract_zip(zp, self.root / "out")


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "x.svg"

    def rec(self, **kw):
        return fetch_asset.make_asset_record(
            self.path, "https://e.org/x.svg", "https://e.org/brand", kw.get("tier", 1),
            "logo", "light", "color")

    def test_record_has_sha256_and_today(self):
        import datetime
        self.path.write_bytes(SVG)
        r = self.rec()
        self.assertEqual(r["sha256"], hashlib.sha256(SVG).hexdigest())
        self.assertEqual(r["retrieved"], datetime.date.today().isoformat())
        self.assertEqual(r["file"], "x.svg")
        self.assertEqual(r["source_tier"], 1)
        self.assertEqual(r["source_url"], "https://e.org/x.svg")
        self.assertEqual(r["page_url"], "https://e.org/brand")

    def test_record_transparent_is_computed(self):
        self.path.write_bytes(SVG)
        self.assertTrue(self.rec()["transparent"])
        self.path.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">'
                              b'<rect width="1" height="1" fill="#fff"/></svg>')
        self.assertFalse(self.rec()["transparent"])

    def test_record_rejects_bad_tier(self):
        self.path.write_bytes(SVG)
        for bad in (3, "x", True):
            with self.assertRaises(ValueError):
                self.rec(tier=bad)
        self.assertEqual(self.rec(tier="internal")["source_tier"], "internal")


if __name__ == "__main__":
    unittest.main()
