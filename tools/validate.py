#!/usr/bin/env python3
"""Validate stakeholder entity folders (entity.json, logos/, house-style/style.json)."""
import argparse
import datetime
import hashlib
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from urllib.parse import urlparse

STATE_ISO2 = {
    "Albania": "AL", "Armenia": "AM", "Austria": "AT", "Belgium": "BE",
    "Bosnia and Herzegovina": "BA", "Bulgaria": "BG", "Croatia": "HR", "Cyprus": "CY",
    "Czech Republic": "CZ", "Denmark": "DK", "Estonia": "EE", "Finland": "FI",
    "France": "FR", "Georgia": "GE", "Germany": "DE", "Greece": "GR", "Hungary": "HU",
    "Iceland": "IS", "Ireland": "IE", "Italy": "IT", "Latvia": "LV", "Lithuania": "LT",
    "Luxembourg": "LU", "Malta": "MT", "Monaco": "MC", "Montenegro": "ME",
    "Netherlands": "NL", "North Macedonia": "MK", "Norway": "NO", "Poland": "PL",
    "Portugal": "PT", "Republic of Moldova": "MD", "Romania": "RO", "Serbia": "RS",
    "Slovakia": "SK", "Slovenia": "SI", "Spain": "ES", "Sweden": "SE",
    "Switzerland": "CH", "Türkiye": "TR", "Ukraine": "UA", "United Kingdom": "GB",
    # comprehensive agreement states
    "Israel": "IL", "Morocco": "MA",
}
STATES = list(STATE_ISO2)

BANNED_HOSTS = ["wikipedia.org", "wikimedia.org", "brandfetch.com", "seeklogo.com",
                "worldvectorlogo.com", "logowik.com", "vectorlogo.zone"]
GROUPS = {"eurocontrol", "european", "international", "state"}
TYPES = {"ectl-entity", "institution", "association", "caa", "ansp", "airline", "airport", "training",
         "manufacturer", "mro", "fuel", "travel-services", "ground-handling", "partner"}
CONTACT_KEYS = {"logo_permission_url", "email", "notes"}
PREVIOUS = "previous/"
STATUSES = {"complete", "partial", "restricted", "not-found", "not-applicable", "pending"}
LOCKUPS = {"logo", "icon", "wordmark", "emblem", "boxed", "with-slogan"}
BACKGROUNDS = {"light", "dark", "any"}
COLOR_MODES = {"color", "white", "black", "mono"}
EXTENSIONS = {"svg": "svg", "png": "png", "jpg": "jpg", "jpeg": "jpg", "pdf": "pdf", "eps": "eps", "webp": "webp", "gif": "gif"}
ENTITY_FIELDS = ["id", "name", "acronym", "group", "country", "iso2", "also_countries", "membership",
                 "types", "official_domains", "terms_url", "aliases", "notes", "status", "gaps", "assets", "contact"]
SOURCE_KINDS = {"guideline", "brand-page", "website-css"}
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
DRAWN = {"rect", "circle", "ellipse", "path", "polygon", "polyline", "line", "image", "text", "use"}


# ---------------------------------------------------------------- format / transparency

def sniff_format(data: bytes):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"%!PS") or data.startswith(b"\xc5\xd0\xd3\xc6"):
        return "eps"
    text = data[:4096].decode("utf-8", "ignore").lstrip("﻿ \t\r\n").lower()
    if text.startswith(("<!doctype html", "<html")):
        return None
    if text.startswith(("<?xml", "<svg", "<!--", "<!doctype svg")) and "<svg" in data[:65536].decode("utf-8", "ignore").lower():
        return "svg"
    return None


def host_is_official(url: str, domains: list) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)


def _is_banned(url: str) -> bool:
    return host_is_official(url, BANNED_HOSTS)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _num(value, ref):
    """Parse an SVG length; percentages are relative to ref. None if unparseable."""
    m = re.fullmatch(r"\s*([-+]?[\d.]+)\s*(%|px)?\s*", value or "")
    if not m:
        return None
    n = float(m.group(1))
    return n * ref / 100 if m.group(2) == "%" else n


