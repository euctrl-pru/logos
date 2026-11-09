import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import validate  # noqa: E402

SVG_OK = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>'


def make_png(pixels, color_type=6, extra_chunks=()):
    """pixels: list of rows, each a list of tuples. Filter 0 on every row."""
    h, w = len(pixels), len(pixels[0])
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in pixels)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    for t, d in extra_chunks:
        out += chunk(t, d)
    return out + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def make_webp(kind, alpha=False):
    """Minimal RIFF/WEBP bodies with just enough header for format and alpha sniffing."""
    def chunk(t, d):
        return t + struct.pack("<I", len(d)) + d + (b"\x00" if len(d) % 2 else b"")

    if kind == "vp8x":
        body = chunk(b"VP8X", bytes([0x10 if alpha else 0]) + b"\x00\x00\x00" + b"\x00\x00\x00" + b"\x00\x00\x00")
    elif kind == "vp8l":
        bits = (1 << 28) if alpha else 0  # alpha_is_used bit follows 14+14 size bits
        body = chunk(b"VP8L", b"\x2f" + struct.pack("<I", bits))
    else:
        body = chunk(b"VP8 ", b"\x00" * 10)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def make_entity(self, id="xx-test", files=None, assets=None, group="european", **over):
        d = self.root / "stakeholders" / group / id
        (d / "logos").mkdir(parents=True)
        (d / "house-style").mkdir()
        files = files if files is not None else {}
        for name, data in files.items():
            (d / "logos" / name).write_bytes(data)
        ent = {
            "id": id, "name": "Test", "acronym": "TST", "group": group,
            "country": None, "iso2": None, "also_countries": [], "membership": None,
            "types": ["institution"], "official_domains": ["example.org"],
            "terms_url": None, "aliases": [], "notes": "", "status": "partial",
            "gaps": [{"need": "dark", "reason": "none published"}],
            "assets": assets if assets is not None else [],
            "contact": {"logo_permission_url": None, "email": None, "notes": None},
        }
        ent.update(over)
        (d / "entity.json").write_text(json.dumps(ent))
        self.write_style(d)
        return d

    def asset(self, id, data, name=None, **over):
        name = name or f"{id}-logo-light.svg"
        a = {
            "file": name, "lockup": "logo", "background": "light", "color_mode": "color",
            "transparent": True, "source_url": "https://www.example.org/logo.svg",
            "page_url": "https://www.example.org/brand", "source_tier": 1,
            "retrieved": "2026-11-08", "sha256": sha(data),
        }
        a.update(over)
        return a

    def entity_with_svg(self, data=SVG_OK, name=None, id="xx-test", **asset_over):
        name = name or f"{id}-logo-light.svg"
        return self.make_entity(id, {name: data}, [self.asset(id, data, name, **asset_over)])

    def write_style(self, d, **over):
        st = {
            "id": d.name, "status": "documented",
            "current_sources": [{"url": "https://example.org/g", "kind": "guideline",
                                 "version_label": "2024", "sha256": None, "retrieved": "2026-11-08"}],
            "previous_sources": [], "last_checked": "2026-11-08",
            "colors": [{"name": "Blue", "hex": "#0055AA", "rgb": None, "cmyk": None, "role": "primary",
                        "evidence": "guideline", "source_url": "https://example.org/g"}],
            "typography": [], "logo_usage": {}, "retrieved": "2026-11-08", "notes": "",
        }
        st.update(over)
        (d / "house-style" / "style.json").write_text(json.dumps(st))

    def errors(self, d, **kw):
        return validate.validate_entity(d, **kw)

    def assertError(self, errs, text):
        self.assertTrue(any(text in e for e in errs), f"{text!r} not in {errs}")


