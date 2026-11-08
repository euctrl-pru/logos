import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import build_catalog  # noqa: E402


def asset(file, background="light", transparent=False):
    return {"file": file, "lockup": "logo", "background": background, "color_mode": "color",
            "transparent": transparent, "source_url": "https://example.org/a",
            "page_url": "https://example.org", "source_tier": 1,
            "retrieved": "2026-01-01", "sha256": "0" * 64}


def style(eid, status="documented"):
    return {"id": eid, "status": status, "current_sources": [], "previous_sources": [],
            "last_checked": "2026-01-01",
            "colors": [{"name": "Blue", "hex": "#003399", "rgb": "0,51,153", "cmyk": None,
                        "role": "primary", "evidence": "guideline",
                        "source_url": "https://example.org/guide.pdf"}],
            "typography": [{"family": "Arial", "role": "body", "fallbacks": ["sans-serif"],
                            "evidence": "observed", "source_url": "https://example.org/site.css"}],
            "logo_usage": {"clear_space": None, "min_size": None,
                           "background_rules": None, "misuse": None},
            "retrieved": "2026-01-01", "notes": ""}


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def make(self, rel, eid, name="Test", group="european", country=None, status="partial",
             assets=None, sty="default"):
        d = self.root / "stakeholders" / rel
        (d / "house-style").mkdir(parents=True)
        ent = {"id": eid, "name": name, "acronym": eid.upper(), "group": group,
               "country": country, "status": status, "assets": assets or [],
               "gaps": [], "notes": ""}
        (d / "entity.json").write_text(json.dumps(ent))
        if sty == "default":
            sty = style(eid)
        if sty is not None:
            (d / "house-style" / "style.json").write_text(json.dumps(sty))
        return d


class CatalogTests(Base):
    def test_catalog_groups_states_by_country(self):
        self.make("states/france/fr-dsna", "fr-dsna", "DSNA", "state", "France")
        self.make("states/belgium/be-skeyes", "be-skeyes", "skeyes", "state", "Belgium")
        self.make("states/belgium/be-caa", "be-caa", "BCAA", "state", "Belgium")
        out = build_catalog.render_catalog(self.root)
        self.assertLess(out.index("### Belgium"), out.index("### France"))
        self.assertLess(out.index("be-caa"), out.index("be-skeyes"))
        self.assertLess(out.index("be-skeyes"), out.index("fr-dsna"))
        self.assertEqual(out.count("### Belgium"), 1)

    def test_catalog_shows_status_and_variants(self):
        self.make("european/xx-a", "xx-a", status="complete", assets=[
            asset("a.svg", "light", True), asset("b.svg", "dark")])
        self.make("european/xx-b", "xx-b", status="not-found")
        out = build_catalog.render_catalog(self.root)
        self.assertIn("| Status | light | dark | transparent |", out)
        rows = {l.split("|")[1].strip(): l for l in out.splitlines() if "xx-" in l}
        a = [c.strip() for c in next(v for k, v in rows.items() if "xx-a" in k).split("|")]
        b = [c.strip() for c in next(v for k, v in rows.items() if "xx-b" in k).split("|")]
        self.assertIn("complete", a)
        self.assertEqual(a[4:7], ["yes", "yes", "yes"])
        self.assertIn("not-found", b)
        self.assertEqual(b[4:7], ["no", "no", "no"])

    def test_catalog_links_are_relative_and_url_encoded(self):
        self.make("states/bosnia-and-herzegovina/ba x", "ba x", "Bosnia", "state", "Bosnia")
        out = build_catalog.render_catalog(self.root)
        self.assertIn("(stakeholders/states/bosnia-and-herzegovina/ba%20x/)", out)
        self.assertNotIn(str(self.root), out)

    def test_catalog_output_is_deterministic(self):
        self.make("european/xx-a", "xx-a", assets=[asset("a.svg")])
        self.make("eurocontrol/xx-b", "xx-b", group="eurocontrol")
        one = build_catalog.render_catalog(self.root)
        self.assertEqual(one, build_catalog.render_catalog(self.root))
        self.assertNotRegex(one, r"\d{2}:\d{2}")
        self.assertLess(one.index("xx-b"), one.index("xx-a"))


class StyleReadmeTests(Base):
    def test_style_readme_shows_evidence_for_each_value(self):
        out = build_catalog.render_style_readme(style("xx-a"), {"name": "Test", "id": "xx-a"})
        self.assertIn("#003399", out)
        self.assertIn("guideline", out)
        self.assertIn("https://example.org/guide.pdf", out)
        self.assertIn("Arial", out)
        self.assertIn("observed", out)
        self.assertIn("https://example.org/site.css", out)
        self.assertIn("unknown", out)

    def test_style_readme_marks_none_status_plainly(self):
        s = style("xx-a", "none")
        s["colors"], s["typography"] = [], []
        out = build_catalog.render_style_readme(s, {"name": "Test", "id": "xx-a"})
        self.assertIn("No public house style found", out)