def _fill(el, css=None):
    return _style_prop(el, "fill", css) or "black"


NON_RENDERED = {"defs", "clipPath", "mask", "pattern", "symbol", "marker", "metadata", "title", "desc"}


def _drawn(el):
    """Yield drawn elements in document order, skipping non-rendered containers."""
    for child in el:
        name = _local(child.tag)
        if name in NON_RENDERED:
            continue
        if name in DRAWN:
            yield child
        yield from _drawn(child)


def _css_rules(root):
    """Map simple selectors (.class, element, *) in <style> blocks to {prop: (order, value)}."""
    rules, order = {}, 0
    for style in (e for e in root.iter() if _local(e.tag) == "style"):
        text = re.sub(r"/\*.*?\*/", "", style.text or "", flags=re.S)
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
            for decl in body.split(";"):
                prop, sep, value = decl.partition(":")
                if not sep:
                    continue
                order += 1
                entry = (order, value.split("!")[0].strip())
                for sel in (s.strip() for s in selectors.split(",")):
                    if re.fullmatch(r"\*|\.?[A-Za-z_][\w-]*", sel):
                        rules.setdefault(sel, {})[prop.strip().lower()] = entry
    return rules


def _css_value(el, prop, css):
    """Value from the stylesheet: class rules, then element rules, then *; last declared wins within a level."""
    if not css:
        return ""
    for selectors in (["." + c for c in (el.get("class") or "").split()], [_local(el.tag)], ["*"]):
        hits = [css[s][prop] for s in selectors if prop in css.get(s, {})]
        if hits:
            return max(hits)[1]
    return ""


def _style_prop(el, prop, css=None):
    m = re.search(rf"(?:^|;)\s*{prop}\s*:\s*([^;]+)", el.get("style") or "")
    return (m.group(1) if m else el.get(prop) or _css_value(el, prop, css)).strip().lower()


def _invisible(el, css=None):
    for prop in ("opacity", "fill-opacity"):
        try:
            if _style_prop(el, prop, css) and float(_style_prop(el, prop, css)) == 0:
                return True
        except ValueError:
            pass
    return False


def _paints(el, css=None):
    """True if the element puts visible paint down (fill or stroke, not fully transparent)."""
    if _invisible(el, css):
        return False
    unpainted = ("none", "transparent")
    if _fill(el, css) not in unpainted:
        return True
    return _style_prop(el, "stroke", css) not in ("",) + unpainted


def _svg_transparent(data: bytes) -> bool:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return False
    vb = root.get("viewBox")
    if vb:
        parts = [float(p) for p in re.split(r"[ ,]+", vb.strip())]
        vw, vh = parts[2], parts[3]
    else:
        vw, vh = _num(root.get("width"), 0), _num(root.get("height"), 0)
    css = _css_rules(root)
    first = next((e for e in _drawn(root) if _paints(e, css)), None)
    if first is None or _local(first.tag) != "rect" or not vw or not vh:
        return True
    w, h = _num(first.get("width"), vw), _num(first.get("height"), vh)
    if not w or not h:
        return True
    return not (w * h >= 0.99 * vw * vh)


def _png_chunks(data):
    pos = 8
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        yield ctype, data[pos + 8:pos + 8 + length]
        pos += 12 + length


def _png_transparent(data: bytes) -> bool:
    chunks = list(_png_chunks(data))
    ihdr = next((d for t, d in chunks if t == b"IHDR"), None)
    if ihdr is None:
        return False
    width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", ihdr)
    if interlace:
        return False
    if ctype in (0, 2, 3):
        trns = next((d for t, d in chunks if t == b"tRNS"), None)
        return bool(trns) and (ctype != 3 or any(b < 255 for b in trns))
    if ctype not in (4, 6) or depth not in (8, 16):
        return False
    bpp = (2 if ctype == 4 else 4) * depth // 8
    alpha_at = bpp - depth // 8  # alpha is the last sample
    raw = zlib.decompress(b"".join(d for t, d in chunks if t == b"IDAT"))
    stride = width * bpp
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ft, line = raw[pos], bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1:
                line[i] = (line[i] + a) & 255
            elif ft == 2:
                line[i] = (line[i] + b) & 255
            elif ft == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 255
        for x in range(width):
            if line[x * bpp + alpha_at] != 255:
                return True
        prev = line
    return False