class SniffAndSvg(Base):
    def test_html_named_svg_rejected(self):
        d = self.entity_with_svg(b"<!doctype html><html><body>x</body></html>")
        self.assertError(self.errors(d), "format")

    def test_jpeg_named_png_rejected(self):
        data = b"\xff\xd8\xff\xe0" + b"0" * 20
        d = self.make_entity(files={"xx-test-logo-light.png": data},
                             assets=[self.asset("xx-test", data, "xx-test-logo-light.png", transparent=False)])
        self.assertError(self.errors(d), "format")

    def test_sniff_formats(self):
        self.assertEqual(validate.sniff_format(make_png([[(0, 0, 0, 255)]])), "png")
        self.assertEqual(validate.sniff_format(b"%PDF-1.4"), "pdf")
        self.assertEqual(validate.sniff_format(b"%!PS-Adobe-3.0 EPSF-3.0"), "eps")
        self.assertEqual(validate.sniff_format(b'<?xml version="1.0"?>\n' + SVG_OK), "svg")
        self.assertIsNone(validate.sniff_format(b"hello"))
        self.assertEqual(validate.sniff_format(make_webp("vp8")), "webp")

    def _webp(self, kind, alpha):
        p = self.root / "t.webp"
        p.write_bytes(make_webp(kind, alpha))
        return p

    def test_webp_vp8x_alpha_flag_is_transparent(self):
        self.assertTrue(validate.is_transparent(self._webp("vp8x", True)))
        self.assertFalse(validate.is_transparent(self._webp("vp8x", False)))

    def test_webp_vp8l_alpha_hint_is_transparent(self):
        self.assertTrue(validate.is_transparent(self._webp("vp8l", True)))
        self.assertFalse(validate.is_transparent(self._webp("vp8l", False)))

    def test_webp_lossy_vp8_not_transparent(self):
        self.assertFalse(validate.is_transparent(self._webp("vp8", False)))

    def _gif(self, transparent=None, truncate=None):
        # 1x1 GIF89a, 2-colour global table; transparent: None = no GCE
        data = b"GIF89a" + struct.pack("<HHBBB", 1, 1, 0x80, 0, 0) + b"\x00\x00\x00\xff\xff\xff"
        if transparent is not None:
            data += b"\x21\xf9\x04" + bytes([1 if transparent else 0]) + b"\x00\x00\x00\x00\x00"
        data += b"\x2c" + struct.pack("<HHHHB", 0, 0, 1, 1, 0) + b"\x02\x02\x44\x01\x00\x3b"
        if truncate is not None:
            data = data[:truncate]
        p = self.root / "t.gif"
        p.write_bytes(data)
        return p

    def test_sniff_gif(self):
        self.assertEqual(validate.sniff_format(b"GIF89a" + b"\x00" * 10), "gif")
        self.assertEqual(validate.sniff_format(b"GIF87a" + b"\x00" * 10), "gif")

    def test_gif_extension_allowed(self):
        self.assertEqual(validate.EXTENSIONS.get("gif"), "gif")

    def test_gif_transparency_flag_is_transparent(self):
        self.assertTrue(validate.is_transparent(self._gif(True)))

    def test_gif_without_transparency_flag_is_opaque(self):
        self.assertFalse(validate.is_transparent(self._gif(False)))
        self.assertFalse(validate.is_transparent(self._gif(None)))

    def test_gif_truncated_is_safe(self):
        full = len(self._gif(True).read_bytes())
        for n in range(0, full):
            validate.is_transparent(self._gif(True, truncate=n))
        self.assertFalse(validate.is_transparent(self._gif(True, truncate=8)))

    def _gif_entity_errors(self, transparent_flag, recorded):
        data = self._gif(transparent_flag).read_bytes()
        d = self.make_entity(files={"xx-test-logo-light.gif": data},
                             assets=[self.asset("xx-test", data, "xx-test-logo-light.gif", transparent=recorded)])
        return self.errors(d)

    def test_gif_flag_set_recorded_false_passes(self):
        self.assertFalse([e for e in self._gif_entity_errors(True, False) if "transparent" in e])

    def test_gif_flag_set_recorded_true_passes(self):
        self.assertFalse([e for e in self._gif_entity_errors(True, True) if "transparent" in e])

    def test_gif_no_flag_recorded_true_fails(self):
        self.assertError(self._gif_entity_errors(False, True), "transparent field does not match file")

    def test_gif_without_gce_recorded_true_fails(self):
        self.assertError(self._gif_entity_errors(None, True), "transparent field does not match file")

    def test_webp_extension_allowed(self):
        self.assertEqual(validate.EXTENSIONS.get("webp"), "webp")

    def test_svg_with_script_rejected(self):
        bads = (b"<script>alert(1)</script>", b'<rect onclick="x()"/>',
                b'<image href="https://evil.example/a.png"/>',
                b'<image href="data:image/svg+xml;base64,PHN2Zy8+"/>',
                b'<image xlink:href="data:text/html;base64,PGI+"/>',
                b'<image href="data:image/png,notbase64"/>')
        for i, bad in enumerate(bads):
            data = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">' + bad + b"</svg>"
            with self.subTest(bad=bad):
                d = self.entity_with_svg(data, id=f"xx-bad{i}")
                self.assertError(self.errors(d), "unsafe svg")

    def test_svg_embedded_raster_data_uri_allowed(self):
        for i, mime in enumerate(("png", "jpeg", "webp", "gif")):
            data = (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                    b'viewBox="0 0 1 1"><image xlink:href="data:image/' + mime.encode()
                    + b';base64,AAAA"/><use href="#a"/></svg>')
            with self.subTest(mime=mime):
                d = self.entity_with_svg(data, id=f"xx-ok{i}")
                self.assertFalse([e for e in self.errors(d) if "unsafe svg" in e])

    def _svg(self, body):
        p = self.root / "t.svg"
        p.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">' + body + b"</svg>")
        return p

    def test_svg_fullbleed_rect_not_transparent(self):
        p = self._svg(b'<rect width="100" height="50" fill="#fff"/><circle r="3"/>')
        self.assertFalse(validate.is_transparent(p))

    def test_svg_fullbleed_rect_fill_none_is_transparent(self):
        p = self._svg(b'<rect width="100" height="50" fill="none"/><circle r="3"/>')
        self.assertTrue(validate.is_transparent(p))

    def test_svg_fullbleed_rect_in_non_rendered_container_transparent(self):
        for wrap in ("defs", "clipPath", "mask", "pattern"):
            with self.subTest(wrap=wrap):
                body = f'<{wrap} id="c"><rect width="100" height="50"/></{wrap}><circle r="3"/>'.encode()
                self.assertTrue(validate.is_transparent(self._svg(body)))

    def test_svg_fullbleed_invisible_rect_transparent(self):
        for attrs in ('fill="transparent"', 'opacity="0"', 'fill-opacity="0"', 'style="fill-opacity:0"'):
            with self.subTest(attrs=attrs):
                body = f'<rect width="100" height="50" {attrs}/><circle r="3"/>'.encode()
                self.assertTrue(validate.is_transparent(self._svg(body)))

    def test_svg_unpainted_rect_then_opaque_fullbleed_rect_not_transparent(self):
        for attrs in ('fill="none"', 'fill="transparent"', 'opacity="0"', 'fill-opacity="0"'):
            with self.subTest(attrs=attrs):
                body = f'<rect width="100" height="50" {attrs}/><rect width="100" height="50" fill="#fff"/>'.encode()
                self.assertFalse(validate.is_transparent(self._svg(body)))

    def test_svg_unpainted_rect_then_small_shape_transparent(self):
        body = b'<rect width="100" height="50" fill="none"/><circle r="3"/>'
        self.assertTrue(validate.is_transparent(self._svg(body)))

    RECT = b'<rect class="a" width="100" height="50"'

    def test_svg_css_class_fill_none_is_unpainted(self):
        body = b"<style>.a{fill:none;}</style>" + self.RECT + b'/><circle r="3"/>'
        self.assertTrue(validate.is_transparent(self._svg(body)))

    def test_svg_css_class_opaque_fill_not_transparent(self):
        body = b"<defs><style>.a{fill:#fff}</style></defs>" + self.RECT + b'/><circle r="3"/>'
        self.assertFalse(validate.is_transparent(self._svg(body)))

    def test_svg_css_inline_overrides_class(self):
        for attrs, css, expected in ((b'fill="#fff"', b".a{fill:none}", False),
                                     (b'style="fill:#fff"', b".a{fill:none}", False),
                                     (b'fill="none"', b".a{fill:#fff}", True),
                                     (b'style="fill:none"', b".a{fill:#fff}", True)):
            with self.subTest(attrs=attrs):
                body = b"<style>" + css + b"</style>" + self.RECT + b" " + attrs + b'/><circle r="3"/>'
                self.assertEqual(validate.is_transparent(self._svg(body)), expected)

    def test_svg_css_opacity_stroke_and_selector_forms(self):
        cases = ((b".a{fill-opacity:0}", True), (b".a{opacity:0}", True),
                 (b".a{fill:none;stroke:#000}", False), (b".z, .a{fill:none}", True),
                 (b"rect{fill:none}", True), (b"*{fill:none}", True),
                 (b"/* .a{fill:#fff} */ .a{fill:none}", True),
                 (b"rect{fill:#fff} .a{fill:none}", True), (b".a{fill:none} rect{fill:#fff}", True),
                 (b".a{fill:#fff} .a{fill:none}", True))
        for css, expected in cases:
            with self.subTest(css=css):
                body = b"<style>" + css + b"</style>" + self.RECT + b'/><circle r="3"/>'
                self.assertEqual(validate.is_transparent(self._svg(body)), expected)

    def test_svg_without_background_transparent(self):
        p = self._svg(b'<rect width="10" height="10"/><circle r="3"/>')
        self.assertTrue(validate.is_transparent(p))


