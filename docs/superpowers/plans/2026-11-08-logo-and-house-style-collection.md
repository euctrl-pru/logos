# Logo and House Style Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the repo into one validated folder per stakeholder, each holding official logo variants, source records and a structured house style.

**Architecture:** Each stakeholder folder is self-describing: `entity.json` records identity, provenance and gaps, and `house-style/style.json` records the design system. Stdlib-only Python tools validate those records and the real file bytes, fetch assets with an official-host check, and generate the catalog. Sourcing is then repeated research in four reviewable batches.

**Tech Stack:** Python 3.14 stdlib only (`unittest`, `urllib`, `zlib`, `json`, `xml.etree`), git. Pillow, PyYAML and pytest are not installed and must not be added.

**Spec:** No separate spec. The requirements are the user's request of 2026-11-08: analyse what is missing; add logos from official sources only; collect several types (transparent, for dark, for light); add a folder per stakeholder with a structured house style; restructuring the repo is allowed.

## Gap Analysis (2026-11-08)

| Area | Expected | Present |
|---|---|---|
| EUROCONTROL entities | 4 | ECTL has 1 SVG; AI+ has 2 SVG icons and 2 logos; NM and CRCO are empty |
| European stakeholders | 8 | 8 empty folders |
| International stakeholders | 8 | Empty group; no entity folders |
| CAAs, listed in README | 36 | No folders under `04/04` or `05/04` |
| ANSPs, listed in README | 36 | No folders under `04/01` or `05/01` |
| House styles | Every stakeholder | None |

Defects found:

- The two AI+ "`.png`" files are JPEGs, so they cannot be transparent.
- `EUROCONTROL Entities/...` is a stale tracked duplicate of the ECTL logo, already deleted in the working tree.
- The README lists 34 Member States; EUROCONTROL lists 42. Missing: Armenia, Austria, Czech Republic, Estonia, Finland, Georgia, Monaco, Republic of Moldova.
- The README header hotlinks a Wikimedia image, which is not an official source.
- Several README rows look outdated or wrong and must be checked against official sites: Belgocontrol (now skeyes), BULATSA listed as a CAA, IAA and HCAA listed as ANSPs, BHDCA and CAAI listed as ANSPs, and Morocco's authority name.
- Empty folders are not tracked by git, so the `04`/`05` category trees exist only locally.

## Target Structure

```text
README.md                       purpose, layout, rules, how to add an entity
CATALOG.md                      generated status table
docs/prompts/check-house-style-updates.md   reusable update-check prompt
tools/{validate,fetch_asset,build_catalog}.py
tests/test_{validate,fetch_asset,build_catalog}.py
stakeholders/
  eurocontrol/<id>/             ectl, ai-plus, nm, crco
  european/<id>/                prc, eu, ec, easa, sesar, sju, era, ebaa
  international/<id>/           iata, icao, aci, canso, ifalpa, ifatca, a4e, a4a
  states/<country-slug>/<id>/   e.g. states/belgium/be-skeyes
```

Every `<id>/` contains:

```text
entity.json
logos/<id>-<lockup>-<background>[-<modifier>].<ext>
house-style/style.json
house-style/README.md           generated
```

## Record Formats

`entity.json` fields: `id`, `name`, `acronym`, `group` (`eurocontrol|european|international|state`), `country` (name or null), `iso2` (or null), `also_countries` (ISO2 list), `membership` (`member|comprehensive-agreement|null`), `types` (subset of `ectl-entity, institution, association, caa, ansp`), `official_domains`, `terms_url`, `aliases`, `notes`, `status`, `gaps` (list of `{need, reason}`), `assets`.

`status` values:

| Value | Meaning |
|---|---|
| `complete` | Has a `light` asset, a `dark` asset and a transparent asset |
| `partial` | At least one asset; `gaps` is non-empty |
| `restricted` | Publisher limits access; no assets; `gaps` is non-empty |
| `not-found` | No official file located; no assets; `gaps` is non-empty |
| `not-applicable` | Role does not exist in this state; no assets; `notes` is non-empty |
| `pending` | Scaffolded only; not allowed once Task 9 starts |