def _webp_transparent(data: bytes) -> bool:
    """True only for VP8X with the alpha flag, or VP8L with its alpha-hint bit."""
    kind = data[12:16]
    if kind == b"VP8X":
        return bool(data[20] & 0x10)
    if kind == b"VP8L":
        if data[20] != 0x2F:
            return False
        bits = struct.unpack("<I", data[21:25])[0]
        return bool(bits >> 28 & 1)
    return False


def _gif_transparent(data: bytes) -> bool:
    """True only when a Graphic Control Extension has its transparency flag set."""
    n = len(data)
    if n < 13:
        return False
    flags = data[10]
    pos = 13
    if flags & 0x80:
        pos += 3 * (2 << (flags & 7))

    def skip_sub_blocks(i):
        while i < n:
            size = data[i]
            i += 1
            if size == 0:
                return i
            i += size
        return n

    while pos < n:
        block = data[pos]
        if block == 0x21:  # extension
            if pos + 2 >= n:
                return False
            if data[pos + 1] == 0xF9:
                if pos + 3 < n and data[pos + 2] >= 4 and data[pos + 3] & 1:
                    return True
            pos = skip_sub_blocks(pos + 2)
        elif block == 0x2C:  # image descriptor
            if pos + 10 > n:
                return False
            lflags = data[pos + 9]
            pos += 10
            if lflags & 0x80:
                pos += 3 * (2 << (lflags & 7))
            pos = skip_sub_blocks(pos + 1)  # LZW minimum code size, then data
        else:
            return False
    return False


def is_transparent(path: Path) -> bool:
    data = Path(path).read_bytes()
    fmt = sniff_format(data)
    if fmt == "svg":
        return _svg_transparent(data)
    if fmt == "webp":
        try:
            return _webp_transparent(data)
        except (struct.error, IndexError):
            return False
    if fmt == "gif":
        return _gif_transparent(data)
    if fmt == "png":
        try:
            return _png_transparent(data)
        except (zlib.error, struct.error, IndexError):
            return False
    return False


def _unsafe_svg(data: bytes):
    text = data.decode("utf-8", "ignore")
    if re.search(r"<\s*script", text, re.I):
        return "script element"
    if re.search(r"\son[a-z]+\s*=", text, re.I):
        return "event handler attribute"
    if re.search(r"(?:xlink:)?href\s*=\s*[\"']\s*(?!#)[^\"']", text, re.I):
        return "non-local href"
    return None


# ---------------------------------------------------------------- helpers

def _is_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _load(path, errs, label):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errs.append(f"{label}: cannot read ({exc})")
        return None


# ---------------------------------------------------------------- entity