class PngTransparency(Base):
    def test_rgba_png_all_opaque_not_transparent(self):
        p = self.root / "a.png"
        p.write_bytes(make_png([[(1, 2, 3, 255), (4, 5, 6, 255)]] * 2))
        self.assertFalse(validate.is_transparent(p))

    def test_rgba_png_with_clear_pixel_transparent(self):
        p = self.root / "a.png"
        p.write_bytes(make_png([[(1, 2, 3, 255), (4, 5, 6, 0)], [(1, 2, 3, 255)] * 2]))
        self.assertTrue(validate.is_transparent(p))

    def test_palette_png_without_trns_not_transparent(self):
        p = self.root / "a.png"
        plte = (b"PLTE", b"\x00\x00\x00\xff\xff\xff")
        raw = make_png([[(0,), (1,)]], color_type=3, extra_chunks=[plte])
        p.write_bytes(raw)
        self.assertFalse(validate.is_transparent(p))

    def test_palette_png_with_trns_transparent(self):
        p = self.root / "a.png"
        extra = [(b"PLTE", b"\x00\x00\x00\xff\xff\xff"), (b"tRNS", b"\x00")]
        p.write_bytes(make_png([[(0,), (1,)]], color_type=3, extra_chunks=extra))
        self.assertTrue(validate.is_transparent(p))


