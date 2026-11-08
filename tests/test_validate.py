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

    def test_svg_with_script_rejected(self):
        bads = (b"<script>alert(1)</script>", b'<rect onclick="x()"/>',
                b'<image href="https://evil.example/a.png"/>')
        for i, bad in enumerate(bads):
            data = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">' + bad + b"</svg>"
            with self.subTest(bad=bad):
                d = self.entity_with_svg(data, id=f"xx-bad{i}")
                self.assertError(self.errors(d), "unsafe svg")

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