def _check_asset(entity_dir, ent, a, errs):
    eid, domains = ent.get("id"), ent.get("official_domains") or []
    name = a.get("file", "")
    pre = f"{eid}: asset {name!r}"
    in_previous = isinstance(name, str) and name.startswith(PREVIOUS)
    base = name[len(PREVIOUS):] if in_previous else name
    pattern = re.compile(
        rf"^{re.escape(str(eid))}-({'|'.join(LOCKUPS)})-({'|'.join(BACKGROUNDS)})(-[a-z0-9]+)*\.({'|'.join(EXTENSIONS)})$")
    if not pattern.match(base):
        errs.append(f"{pre}: bad file name, expected <id>-<lockup>-<background>[-<modifier>].<ext>")
    superseded = a.get("superseded", False)
    if not isinstance(superseded, bool):
        errs.append(f"{pre}: superseded must be a boolean")
    elif superseded != in_previous:
        errs.append(f"{pre}: superseded assets must be recorded as previous/<name>, and only those")
    lang = a.get("language")
    if lang is not None and not (isinstance(lang, str) and re.fullmatch(r"[a-z]{2}", lang)):
        errs.append(f"{pre}: language must be an ISO 639-1 code or null")
    if a.get("valid_until") is not None and not _is_date(a.get("valid_until")):
        errs.append(f"{pre}: valid_until must be an ISO date or null")
    if a.get("lockup") not in LOCKUPS:
        errs.append(f"{pre}: invalid lockup")
    if a.get("background") not in BACKGROUNDS:
        errs.append(f"{pre}: invalid background")
    if a.get("color_mode") not in COLOR_MODES:
        errs.append(f"{pre}: invalid color_mode")
    if not _is_date(a.get("retrieved")):
        errs.append(f"{pre}: retrieved must be an ISO date")
    tier = a.get("source_tier")
    if tier not in (1, 2, "internal"):
        errs.append(f"{pre}: invalid source_tier")
    elif tier != "internal":
        url = a.get("source_url") or ""
        if _is_banned(url):
            errs.append(f"{pre}: banned host in source_url")
        elif not host_is_official(url, domains):
            errs.append(f"{pre}: source_url host is not an official domain")
    path = entity_dir / "logos" / name
    if not path.is_file():
        errs.append(f"{pre}: file missing")
        return
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != a.get("sha256"):
        errs.append(f"{pre}: sha256 mismatch")
    fmt = sniff_format(data)
    ext = EXTENSIONS.get(path.suffix.lower().lstrip("."))
    if fmt is None or fmt != ext:
        errs.append(f"{pre}: format mismatch (extension {ext}, content {fmt})")
        return
    if fmt == "svg":
        why = _unsafe_svg(data)
        if why:
            errs.append(f"{pre}: unsafe svg ({why})")
    flag = is_transparent(path)
    # A GIF's transparency flag does not prove any pixel is transparent, so a set flag allows either value.
    gif_flag_ok = fmt == "gif" and flag and isinstance(a.get("transparent"), bool)
    if a.get("transparent") != flag and not gif_flag_ok:
        errs.append(f"{pre}: transparent field does not match file")


def validate_entity(entity_dir: Path, allow_pending: bool = False) -> list:
    entity_dir = Path(entity_dir)
    errs = []
    ent = _load(entity_dir / "entity.json", errs, f"{entity_dir.name}/entity.json")
    if ent is None:
        return errs
    eid = ent.get("id")
    for f in ENTITY_FIELDS:
        if f not in ent:
            errs.append(f"{eid}: missing field {f}")
    if eid != entity_dir.name:
        errs.append(f"{eid}: id does not match folder name {entity_dir.name}")
    if ent.get("group") not in GROUPS:
        errs.append(f"{eid}: invalid group")
    if not set(ent.get("types") or []) <= TYPES:
        errs.append(f"{eid}: invalid types")
    contact = ent.get("contact")
    if "contact" in ent and not (
            isinstance(contact, dict) and set(contact) == CONTACT_KEYS
            and all(v is None or isinstance(v, str) for v in contact.values())):
        errs.append(f"{eid}: contact must have exactly logo_permission_url, email, notes (string or null)")
    status, assets = ent.get("status"), ent.get("assets") or []
    gaps = ent.get("gaps") or []
    if status not in STATUSES:
        errs.append(f"{eid}: invalid status {status!r}")
    for g in gaps:
        if not (isinstance(g, dict) and g.get("need") and g.get("reason")):
            errs.append(f"{eid}: each gap needs need and reason")

    if status == "pending":
        if not allow_pending:
            errs.append(f"{eid}: status pending is not allowed")
        return errs

    for a in assets:
        _check_asset(entity_dir, ent, a, errs)
    recorded = {a.get("file") for a in assets}
    logos = entity_dir / "logos"
    found = []
    for folder, prefix in ((logos, ""), (logos / "previous", PREVIOUS)):
        found += [(f, prefix + f.name) for f in sorted(folder.iterdir()) if f.is_file()] if folder.is_dir() else []
    for f, rel in found:
        if rel not in recorded and not f.name.startswith("."):
            errs.append(f"{eid}: unrecorded logo file {rel}")

    if status == "complete":
        current = [a for a in assets if not a.get("superseded")]
        has = lambda bg: any(a.get("background") == bg for a in current)  # noqa: E731
        if not (has("light") and has("dark") and any(a.get("transparent") for a in current)):
            errs.append(f"{eid}: complete requires a light, a dark and a transparent asset")
    elif status == "partial":
        if not assets or not gaps:
            errs.append(f"{eid}: partial requires at least one asset and non-empty gaps")
    elif status in ("restricted", "not-found"):
        if assets or not gaps:
            errs.append(f"{eid}: {status} requires no assets and non-empty gaps")
    elif status == "not-applicable":
        if assets or not ent.get("notes"):
            errs.append(f"{eid}: not-applicable requires no assets and non-empty notes")

    style = entity_dir / "house-style" / "style.json"
    if style.is_file():
        errs += _validate_style(style, eid)
    elif status != "not-applicable":
        errs.append(f"{eid}: missing house-style/style.json")
    return errs


