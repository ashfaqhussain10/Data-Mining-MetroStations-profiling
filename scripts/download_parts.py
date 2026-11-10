"""Download selected parts of the Dubai Metro Ridership dataset from data.dubai.

Usage:
    python scripts/download_parts.py --parts 2
    python scripts/download_parts.py --parts 2 3 4 --out data/raw

Files are fetched one at a time with a pause between them. Each download link
lasts about 10 minutes, so a fresh link is requested just before each file.
This uses the address the portal's Download window calls, which is not a
published API and may change. Downloading by hand is the fallback.
"""
import argparse
import gzip
import hashlib
import http.cookiejar
import json
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATASET_ID = 466403
PAGE_URL = f"https://data.dubai/en/l/{DATASET_ID}"
LIST_URL = "https://data.dubai/o/dda/data-services/dataset-download"
PART_PREFIX = "metro_ridership_2026-07-21_18-21-58"
PAGE_SIZE = 30
HEADERS = {"User-Agent": "Mozilla/5.0"}
CHUNK = 1024 * 1024


def open_session():
    """Load the dataset page to get the session cookie and page token."""
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request = urllib.request.Request(PAGE_URL, headers=HEADERS)
    html = opener.open(request, timeout=60).read().decode("utf8", "ignore")
    match = re.search(r"authToken\s*=\s*'([^']+)'", html)
    if not match:
        sys.exit("Could not find the page token. The portal may have changed.")
    return opener, match.group(1)


def find_csv(opener, token, part):
    """Return the CSV entry for a part, with a fresh download link."""
    page = (part - 1) // PAGE_SIZE + 1
    url = f"{LIST_URL}?datasetId={DATASET_ID}&page={page}&pageSize={PAGE_SIZE}&sortDir=desc"
    headers = {**HEADERS, "x-csrf-token": token, "Accept": "application/json"}
    body = opener.open(urllib.request.Request(url, headers=headers), timeout=60).read()
    folders = json.loads(body)["data"]["metadata"]
    folder_name = f"{PART_PREFIX}_{part:04d}"
    for folder in folders:
        if folder["file_folder"] == folder_name:
            for entry in folder["files"]:
                if entry["file_extension"] == "csv":
                    return entry
    sys.exit(f"{folder_name} not found on page {page}.")


def fetch(entry, temp_path):
    """Stream the file to disk and return the number of bytes received."""
    request = urllib.request.Request(entry["file_url"], headers=HEADERS)
    received = 0
    with urllib.request.urlopen(request, timeout=120) as response, open(temp_path, "wb") as out:
        while chunk := response.read(CHUNK):
            out.write(chunk)
            received += len(chunk)
            if received % (32 * CHUNK) < CHUNK:
                print(f"  {received / 1e6:.0f} MB", flush=True)
    return received


def to_plain_csv(temp_path, final_path):
    """Save as plain CSV, decompressing only if the bytes really are gzip."""
    with open(temp_path, "rb") as source:
        compressed = source.read(2) == b"\x1f\x8b"
    if compressed:
        with gzip.open(temp_path, "rb") as source, open(final_path, "wb") as out:
            shutil.copyfileobj(source, out, CHUNK)
        temp_path.unlink()
    else:
        temp_path.replace(final_path)
    return compressed


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(opener, token, part, out_dir):
    final_path = out_dir / f"{PART_PREFIX}_{part:04d}.csv"
    entry = find_csv(opener, token, part)
    expected = entry["file_size"]
    if final_path.exists() and final_path.stat().st_size == expected:
        print(f"{final_path.name}: already complete, skipping")
        return

    temp_path = final_path.with_suffix(".partial")
    print(f"{final_path.name}: downloading, listed size {expected:,} bytes", flush=True)
    received = fetch(entry, temp_path)
    compressed = to_plain_csv(temp_path, final_path)
    size = final_path.stat().st_size
    matches = expected in (size, received)
    record = {
        "file": final_path.name, "listed_bytes": expected, "received_bytes": received,
        "saved_bytes": size, "arrived_gzipped": compressed, "size_matches": matches,
        "sha256": sha256(final_path),
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(out_dir / "download_log.jsonl", "a", encoding="utf8") as log:
        log.write(json.dumps(record) + "\n")
    print(json.dumps(record, indent=2))
    if not matches:
        sys.exit("Size does not match the listing. Check this file before using it.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--parts", type=int, nargs="+", required=True, help="part numbers, e.g. 2 3 4")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "data" / "raw")
    parser.add_argument("--pause", type=float, default=5, help="seconds between files")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    opener, token = open_session()
    for position, part in enumerate(args.parts):
        if position:
            time.sleep(args.pause)
        download(opener, token, part, args.out)


if __name__ == "__main__":
    main()