class Hosts(Base):
    def test_lookalike_host_rejected(self):
        self.assertFalse(validate.host_is_official("https://eurocontrol.int.example.com/a.svg", ["eurocontrol.int"]))

    def test_subdomain_accepted(self):
        self.assertTrue(validate.host_is_official("https://www.ec.europa.eu/a.svg", ["europa.eu"]))

    def test_banned_host_rejected(self):
        d = self.entity_with_svg(source_url="https://upload.wikimedia.org/a.svg")
        ent = json.loads((d / "entity.json").read_text())
        ent["official_domains"] = ["wikimedia.org"]
        (d / "entity.json").write_text(json.dumps(ent))
        self.assertError(self.errors(d), "banned")

    def test_off_domain_rejected(self):
        d = self.entity_with_svg(source_url="https://cdn.other.net/a.svg")
        self.assertError(self.errors(d), "official")

    def test_internal_tier_skips_host_checks(self):
        d = self.entity_with_svg(source_url="repo-history", source_tier="internal", page_url=None)
        self.assertEqual(self.errors(d), [])


class EntityRules(Base):
    def test_valid_partial_entity_ok(self):
        self.assertEqual(self.errors(self.entity_with_svg()), [])

    def test_sha_mismatch_rejected(self):
        d = self.entity_with_svg(sha256="0" * 64)
        self.assertError(self.errors(d), "sha256")

    def test_transparent_flag_must_match(self):
        d = self.entity_with_svg(transparent=False)
        self.assertError(self.errors(d), "transparent")

    def test_complete_requires_three_variants(self):
        d = self.entity_with_svg()
        ent = json.loads((d / "entity.json").read_text())
        ent.update(status="complete", gaps=[])
        (d / "entity.json").write_text(json.dumps(ent))
        self.assertError(self.errors(d), "complete")

    def test_complete_with_all_variants_ok(self):
        files = {"xx-test-logo-light.svg": SVG_OK, "xx-test-logo-dark.svg": SVG_OK + b" "}
        assets = [self.asset("xx-test", SVG_OK), self.asset("xx-test", SVG_OK + b" ", "xx-test-logo-dark.svg", background="dark")]
        d = self.make_entity(files=files, assets=assets, status="complete", gaps=[])
        self.assertEqual(self.errors(d), [])

    def test_restricted_requires_gap(self):
        d = self.make_entity(status="restricted", gaps=[])
        self.assertTrue(self.errors(d))

    def test_restricted_with_assets_rejected(self):
        d = self.entity_with_svg()
        ent = json.loads((d / "entity.json").read_text())
        ent["status"] = "restricted"
        (d / "entity.json").write_text(json.dumps(ent))
        self.assertTrue(self.errors(d))

    def test_not_applicable_requires_notes(self):
        d = self.make_entity(status="not-applicable", gaps=[], notes="")
        self.assertError(self.errors(d), "notes")

    def test_unrecorded_logo_file_rejected(self):
        d = self.make_entity(files={"xx-test-logo-light.svg": SVG_OK})
        self.assertError(self.errors(d), "unrecorded")

    def test_filename_convention(self):
        d = self.entity_with_svg(name="Logo Final.svg")
        self.assertError(self.errors(d), "name")

    def test_pending_rejected_by_default(self):
        d = self.make_entity(status="pending", gaps=[])
        self.assertError(self.errors(d), "pending")
        self.assertEqual(self.errors(d, allow_pending=True), [])


