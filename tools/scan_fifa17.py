from __future__ import annotations

import argparse
import re
from pathlib import Path

ASCII_RE = re.compile(rb"[ -~]{6,}")
UTF16_RE = re.compile(rb"(?:[ -~]\x00){6,}")
HOST_RE = re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+(?:ea\.com|easports\.com|origin\.com)\b")
URL_RE = re.compile(r"(?i)https?://[^\s\x00\"'<>]{4,}")
DEFAULT_TERMS = (
    "fut",
    "ultimate",
    "blaze",
    "redirector",
    "gosredirector",
    "nucleus",
    "lsx",
    "pow",
    "easw",
    "ea.com",
    "easports",
    "origin",
    "hostname",
    "target_port",
    "base_url",
)


def strings_from_binary(data: bytes):
    for match in ASCII_RE.finditer(data):
        yield match.start(), match.group().decode("ascii", errors="ignore")
    for match in UTF16_RE.finditer(data):
        raw = match.group()
        yield match.start(), raw.decode("utf-16le", errors="ignore")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract FIFA 17 networking-related strings from FIFA17.exe")
    parser.add_argument("exe", help="path to FIFA17.exe")
    parser.add_argument("-o", "--output", default="logs/fifa17_string_hits.txt")
    parser.add_argument("--term", action="append", dest="terms", help="additional case-insensitive filter term")
    args = parser.parse_args()

    exe = Path(args.exe)
    if not exe.is_file():
        raise SystemExit(f"file not found: {exe}")

    print(f"Reading {exe} ...")
    data = exe.read_bytes()
    terms = tuple(t.lower() for t in DEFAULT_TERMS + tuple(args.terms or []))

    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    all_strings: list[str] = []

    for offset, text in strings_from_binary(data):
        clean = text.strip()
        if not clean:
            continue
        all_strings.append(clean)
        lowered = clean.lower()
        if any(term in lowered for term in terms):
            key = clean.casefold()
            if key not in seen:
                seen.add(key)
                hits.append((offset, clean))

    joined = "\n".join(all_strings)
    hosts = sorted(set(HOST_RE.findall(joined)), key=str.lower)
    urls = sorted(set(URL_RE.findall(joined)), key=str.lower)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", errors="replace") as fh:
        fh.write(f"source={exe}\n")
        fh.write(f"size={len(data)}\n")
        fh.write(f"filtered_hits={len(hits)}\n\n")
        fh.write("=== HOSTNAMES ===\n")
        for host in hosts:
            fh.write(host + "\n")
        fh.write("\n=== URLS ===\n")
        for url in urls:
            fh.write(url + "\n")
        fh.write("\n=== FILTERED STRINGS ===\n")
        for offset, text in sorted(hits):
            fh.write(f"0x{offset:08X}  {text}\n")

    print(f"Found {len(hosts)} EA/Origin hostnames, {len(urls)} URLs, {len(hits)} filtered strings")
    print(f"Saved: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