Each `assets[]` item has: `file`, `lockup` (`logo|icon|wordmark|emblem|boxed|with-slogan`), `background` (`light|dark|any`), `color_mode` (`color|white|black|mono`), `transparent` (bool), `source_url`, `page_url`, `source_tier` (`1|2|internal`), `retrieved` (ISO date), `sha256`.

`style.json` fields: `id`, `status` (`documented|observed|none`), `current_sources`, `previous_sources`, `last_checked` (ISO date), `colors` (list of `{name, hex, rgb, cmyk, role, evidence, source_url}`), `typography` (list of `{family, role, fallbacks, evidence, source_url}`), `logo_usage` (`{clear_space, min_size, background_rules, misuse}`), `retrieved`, `notes`. `evidence` is `guideline` or `observed`. Unknown values are `null`, never guessed.

Each `current_sources[]` item has: `url`, `kind` (`guideline|brand-page|website-css`), `version_label` (publisher's edition or year, or null), `sha256` (of the downloaded guideline file; null for web pages), `retrieved`. Each `previous_sources[]` item has the same fields plus `superseded_on` (ISO date) and `change_summary`. When a source is replaced, it moves to `previous_sources` and is never deleted.

## Global Constraints

- Official sources only: a publisher's brand page, press kit or media library (`source_tier: 1`), or a logo file served by the publisher's own website (`source_tier: 2`). Favicons do not count.
- Never use Wikipedia, Wikimedia, logo aggregators, search-result thumbnails or `Brandfetch`-style services.
- Store official files byte-for-byte. Never recolour, trace, remove backgrounds, convert formats or otherwise derive a variant. A missing variant is recorded in `gaps`. EUROCONTROL's terms explicitly prohibit modification.
- Never bypass a login, portal, CAPTCHA or access restriction. Record `restricted` and name the contact route in `gaps`. IATA is the known case: its logo is limited to accredited agents through its Customer Portal.
- Do not commit guideline PDFs or font files. Link them from `style.json`.
- `terms_url` is set whenever the publisher has logo terms. Record any restriction on redistribution in `notes`, because `euctrl-pru/logos` is hosted on GitHub.
- Put each download or extracted archive in its own new empty directory under the scratchpad, keep scripts elsewhere, and run Python that reads them with `-I`.
- Work on branch `feature/logos-house-styles`. Commit only there and do not push unless the user asks.
- Commit messages are brief, with no Claude author, co-author or "Generated with" line (user's global instruction).
- Member-state source of truth: <https://www.eurocontrol.int/our-member-and-comprehensive-agreement-states>.

## Review Focus

1. An official URL returns an HTML error or login page with status 200: it must be rejected, not stored as a logo.
2. A file's extension disagrees with its bytes (the AI+ JPEGs named `.png`): validation fails.
3. A file labelled transparent has an opaque background (SVG full-bleed rectangle, RGBA PNG with all alpha 255): validation fails.
4. A lookalike or redirected host (`eurocontrol.int.example.com`, or a redirect to Wikimedia): the fetch is refused.
5. An entity with no public logo must stay honest: `restricted` or `not-found` needs a recorded gap, and `complete` needs all three variants.

---

### Task 1: Entity validator

**Files:**
- Create: `tools/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Produces: `sniff_format(data: bytes) -> str | None` returning `png|jpg|svg|pdf|eps|None`; `host_is_official(url: str, domains: list[str]) -> bool`; `is_transparent(path: Path) -> bool`; `validate_entity(entity_dir: Path) -> list[str]`; `validate_repo(root: Path) -> list[str]`, including coverage checks. CLI: `python3 tools/validate.py [--allow-pending]`, exit 0 only with no errors.

- [ ] **Step 1: Write failing tests** using temp directories and PNG bytes built with `zlib` and `struct`.

| Test | Asserts |
|---|---|
| `test_html_named_svg_rejected` | `<!doctype html>` in `x.svg` gives an error containing `format` |
| `test_jpeg_named_png_rejected` | Bytes `\xff\xd8\xff...` in `x.png` give an error containing `format` |
| `test_svg_with_script_rejected` | `<script>`, an `on*=` attribute or a remote `href` gives an error containing `unsafe svg` |
| `test_svg_fullbleed_rect_not_transparent` | First drawn `rect` covers at least 99% of the viewBox with a non-`none` fill: `is_transparent` is False |
| `test_svg_without_background_transparent` | `is_transparent` is True |
| `test_rgba_png_all_opaque_not_transparent` | Alpha all 255: False |
| `test_rgba_png_with_clear_pixel_transparent` | One pixel with alpha 0: True |
| `test_lookalike_host_rejected` | `host_is_official("https://eurocontrol.int.example.com/a.svg", ["eurocontrol.int"])` is False |
| `test_subdomain_accepted` | `host_is_official("https://www.ec.europa.eu/a.svg", ["europa.eu"])` is True |
| `test_banned_host_rejected` | Source on `upload.wikimedia.org` is an error even if it is listed in `official_domains` |
| `test_sha_mismatch_rejected` | Error containing `sha256` |
| `test_complete_requires_three_variants` | `complete` lacking `dark` gives an error containing `complete` |
| `test_restricted_requires_gap` | `restricted` with empty `gaps` gives an error |
| `test_restricted_with_assets_rejected` | Error |
| `test_unrecorded_logo_file_rejected` | A file in `logos/` absent from `assets` gives an error containing `unrecorded` |
| `test_filename_convention` | `Logo Final.svg` gives an error containing `name` |
| `test_observed_or_guideline_evidence_required` | A colour with no `evidence` gives an error |
| `test_invalid_hex_rejected` | `#12345` gives an error |
| `test_documented_style_requires_current_source` | `documented` or `observed` with empty `current_sources` gives an error |
| `test_previous_source_requires_superseded_fields` | A `previous_sources` item lacking `superseded_on` or `change_summary` gives an error |
| `test_style_requires_last_checked` | Missing or non-ISO `last_checked` gives an error |
| `test_pending_rejected_by_default` | Error unless `--allow-pending` |
| `test_coverage_requires_caa_and_ansp_per_state` | A state missing a `caa` gives an error naming the state; `also_countries` counts; `not-applicable` entities count |

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL with `ModuleNotFoundError: validate`.

- [ ] **Step 3: Implement `tools/validate.py`** with the signatures above. `is_transparent` decodes non-interlaced PNGs by reversing scanline filters; interlaced PNGs or palette PNGs without `tRNS` return False. The banned-host list is `wikipedia.org, wikimedia.org, brandfetch.com, seeklogo.com, worldvectorlogo.com, logowik.com, vectorlogo.zone`. `is_transparent` must equal the asset's `transparent` field. JPEG is always non-transparent. Coverage loads the 44 state names from a `STATES` constant holding the list in Task 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests `OK`.

- [ ] **Step 5: Commit**

```bash
git checkout -b feature/logos-house-styles
git add tools/validate.py tests/test_validate.py
git commit -m "Add entity and logo validator"
```

### Task 2: Official-source fetcher

**Files:**
- Create: `tools/fetch_asset.py`
- Test: `tests/test_fetch_asset.py`

**Interfaces:**
- Consumes: `sniff_format`, `host_is_official`, `is_transparent` from Task 1.
- Produces: `fetch(url: str, dest_dir: Path, domains: list[str]) -> Path`; `make_asset_record(path: Path, source_url: str, page_url: str, tier: int | str, lockup: str, background: str, color_mode: str) -> dict`; `safe_extract_zip(zip_path: Path, dest_dir: Path) -> list[Path]`. Raises `FetchRefused` on any refusal. CLI: `python3 tools/fetch_asset.py URL DEST --domains a,b`.

- [ ] **Step 1: Write failing tests** with a local `http.server` thread and an injected opener:
  - `test_refuses_nonofficial_host`
  - `test_refuses_redirect_to_other_host`, checking every hop
  - `test_refuses_html_body_with_200`
  - `test_refuses_body_over_25_mb`
  - `test_zip_slip_member_refused`, for a `../evil.svg` member
  - `test_record_has_sha256_and_today`
  - `test_record_transparent_is_computed`

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_fetch_asset -v`
Expected: FAIL with `ModuleNotFoundError: fetch_asset`.

- [ ] **Step 3: Implement `tools/fetch_asset.py`.** Use a generic `User-Agent` such as `logo-collector/1.0`, a 30-second timeout and manual redirect handling. Do not send personal contact details in any header. `dest_dir` must be new and empty.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/fetch_asset.py tests/test_fetch_asset.py
git commit -m "Add official-source asset fetcher"
```

### Task 3: Catalog and house-style generator

**Files:**
- Create: `tools/build_catalog.py`
- Test: `tests/test_build_catalog.py`

**Interfaces:**
- Consumes: the record formats above.
- Produces: `render_catalog(root: Path) -> str`; `render_style_readme(style: dict, entity: dict) -> str`; `main(check: bool = False)`. CLI flag `--check` exits 1 if any generated file is stale.

- [ ] **Step 1: Write failing tests:**
  - `test_catalog_groups_states_by_country`
  - `test_catalog_shows_status_and_variants`: columns `light`, `dark`, `transparent`
  - `test_catalog_links_are_relative_and_url_encoded`
  - `test_catalog_output_is_deterministic`: two runs are identical, with no timestamp
  - `test_style_readme_shows_evidence_for_each_value`
  - `test_style_readme_marks_none_status_plainly`: contains `No public house style found`
  - `test_check_mode_detects_stale_file`

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_build_catalog -v`
Expected: FAIL with `ModuleNotFoundError: build_catalog`.

- [ ] **Step 3: Implement `tools/build_catalog.py`,** writing `CATALOG.md` and each `house-style/README.md`, sorted by group, country and id.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add tools/build_catalog.py tests/test_build_catalog.py
git commit -m "Add catalog generator"
```

### Task 4: Restructure repo and pilot on ECTL

**Files:**
- Create: `.gitignore` (`.DS_Store`), `stakeholders/**/entity.json`, `stakeholders/**/house-style/style.json`, `CATALOG.md`
- Move: `01 EUROCONTROL Entities/AI+ - Aviation Intelligence+/*` to `stakeholders/eurocontrol/ai-plus/logos/`, with `.jpg` extensions for the two JPEGs
- Delete: `EUROCONTROL Entities/`, `01 EUROCONTROL Entities/ECTL - EUROCONTROL/logos/ec-logo-default.svg` (replaced by the official download), all tracked `.DS_Store` files, and the now-empty numbered directories
- Modify: `README.md`

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces: the folder for every stakeholder that Tasks 5 to 8 fill.

`STATES`, the 44 states: Albania, Armenia, Austria, Belgium, Bosnia and Herzegovina, Bulgaria, Croatia, Cyprus, Czech Republic, Denmark, Estonia, Finland, France, Georgia, Germany, Greece, Hungary, Iceland, Ireland, Italy, Latvia, Lithuania, Luxembourg, Malta, Monaco, Montenegro, Netherlands, North Macedonia, Norway, Poland, Portugal, Republic of Moldova, Romania, Serbia, Slovakia, Slovenia, Spain, Sweden, Switzerland, Türkiye, Ukraine, United Kingdom, plus Israel and Morocco as `comprehensive-agreement`.

- [ ] **Step 1: Scaffold.** Create one `pending` folder per entity in Target Structure, and one CAA and one ANSP per state. Use the README row where one exists; ids are `<iso2>-<slug>`, e.g. `be-bcaa`. If one body fills both roles, create one folder with both `types`. If one body serves two states (SMATSA for Serbia and Montenegro), create one folder and use `also_countries`.

- [ ] **Step 2: Verify the scaffold**

Run: `python3 tools/validate.py --allow-pending`
Expected: exit 0, with no coverage errors for any of the 44 states.

- [ ] **Step 3: Pilot ECTL** from <https://www.eurocontrol.int/brand>. Fetch all three flat SVGs and six boxed SVGs, then fill `style.json` from the 2024 visual identity guide. It must include `#003366`, `#2990EA`, the three typefaces with their roles, the 12 mm minimum size, and the rule that dark backgrounds need the boxed logo. Check each value against the PDF. Record the terms from the brand page, including the bans on sale and modification.

- [ ] **Step 4: Migrate AI+.** Record the existing files with `source_tier: "internal"`, `source_url: "repo-history"`, status `partial`, and a gap for a transparent full logo.

- [ ] **Step 5: Rewrite `README.md`** to cover purpose, layout, the official-source rule, how to add an entity, and validation commands. Remove the entity lists (now in `CATALOG.md`) and the Wikimedia hotlink. Keep the author section.

- [ ] **Step 6: Verify the move lost nothing**

Run: `python3 tools/build_catalog.py && python3 tools/validate.py --allow-pending && git status --short && find . -path ./.git -prune -o -type d -empty -print`
Expected: validator exit 0; ECTL is `complete` only if a transparent asset was verified; no empty directories except unfilled `logos/`, which are expected to be absent from git.

- [ ] **Step 7: Commit**

```bash
git add -A .gitignore README.md CATALOG.md stakeholders tools tests "EUROCONTROL Entities" "01 EUROCONTROL Entities"
git commit -m "Restructure repo by stakeholder and add ECTL assets"
```

### Sourcing Procedure (used by Tasks 5 to 8)

For each entity, in order:

1. Confirm the entity's current name and official site through a web search. Update `name`, `aliases` and `notes` for rebrands or role changes. Use the current logo, not a former one.
2. Look for a brand page, press or media centre, or downloads page.
3. If none exists, use a logo file served by the official site, preferring SVG, then the largest PNG (`source_tier: 2`).
4. Fetch with `tools/fetch_asset.py`. Open every raster with the `Read` tool to confirm it is the right logo and `background` is right. Classify `background` from the publisher's label or visible colours: coloured or dark artwork is `light`, white artwork is `dark`, and only choose `any` if the publisher says so.
5. Fill `style.json` from official guidelines (`documented`), or else from the official site's own CSS (`observed`), or else `none`. Never infer colours from memory.
6. Set the final status and write a precise `gaps` entry for anything not found, e.g. `{"need": "dark variant", "reason": "brand page offers colour PNG only"}`.
7. Spend at most about 10 minutes per entity, then record the gap and move on.

Every batch ends with `python3 tools/build_catalog.py && python3 tools/validate.py --allow-pending` exiting 0, then a commit of only `stakeholders` and `CATALOG.md`. Report the batch's status counts and any list corrections.

### Task 5: EUROCONTROL and European batch

**Files:** Modify `stakeholders/eurocontrol/{nm,crco}/**` and `stakeholders/european/**`.

**Interfaces:** Consumes the Sourcing Procedure and Task 2's CLI.

- [ ] **Step 1: Source EU and EC first.** The EU emblem comes from <https://european-union.europa.eu/principles-countries-history/symbols/european-flag_en>, and colours and geometry from the [graphics guide](https://style-guide.europa.eu/en/content/-/isg/topic?identifier=annex-a1-graphics-guide-european-emblem). Include full colour, white and blue, and black and white versions.
- [ ] **Step 2: Source NM, CRCO, PRC, EASA, SESAR, SJU, ERA and EBAA.** NM, CRCO and PRC may have no separate logo; if EUROCONTROL publishes none, record `not-found` rather than reusing the ECTL logo. Resolve whether SESAR and SJU have distinct current identities, and note the result.
- [ ] **Step 3: Verify:** `python3 tools/validate.py --allow-pending` exits 0.
- [ ] **Step 4: Commit:** `git commit -m "Add EUROCONTROL and European stakeholder assets"`

### Task 6: International batch

**Files:** Modify `stakeholders/international/**`.

**Interfaces:** Consumes the Sourcing Procedure and Task 2's CLI.

- [ ] **Step 1: Source ICAO, ACI, CANSO, IFALPA, IFATCA, A4E and A4A.** Record restrictive terms in `notes`.
- [ ] **Step 2: Record IATA as `restricted`.** Do not take its logo from its website or portal. Give the [portal FAQ](https://portal.iata.org/faq/articles/en_US/FAQ/Where-can-I-find-the-IATA-logo-and-how-can-I-use-it-1415811051031) as the route in `gaps`.
- [ ] **Step 3: Verify:** `python3 tools/validate.py --allow-pending` exits 0.
- [ ] **Step 4: Commit:** `git commit -m "Add international stakeholder assets"`

### Task 7: Civil aviation authorities batch

**Files:** Modify every state entity whose `types` contains `caa`.

**Interfaces:** Consumes the Sourcing Procedure and Task 2's CLI.

- [ ] **Step 1: Source all 44 states' CAAs**, in `STATES` order. Correct the README-derived errors listed in the Gap Analysis. If a state's government identity is the only logo, record that in `notes`.
- [ ] **Step 2: Verify:** `python3 tools/validate.py --allow-pending` exits 0, with no CAA still `pending`.
- [ ] **Step 3: Commit:** `git commit -m "Add civil aviation authority assets"`

### Task 8: ANSP batch

**Files:** Modify every state entity whose `types` contains `ansp`.

**Interfaces:** Consumes the Sourcing Procedure and Task 2's CLI.

- [ ] **Step 1: Source all 44 states' ANSPs.** Use `not-applicable` where no national ANSP exists, with the serving provider named in `notes` (check Monaco).
- [ ] **Step 2: Verify:** `python3 tools/validate.py --allow-pending` exits 0, with no ANSP still `pending`.
- [ ] **Step 3: Commit:** `git commit -m "Add air navigation service provider assets"`

### Task 9: Final audit

**Files:** Modify any entity the audit corrects, plus `CATALOG.md`.

**Interfaces:** Consumes the whole collection.

- [ ] **Step 1: Run strict validation**

Run: `python3 tools/validate.py && python3 tools/build_catalog.py --check && python3 -m unittest discover -s tests`
Expected: all exit 0, and no `pending` entities remain.

- [ ] **Step 2: Sample-audit provenance.** Re-open `page_url` and compare the logo for 15 randomly chosen assets, covering every group. Fix every wrong result, and extend the audit to that whole batch if more than one is wrong.

- [ ] **Step 3: Create `docs/prompts/check-house-style-updates.md`** with exactly the prompt below, and link it from `README.md`.

```markdown
Check this repository for updates to stakeholder house styles and logos. Work on a new branch and do not push.

Scope: every `stakeholders/**/house-style/style.json`, or only these ids if listed here: <ids or "all">.

For each stakeholder:
1. Read `style.json` and `entity.json`. Revisit each `current_sources` URL and the official site in `official_domains`.
2. Search the official domains for a newer guideline, brand page, rebrand announcement or logo files. Use official sources only, under the rules in `README.md`. Never bypass a login or access restriction.
3. Compare against the record: `version_label`; the `sha256` of guideline files, downloaded to a new empty directory in temporary storage and never committed; colours; typography; logo usage rules; and each asset's `sha256` from `entity.json`.
4. Classify the stakeholder as `unchanged`, `changed`, `source-moved` (same content, new URL), `new-source-found` (for a stakeholder with status `none`, or an entity with a gap that can now be closed), or `unreachable`.

Update only what you verified:
- Always set `last_checked` to today, except for `unreachable` stakeholders.
- For `changed` or `source-moved`, move the old entry to `previous_sources` with `superseded_on` and a one-sentence `change_summary`, add the new entry to `current_sources`, then update the affected values.
- Replace changed logo files only with official files, using `tools/fetch_asset.py`, and update their records. Keep prior versions available through git history.
- Do not record a change you inferred from memory. Treat a site that cannot be reached as `unreachable`, and keep its existing data.

Finish by running `python3 tools/build_catalog.py`, `python3 tools/validate.py` and `python3 -m unittest discover -s tests`. Report a table of stakeholder, classification, what changed and source URL, followed by anything needing a human decision. Commit only if the checks pass.
```

- [ ] **Step 4: Verify the prompt's references exist**

Run: `test -f tools/fetch_asset.py && test -f tools/build_catalog.py && test -f tools/validate.py && grep -q check-house-style-updates README.md && echo ok`
Expected: `ok`.

- [ ] **Step 5: Report results to the user:** counts by status, entities restricted or not found, list corrections, and any terms that may limit public redistribution.

- [ ] **Step 6: Commit** corrections and the prompt: `git add docs/prompts README.md stakeholders CATALOG.md && git commit -m "Add house style update prompt and audit corrections"`

---

## Scope Amendment (user decisions, 2026-11-08)

The user chose: fill all categories now; the repo will be made private by the user (do not change its visibility); collect all proposed extras.

**Execution order:** 1, 2, 3, 10, 4, 5, 6, 7, 8, 11, 12, 9. Task 9 stays last.

**Inclusion rule for categories** (the full population is thousands of organisations, so each state is capped and the selection is recorded):

| Category | `types` value | Per-state cap | Selection |
|---|---|---|---|
| Airlines | `airline` | 5 | Largest active operators certificated in that state |
| Airports | `airport` | 5 | Busiest by commercial passengers |
| Training institutes | `training` | 3 | Approved by the national CAA or EASA |
| Industry associations | `association` | 3 | National aviation or airline associations |
| Manufacturers | `manufacturer` | 3 | Headquartered in the state |
| MRO providers | `mro` | 3 | Largest approved organisations headquartered in the state |
| Fuel suppliers | `fuel` | 3 | Major into-plane or SAF suppliers active in the state |
| Air travel service providers | `travel-services` | 3 | Largest travel agencies, GDS or booking companies headquartered in the state |
| Ground handlers | `ground-handling` | 3 | Largest active handlers at the state's main airport |

An organisation appears once, in the state of its headquarters, with `also_countries` for its other states. Fewer than the cap is acceptable; do not pad. Each entity's `notes` gives the reason it qualified. Keep the Sourcing Procedure, but cap research at 5 minutes per entity for these categories.

### Task 10: Schema extensions for extras

**Files:** Modify `tools/validate.py`, `tools/build_catalog.py` and their tests.

**Interfaces:**
- Consumes: Tasks 1 and 3.
- Produces: these record additions, used by all later tasks.
  - `types` also accepts the values in the table above, plus `partner`.
  - Asset fields `language` (ISO 639-1 or null), `superseded` (bool, default false), `valid_until` (ISO date or null). Superseded files live in `logos/previous/`.
  - `entity.json` field `contact`: `{logo_permission_url, email, notes}`, with null for unknowns.
  - Generated `house-style/tokens.json` and `house-style/tokens.css` (custom properties `--<id>-color-<name>` and `--<id>-font-<role>`), and `gallery/index.html` showing each logo on light and dark backgrounds using relative paths.

- [ ] **Step 1: Write failing tests:** `test_new_types_accepted`, `test_superseded_asset_must_be_in_previous_dir`, `test_superseded_assets_do_not_satisfy_complete`, `test_language_must_be_iso639`, `test_contact_required_keys`, `test_tokens_css_has_only_recorded_values`, `test_tokens_omit_null_values`, `test_gallery_uses_relative_encoded_paths`, `test_gallery_is_deterministic`.
- [ ] **Step 2: Run tests to verify they fail:** `python3 -m unittest discover -s tests -v`; expected FAIL on the new tests.
- [ ] **Step 3: Implement** the additions.
- [ ] **Step 4: Run tests to verify they pass:** same command; expected `OK`.
- [ ] **Step 5: Commit:** `git commit -m "Add language, history, contact, tokens and gallery support"`

### Task 11: Extras on existing entities and new partners

**Files:** Modify `stakeholders/**`; create `stakeholders/eurocontrol/muac/`, and `stakeholders/international/{eurocae,ecac,faa}/`.

**Interfaces:** Consumes Task 10 and the Sourcing Procedure.

- [ ] **Step 1: Source MUAC, EUROCAE, ECAC and FAA.**
- [ ] **Step 2: For every entity, fill `contact`,** and add officially published previous logos and language lockups where the publisher offers them. Never take either from a third-party archive. The EU emblem translations come from the [Commission download centre](https://ec.europa.eu/regional_policy/information-sources/logo-download-center_en).
- [ ] **Step 3: Verify:** `python3 tools/build_catalog.py && python3 tools/validate.py --allow-pending` exits 0.
- [ ] **Step 4: Commit:** `git commit -m "Add partners, contacts, previous logos and language variants"`

### Task 12: Category batches

**Files:** Create `stakeholders/states/<country-slug>/<id>/` for each selected organisation.

**Interfaces:** Consumes Task 10, the Inclusion rule and the Sourcing Procedure.

Work one category at a time, in table order. For each category, produce the selection, source its entities, run `python3 tools/build_catalog.py && python3 tools/validate.py --allow-pending`, and commit with `git commit -m "Add <category> assets"`.

- [ ] **Step 1: Airlines**
- [ ] **Step 2: Airports**
- [ ] **Step 3: Training institutes**
- [ ] **Step 4: Industry associations**
- [ ] **Step 5: Manufacturers**
- [ ] **Step 6: MRO providers**
- [ ] **Step 7: Fuel suppliers**
- [ ] **Step 8: Air travel service providers**
- [ ] **Step 9: Ground handlers**