class ExtrasRules(Base):
    def test_new_types_accepted(self):
        types = ["airline", "airport", "training", "association", "manufacturer", "mro",
                 "fuel", "travel-services", "ground-handling", "partner"]
        d = self.make_entity(types=types, status="not-found")
        self.assertEqual(self.errors(d), [])
        d = self.make_entity(id="xx-bad", types=["bogus"], status="not-found")
        self.assertError(self.errors(d), "types")

    def _previous(self, **over):
        files = {"previous/xx-test-logo-light.svg": SVG_OK}
        a = self.asset("xx-test", SVG_OK, "previous/xx-test-logo-light.svg", superseded=True)
        a.update(over)
        d = self.make_entity(files={}, assets=[a])
        (d / "logos" / "previous").mkdir()
        for n, data in files.items():
            (d / "logos" / n).write_bytes(data)
        return d

    def test_superseded_asset_must_be_in_previous_dir(self):
        d = self._previous()
        self.assertEqual(self.errors(d), [])
        self.root = Path(tempfile.mkdtemp(dir=self._tmp.name))
        d = self.entity_with_svg(id="xx-s", superseded=True)
        self.assertError(self.errors(d), "previous/")
        self.root = Path(tempfile.mkdtemp(dir=self._tmp.name))
        d = self._previous(superseded=False)
        self.assertError(self.errors(d), "previous/")

    def test_previous_name_convention_and_unrecorded(self):
        d = self.make_entity(id="xx-p", files={}, assets=[
            self.asset("xx-p", SVG_OK, "previous/Old Logo.svg", superseded=True)])
        (d / "logos" / "previous").mkdir()
        (d / "logos" / "previous" / "Old Logo.svg").write_bytes(SVG_OK)
        (d / "logos" / "previous" / "stray.svg").write_bytes(SVG_OK)
        errs = self.errors(d)
        self.assertError(errs, "bad file name")
        self.assertError(errs, "unrecorded logo file previous/stray.svg")

    def test_superseded_assets_do_not_satisfy_complete(self):
        d = self.entity_with_svg()
        data = SVG_OK + b" "
        (d / "logos" / "previous").mkdir()
        (d / "logos" / "previous" / "xx-test-logo-dark.svg").write_bytes(data)
        ent = json.loads((d / "entity.json").read_text())
        ent["assets"].append(self.asset("xx-test", data, "previous/xx-test-logo-dark.svg",
                                        background="dark", superseded=True))
        ent.update(status="complete", gaps=[])
        (d / "entity.json").write_text(json.dumps(ent))
        self.assertError(self.errors(d), "complete")

    def test_language_must_be_iso639(self):
        self.assertEqual(self.errors(self.entity_with_svg(language="fr")), [])
        for i, bad in enumerate(("FR", "fra", "f", 5)):
            with self.subTest(bad=bad):
                d = self.entity_with_svg(id=f"xx-l{i}", language=bad)
                self.assertError(self.errors(d), "language")

    def test_valid_until_must_be_date_or_null(self):
        self.assertEqual(self.errors(self.entity_with_svg(valid_until="2027-01-31")), [])
        d = self.entity_with_svg(id="xx-v", valid_until="soon")
        self.assertError(self.errors(d), "valid_until")

    def test_contact_required_keys(self):
        d = self.make_entity(status="not-found")
        ent = json.loads((d / "entity.json").read_text())
        del ent["contact"]
        (d / "entity.json").write_text(json.dumps(ent))
        self.assertError(self.errors(d), "contact")
        for i, bad in enumerate(({"email": None}, {"logo_permission_url": None, "email": None, "notes": None, "x": 1},
                                 {"logo_permission_url": 1, "email": None, "notes": None}, [])):
            with self.subTest(bad=bad):
                d = self.make_entity(id=f"xx-c{i}", contact=bad, status="not-found")
                self.assertError(self.errors(d), "contact")
        d = self.make_entity(id="xx-ok", status="not-found", contact={"logo_permission_url": "https://example.org/p",
                                                  "email": "a@example.org", "notes": "n"})
        self.assertEqual(self.errors(d), [])