# ---------------------------------------------------------------- style

def _check_source(src, errs, pre, previous):
    if not isinstance(src, dict):
        errs.append(f"{pre}: source must be an object")
        return
    if not src.get("url"):
        errs.append(f"{pre}: source needs url")
    if src.get("kind") not in SOURCE_KINDS:
        errs.append(f"{pre}: invalid source kind")
    if not _is_date(src.get("retrieved")):
        errs.append(f"{pre}: source retrieved must be an ISO date")
    if previous:
        if not _is_date(src.get("superseded_on")):
            errs.append(f"{pre}: previous source needs superseded_on (ISO date)")
        if not src.get("change_summary"):
            errs.append(f"{pre}: previous source needs change_summary")


def _validate_style(path, eid):
    errs = []
    st = _load(path, errs, f"{eid}/style.json")
    if st is None:
        return errs
    if st.get("id") != eid:
        errs.append(f"{eid}: style id does not match entity id")
    if st.get("status") not in ("documented", "observed", "none"):
        errs.append(f"{eid}: invalid style status")
    current = st.get("current_sources") or []
    if st.get("status") in ("documented", "observed") and not current:
        errs.append(f"{eid}: style {st.get('status')} requires current_sources")
    for s in current:
        _check_source(s, errs, f"{eid}: current_sources", False)
    for s in st.get("previous_sources") or []:
        _check_source(s, errs, f"{eid}: previous_sources", True)
    if not _is_date(st.get("last_checked")):
        errs.append(f"{eid}: last_checked must be an ISO date")
    for c in st.get("colors") or []:
        if not HEX_RE.match(str(c.get("hex"))):
            errs.append(f"{eid}: invalid hex {c.get('hex')!r}")
        if c.get("evidence") not in ("guideline", "observed"):
            errs.append(f"{eid}: colour {c.get('name')!r} needs evidence guideline or observed")
    for t in st.get("typography") or []:
        if t.get("evidence") not in ("guideline", "observed"):
            errs.append(f"{eid}: typography {t.get('family')!r} needs evidence guideline or observed")
    return errs


# ---------------------------------------------------------------- repo

def validate_repo(root: Path, allow_pending: bool = False) -> list:
    root = Path(root)
    errs, entities = [], []
    for ef in sorted((root / "stakeholders").rglob("entity.json")):
        errs += validate_entity(ef.parent, allow_pending)
        try:
            entities.append(json.loads(ef.read_text(encoding="utf-8")))
        except ValueError:
            pass
    for state, iso in STATE_ISO2.items():
        for role in ("caa", "ansp"):
            if not any(role in (e.get("types") or []) and
                       (e.get("country") == state or iso in (e.get("also_countries") or []))
                       for e in entities):
                errs.append(f"coverage: {state} has no {role} entity")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--allow-pending", action="store_true")
    args = ap.parse_args(argv)
    errs = validate_repo(Path(__file__).resolve().parent.parent, args.allow_pending)
    for e in errs:
        print(e)
    print(f"{len(errs)} error(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