class ExtrasTests(Base):
    def styled(self, rel, eid, **over):
        sty = style(eid)
        sty.update(over)
        return self.make(rel, eid, sty=sty)

    def test_tokens_css_has_only_recorded_values(self):
        d = self.styled("european/xx-a", "xx-a")
        files = build_catalog.generated_files(self.root)
        css = files[d / "house-style" / "tokens.css"]
        self.assertEqual(css.count(":root"), 1)
        self.assertIn("--xx-a-color-blue: #003399;", css)
        self.assertIn("--xx-a-font-body: Arial, sans-serif;", css)
        self.assertEqual(css.count("--"), 2)
        self.assertNotRegex(css, r"\d{2}:\d{2}")
        data = json.loads(files[d / "house-style" / "tokens.json"])
        self.assertEqual(data["colors"], {"blue": "#003399"})
        self.assertEqual(data["fonts"], {"body": "Arial, sans-serif"})

    def test_tokens_omit_null_values(self):
        d = self.styled("european/xx-a", "xx-a",
                        colors=[{"name": "Light Blue / 2", "hex": "#0055AA", "rgb": None, "cmyk": None,
                                 "role": None, "evidence": "observed", "source_url": None},
                                {"name": None, "hex": "#000000", "evidence": "observed"}],
                        typography=[{"family": "Arial", "role": None, "fallbacks": [],
                                     "evidence": "observed", "source_url": None},
                                    {"family": None, "role": "Display Font", "fallbacks": [],
                                     "evidence": "observed"}])
        files = build_catalog.generated_files(self.root)
        data = json.loads(files[d / "house-style" / "tokens.json"])
        self.assertEqual(data["colors"], {"light-blue-2": "#0055AA"})
        self.assertEqual(data["fonts"], {})
        self.assertNotIn("null", files[d / "house-style" / "tokens.css"])
        self.assertNotIn("None", files[d / "house-style" / "tokens.css"])

    def test_no_tokens_without_style(self):
        d = self.make("european/xx-a", "xx-a", sty=None)
        self.assertNotIn(d / "house-style" / "tokens.css", build_catalog.generated_files(self.root))

    def test_gallery_uses_relative_encoded_paths(self):
        self.make("states/bosnia/ba x", "ba x", assets=[
            asset("ba x-logo-light.svg"), dict(asset("previous/ba x-logo-light.svg"), superseded=True)])
        out = build_catalog.generated_files(self.root)[self.root / "gallery" / "index.html"]
        self.assertIn('src="../stakeholders/states/bosnia/ba%20x/logos/ba%20x-logo-light.svg"', out)
        self.assertNotIn("previous", out)
        self.assertEqual(out.count("<img"), 2)  # light and dark tile
        self.assertNotIn(str(self.root), out)
        self.assertNotIn("<script", out)
        self.assertNotIn("http", out)

    def test_gallery_is_deterministic(self):
        self.make("european/xx-a", "xx-a", assets=[asset("a.svg")])
        self.make("eurocontrol/xx-b", "xx-b", group="eurocontrol", assets=[asset("b.svg")])
        one = build_catalog.generated_files(self.root)[self.root / "gallery" / "index.html"]
        self.assertEqual(one, build_catalog.generated_files(self.root)[self.root / "gallery" / "index.html"])
        self.assertLess(one.index("xx-b"), one.index("xx-a"))
        self.assertNotRegex(one, r"\d{2}:\d{2}")

    def test_check_covers_new_files(self):
        d = self.styled("european/xx-a", "xx-a")
        self.assertEqual(build_catalog.main(root=self.root), 0)
        for p in (d / "house-style" / "tokens.css", d / "house-style" / "tokens.json",
                  self.root / "gallery" / "index.html"):
            self.assertTrue(p.exists(), p)
            self.assertEqual(build_catalog.main(check=True, root=self.root), 0)
            p.write_text("stale")
            self.assertEqual(build_catalog.main(check=True, root=self.root), 1)
            build_catalog.main(root=self.root)

    def test_superseded_not_in_catalog_columns(self):
        self.make("european/xx-a", "xx-a", status="partial", assets=[
            dict(asset("previous/a.svg", "dark", True), superseded=True)])
        row = [l for l in build_catalog.render_catalog(self.root).splitlines() if "xx-a" in l][0]
        cells = [c.strip() for c in row.split("|")]
        self.assertEqual(cells[4:8], ["no", "no", "no", "0"])


class CheckTests(Base):
    def test_check_mode_detects_stale_file(self):
        d = self.make("european/xx-a", "xx-a")
        self.assertEqual(build_catalog.main(root=self.root), 0)
        self.assertTrue((self.root / "CATALOG.md").exists())
        self.assertTrue((d / "house-style" / "README.md").exists())
        self.assertEqual(build_catalog.main(check=True, root=self.root), 0)
        (d / "house-style" / "README.md").write_text("stale")
        self.assertEqual(build_catalog.main(check=True, root=self.root), 1)
        self.assertEqual(build_catalog.main(root=self.root), 0)
        self.assertEqual(build_catalog.main(check=True, root=self.root), 0)
        (self.root / "CATALOG.md").unlink()
        self.assertEqual(build_catalog.main(check=True, root=self.root), 1)

    def test_not_applicable_without_style_skips_readme(self):
        d = self.make("states/malta/mt-x", "mt-x", group="state", country="Malta",
                      status="not-applicable", sty=None)
        self.assertEqual(build_catalog.main(root=self.root), 0)
        self.assertFalse((d / "house-style" / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