class StyleRules(Base):
    def entity(self):
        return self.make_entity(status="not-found")

    def test_valid_style_ok(self):
        d = self.entity()
        self.write_style(d)
        self.assertEqual(self.errors(d), [])

    def test_observed_or_guideline_evidence_required(self):
        d = self.entity()
        self.write_style(d, colors=[{"name": "Blue", "hex": "#0055AA", "role": "primary", "source_url": None}])
        self.assertTrue(self.errors(d))

    def test_invalid_hex_rejected(self):
        d = self.entity()
        self.write_style(d, colors=[{"name": "Blue", "hex": "#12345", "role": "primary",
                                     "evidence": "observed", "source_url": None}])
        self.assertError(self.errors(d), "hex")

    def test_documented_style_requires_current_source(self):
        for status in ("documented", "observed"):
            with self.subTest(status=status):
                d = self.make_entity(id="xx-" + status, status="not-found")
                self.write_style(d, status=status, current_sources=[])
                self.assertError(self.errors(d), "current_sources")

    def test_none_style_needs_no_source(self):
        d = self.entity()
        self.write_style(d, status="none", current_sources=[], colors=[])
        self.assertEqual(self.errors(d), [])

    def test_previous_source_requires_superseded_fields(self):
        prev = {"url": "https://example.org/old", "kind": "guideline", "version_label": "2019",
                "sha256": None, "retrieved": "2025-01-01"}
        for missing in ("superseded_on", "change_summary"):
            with self.subTest(missing=missing):
                item = dict(prev, superseded_on="2026-01-01", change_summary="new logo")
                del item[missing]
                d = self.make_entity(id="xx-" + missing.replace("_", "-"), status="not-found")
                self.write_style(d, previous_sources=[item])
                self.assertError(self.errors(d), missing)

    def test_style_requires_last_checked(self):
        for i, val in enumerate((None, "yesterday", "2026-13-40")):
            with self.subTest(val=val):
                d = self.make_entity(id=f"xx-lc{i}", status="not-found")
                self.write_style(d, last_checked=val)
                self.assertError(self.errors(d), "last_checked")


class Coverage(Base):
    def test_coverage_requires_caa_and_ansp_per_state(self):
        # Austria: caa directly, ansp via also_countries on a pan-state entity.
        self.make_entity("at-caa", group="state", status="not-applicable", gaps=[], notes="n/a",
                         country="Austria", iso2="AT", types=["caa"])
        self.make_entity("eu-ansp", status="not-applicable", gaps=[], notes="n/a",
                         types=["ansp"], also_countries=["AT"])
        errs = validate.validate_repo(self.root)
        self.assertFalse([e for e in errs if "Austria" in e], errs)
        self.assertTrue(any("Belgium" in e and "caa" in e for e in errs))
        self.assertTrue(any("Belgium" in e and "ansp" in e for e in errs))
        self.assertEqual(len([e for e in errs if "Austria" in e]), 0)

    def test_coverage_names_state_missing_caa(self):
        self.make_entity("be-ansp", group="state", status="not-applicable", gaps=[], notes="n/a",
                         country="Belgium", iso2="BE", types=["ansp"])
        errs = validate.validate_repo(self.root)
        self.assertTrue(any("Belgium" in e and "caa" in e for e in errs))
        self.assertFalse(any("Belgium" in e and "ansp" in e for e in errs))

    def test_states_constant(self):
        self.assertEqual(len(validate.STATES), 44)
        self.assertEqual(set(validate.STATES), set(validate.STATE_ISO2))


if __name__ == "__main__":
    unittest.main()
