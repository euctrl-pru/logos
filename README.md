# Logo and house style collection

This repository collects the official logos and house styles of aviation stakeholders: EUROCONTROL entities, European and international bodies, and the civil aviation authorities (CAAs) and air navigation service providers (ANSPs) of the EUROCONTROL member and comprehensive agreement states.

See [CATALOG.md](CATALOG.md) for every stakeholder and its status, and [gallery/index.html](gallery/index.html) for a preview of the logos.

## Layout

```text
CATALOG.md                 generated status table
gallery/index.html         generated logo preview
tools/                     validate.py, fetch_asset.py, build_catalog.py
tests/                     unit tests for the tools
stakeholders/
  eurocontrol/<id>/        EUROCONTROL entities
  european/<id>/           European bodies
  international/<id>/      international bodies
  states/<country>/<id>/   one folder per organisation, e.g. states/belgium/be-skeyes
```

Each `<id>/` folder contains:

```text
entity.json                identity, status, gaps and one record per logo file
logos/                     <id>-<lockup>-<background>[-<modifier>].<ext>
house-style/style.json     colours, typography, logo usage and their sources
house-style/README.md      generated
house-style/tokens.json    generated
house-style/tokens.css     generated
```

## Official-source rule

- Logos come only from a publisher's brand page, press kit or media library (`source_tier: 1`), or from a logo file served by the publisher's own website (`source_tier: 2`). Favicons do not count.
- Never use Wikipedia, Wikimedia, logo aggregators, search-result thumbnails or similar services.
- Files are stored byte-for-byte. Do not recolour, trace, remove backgrounds or convert formats. A missing variant is recorded in `gaps`.
- Do not bypass a login, portal, CAPTCHA or other access restriction. Record the entity as `restricted` and name the contact route in `gaps`.
- Do not commit guideline PDFs or font files. Link them from `style.json`.
- Record the publisher's logo terms in `terms_url`, and any limit on redistribution in `notes`.

## Add an entity

1. Create `stakeholders/<group>/<id>/`, or `stakeholders/states/<country>/<id>/` with an id of the form `<iso2>-<slug>`.
2. Write `entity.json` and `house-style/style.json`, using an existing entity as a template.
3. Fetch each logo into a new empty directory outside the repository:

   ```bash
   python3 tools/fetch_asset.py <url> <new-empty-dir> --domains example.org
   ```

4. Copy the file to `logos/` under its standard name, then add its record to `assets`.
5. Set `status`, and add a `gaps` entry for anything not found.

## Validation

```bash
python3 tools/build_catalog.py                # regenerate CATALOG.md, the gallery and house-style files
python3 tools/build_catalog.py --check        # fail if generated files are stale
python3 tools/validate.py --allow-pending     # validate, tolerating scaffolded entities
python3 tools/validate.py                     # validate with no pending entities allowed
python3 -W error -m unittest discover -s tests
```

## Help

In case you need help, don't hesitate to get in touch with the author(s).

## Author(s)

* [Quinten GOENS](mailto:Quinten.Goens@eurocontrol.int)
