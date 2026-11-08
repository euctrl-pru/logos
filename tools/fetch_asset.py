"""Fetch logo files from official sources only. Downloaded files are untrusted data."""
import argparse
import datetime
import hashlib
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate import _is_banned, host_is_official, is_transparent, sniff_format  # noqa: E402

MAX_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = 30
USER_AGENT = "logo-collector/1.0"
REDIRECTS = {301, 302, 303, 307, 308}


class FetchRefused(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _default_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def _check_url(url, domains):
    if urlparse(url).scheme not in ("http", "https"):
        raise FetchRefused(f"unsupported scheme: {url}")
    if _is_banned(url):
        raise FetchRefused(f"banned host: {url}")
    if not host_is_official(url, domains):
        raise FetchRefused(f"not an official host: {url}")


def _read_limited(resp):
    chunks, total = [], 0
    while True:
        chunk = resp.read(65536)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > MAX_BYTES:
            raise FetchRefused(f"body exceeds {MAX_BYTES} bytes")
        chunks.append(chunk)


def _prepare_dest(dest_dir):
    dest_dir = Path(dest_dir)
    if dest_dir.exists() and (not dest_dir.is_dir() or any(dest_dir.iterdir())):
        raise FetchRefused(f"destination must be a new empty directory: {dest_dir}")
    return dest_dir


def fetch(url, dest_dir, domains, opener=None):
    dest_dir = _prepare_dest(dest_dir)
    _check_url(url, domains)
    opener = opener or _default_opener()
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        req = urllib.request.Request(current, headers={"User-Agent": USER_AGENT})
        try:
            resp = opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in REDIRECTS and e.headers.get("Location"):
                nxt = urljoin(current, e.headers["Location"])
                e.close()
                _check_url(nxt, domains)
                current = nxt
                continue
            code = e.code
            e.close()
            raise FetchRefused(f"HTTP {code} for {current}")
        except (urllib.error.URLError, OSError) as e:
            raise FetchRefused(f"request failed for {current}: {e}")
        with resp:
            if resp.status != 200:
                raise FetchRefused(f"HTTP {resp.status} for {current}")
            data = _read_limited(resp)
        break
    else:
        raise FetchRefused("too many redirects")
    fmt = sniff_format(data)
    if fmt is None:
        raise FetchRefused(f"body is not a recognised logo format: {current}")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", PurePosixPath(urlparse(current).path).stem) or "asset"
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{stem.lstrip('.') or 'asset'}.{fmt}"
    with open(out, "xb") as f:
        f.write(data)
    return out


def make_asset_record(path, source_url, page_url, tier, lockup, background, color_mode):
    if tier not in (1, 2, "internal") or tier is True:
        raise ValueError(f"source tier must be 1, 2 or 'internal': {tier!r}")
    path = Path(path)
    return {
        "file": path.name,
        "lockup": lockup,
        "background": background,
        "color_mode": color_mode,
        "transparent": is_transparent(path),
        "source_url": source_url,
        "page_url": page_url,
        "source_tier": tier,
        "retrieved": datetime.date.today().isoformat(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def safe_extract_zip(zip_path, dest_dir):
    dest_dir = _prepare_dest(dest_dir)
    out = []
    with zipfile.ZipFile(zip_path) as z:
        plan, total = [], 0
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in parts or not parts:
                raise FetchRefused(f"unsafe zip member: {info.filename}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise FetchRefused(f"symlink zip member: {info.filename}")
            total += info.file_size
            if total > MAX_BYTES:
                raise FetchRefused("zip contents exceed size limit")
            plan.append((info, dest_dir.joinpath(*parts)))
        root = dest_dir.resolve()
        for _, target in plan:
            if not target.resolve().is_relative_to(root):
                raise FetchRefused(f"unsafe zip member: {target}")
        for info, target in plan:
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "xb") as dst:
                data = src.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise FetchRefused("zip member exceeds size limit")
                dst.write(data)
            out.append(target)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch a logo from an official source.")
    ap.add_argument("url")
    ap.add_argument("dest")
    ap.add_argument("--domains", required=True, help="comma-separated official domains")
    args = ap.parse_args(argv)
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    try:
        print(fetch(args.url, Path(args.dest), domains))
    except FetchRefused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
