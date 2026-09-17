from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

KNOWN_RVA = 0x61361B0
FULL_PATTERN = "48 89 5c 24 08 44 88 44 24 18 55 56 57 48 83 ec 30"
PARTIAL_PATTERNS = {
    "prefix8": "48 89 5c 24 08 44 88 44",
    "tail7": "55 56 57 48 83 ec 30",
    "prologue_generic": "48 89 5c 24 08 ?? ?? ?? ?? ?? 55 56 57 48 83 ec 30",
}

AGENT = r"""
'use strict';

const KNOWN_RVA = 0x61361b0;
const FULL_PATTERN = '48 89 5c 24 08 44 88 44 24 18 55 56 57 48 83 ec 30';
const PARTIALS = {
  prefix8: '48 89 5c 24 08 44 88 44',
  tail7: '55 56 57 48 83 ec 30',
  prologue_generic: '48 89 5c 24 08 ?? ?? ?? ?? ?? 55 56 57 48 83 ec 30'
};

function emit(kind, data) {
  send(Object.assign({ kind: kind, time_ms: Date.now() }, data || {}));
}

function rvaOf(module, p) {
  try {
    if (p.compare(module.base) >= 0 && p.compare(module.base.add(module.size)) < 0)
      return '0x' + p.sub(module.base).toString(16);
  } catch (_) {}
  return null;
}

function scanModule(module, pattern, protections) {
  const hits = [];
  for (const prot of protections) {
    let ranges = [];
    try { ranges = module.enumerateRanges(prot); } catch (_) { continue; }
    for (const range of ranges) {
      try {
        const found = Memory.scanSync(range.base, range.size, pattern);
        for (const hit of found) hits.push({ address: hit.address.toString(), rva: rvaOf(module, hit.address), prot: prot });
      } catch (_) {}
    }
  }
  const seen = new Set();
  return hits.filter(h => {
    if (seen.has(h.address)) return false;
    seen.add(h.address);
    return true;
  });
}

const fifa = Process.getModuleByName('FIFA17.exe');
emit('MODULE', {
  name: fifa.name,
  path: fifa.path,
  base: fifa.base.toString(),
  size: fifa.size,
  known_rva_address: fifa.base.add(KNOWN_RVA).toString()
});

try {
  const p = fifa.base.add(KNOWN_RVA);
  const before = p.sub(32).readByteArray(96);
  emit('KNOWN-RVA-BYTES', {
    rva: '0x' + KNOWN_RVA.toString(16),
    bytes: Array.from(new Uint8Array(before)).map(b => b.toString(16).padStart(2, '0')).join(' ')
  });
} catch (e) {
  emit('KNOWN-RVA-READ-ERROR', { error: String(e) });
}

const protections = ['r-x', 'r--', 'rw-', 'rwx'];
emit('SCAN', { name: 'full17', pattern: FULL_PATTERN, hits: scanModule(fifa, FULL_PATTERN, protections) });
for (const name in PARTIALS) {
  emit('SCAN', { name: name, pattern: PARTIALS[name], hits: scanModule(fifa, PARTIALS[name], protections) });
}

emit('DONE', {});
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def static_scan(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    full = bytes.fromhex(FULL_PATTERN)
    prefix = bytes.fromhex(PARTIAL_PATTERNS["prefix8"])
    tail = bytes.fromhex(PARTIAL_PATTERNS["tail7"])

    def all_hits(needle: bytes, limit: int = 32) -> list[int]:
        out: list[int] = []
        pos = 0
        while len(out) < limit:
            idx = data.find(needle, pos)
            if idx < 0:
                break
            out.append(idx)
            pos = idx + 1
        return out

    return {
        "size": len(data),
        "sha256": sha256_file(path),
        "static_full17_offsets": [hex(x) for x in all_hits(full)],
        "static_prefix8_offsets": [hex(x) for x in all_hits(prefix)],
        "static_tail7_offsets": [hex(x) for x in all_hits(tail)],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fingerprint the active FIFA17.exe and locate the known ProtoSSL verifier pattern without modifying the process.")
    ap.add_argument("--exe", default=r"C:\Users\Administrator\Desktop\FIFA 17\FIFA17.exe")
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--log", default="logs/protossl_build_diagnostic.jsonl")
    args = ap.parse_args()

    exe = Path(args.exe)
    if not exe.exists():
        raise SystemExit(f"FIFA17.exe not found: {exe}")

    info = static_scan(exe)
    print("[DIAG] executable fingerprint:")
    print(json.dumps(info, indent=2))

    try:
        import frida
    except ImportError:
        raise SystemExit("frida is required: python -m pip install frida frida-tools")

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(obj: dict[str, object]) -> None:
        row = {"outer_time": now(), **obj}
        print(json.dumps(row, ensure_ascii=False), flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    record({"kind": "FILE-FINGERPRINT", "exe": str(exe), **info})

    device = frida.get_local_device()
    deadline = time.time() + args.seconds
    pid = None
    print("[DIAG] waiting for FIFA17.exe ...")
    while time.time() < deadline:
        matches = [p for p in device.enumerate_processes() if p.name.lower() == "fifa17.exe"]
        if matches:
            pid = matches[0].pid
            break
        time.sleep(0.25)

    if pid is None:
        raise SystemExit("FIFA17.exe was not found before timeout")

    print(f"[DIAG] attaching to FIFA17.exe pid={pid}")
    session = device.attach(pid)
    script = session.create_script(AGENT)
    done = False

    def on_message(message, data):
        nonlocal done
        if message.get("type") == "send":
            payload = message.get("payload")
            if isinstance(payload, dict):
                record(payload)
                if payload.get("kind") == "DONE":
                    done = True
            else:
                record({"kind": "frida-send", "payload": payload})
        else:
            record({"kind": "frida-message", "message": message})
            if message.get("type") == "error":
                done = True

    script.on("message", on_message)
    script.load()

    wait_deadline = time.time() + 15
    while not done and time.time() < wait_deadline:
        time.sleep(0.1)

    try:
        script.unload()
    except Exception:
        pass
    try:
        session.detach()
    except Exception:
        pass

    print(f"[DIAG] saved -> {log_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
