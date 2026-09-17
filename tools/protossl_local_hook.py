from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

# This tool is intentionally narrow: it only makes FIFA17's DirtySDK ProtoSSL
# certificate verifier return success while this process-memory hook is loaded.
# It does not modify EA App/Origin ownership, entitlement, readiness, auth-code,
# age checks, or any on-disk game files.

AGENT = r"""
'use strict';

const fifa = Process.getModuleByName('FIFA17.exe');
const PROTOSSL_VERIFY_PATTERN =
    '48 89 5c 24 08 44 88 44 24 18 55 56 57 48 83 ec 30';

function emit(kind, data) {
    send(Object.assign({
        kind: kind,
        time_ms: Date.now(),
        tid: Process.getCurrentThreadId()
    }, data || {}));
}

function rvaOf(p) {
    try {
        if (p.compare(fifa.base) >= 0 && p.compare(fifa.base.add(fifa.size)) < 0) {
            return '0x' + p.sub(fifa.base).toString(16);
        }
    } catch (_) {}
    return null;
}

function scanModule(pattern) {
    const hits = [];
    const ranges = fifa.enumerateRanges('r-x');
    for (const range of ranges) {
        try {
            const found = Memory.scanSync(range.base, range.size, pattern);
            for (const hit of found) hits.push(hit.address);
        } catch (_) {}
    }
    return hits;
}

const hits = scanModule(PROTOSSL_VERIFY_PATTERN);
if (hits.length !== 1) {
    emit('PROTOSSL-SIGNATURE-ERROR', {
        hits: hits.length,
        hit_rvas: hits.map(rvaOf)
    });
    throw new Error('ProtoSSL verifier signature expected exactly one hit; got ' + hits.length);
}

const verifier = hits[0];
let callCount = 0;
let replacement = new NativeCallback(function () {
    callCount++;
    if (callCount <= 16) {
        emit('PROTOSSL-CERTIFICATE-ACCEPTED-LOCAL', {
            call: callCount,
            verifier_rva: rvaOf(verifier)
        });
    }
    return 0;
}, 'int', []);

Interceptor.replace(verifier, replacement);

emit('PROTOSSL-HOOK-READY', {
    module_base: fifa.base.toString(),
    module_size: fifa.size,
    verifier: verifier.toString(),
    verifier_rva: rvaOf(verifier),
    scope: 'redirector certificate verification only'
});
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Attach a scoped local ProtoSSL certificate hook to FIFA17.exe"
    )
    parser.add_argument("--pid", type=int, help="attach to a specific FIFA17.exe PID")
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=180,
        help="how long to wait for FIFA17.exe when --pid is omitted",
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=900,
        help="maximum time to keep the hook installed",
    )
    parser.add_argument(
        "--log",
        default="logs/protossl_local_hook.jsonl",
        help="JSONL diagnostic log path",
    )
    args = parser.parse_args()

    try:
        import frida
    except ImportError:
        raise SystemExit(
            "Frida is required. Install it with:\n"
            "  python -m pip install frida frida-tools"
        )

    device = frida.get_local_device()
    pid = args.pid

    if pid is None:
        deadline = time.time() + max(1, args.wait_seconds)
        print("[PROTOSSL] waiting for FIFA17.exe ...", flush=True)
        while time.time() < deadline:
            matches = [
                p for p in device.enumerate_processes()
                if p.name.lower() == "fifa17.exe"
            ]
            if matches:
                pid = matches[0].pid
                break
            time.sleep(0.25)

    if pid is None:
        raise SystemExit("FIFA17.exe was not found before the wait timeout")

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(obj: dict) -> None:
        row = {"outer_time": utc_now(), **obj}
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=False), flush=True)

    print(f"[PROTOSSL] attaching to FIFA17.exe pid={pid}", flush=True)
    session = device.attach(pid)
    script = session.create_script(AGENT)

    ready = {"value": False}

    def on_message(message, data):
        if message.get("type") == "send":
            payload = message.get("payload")
            if isinstance(payload, dict):
                if payload.get("kind") == "PROTOSSL-HOOK-READY":
                    ready["value"] = True
                record(payload)
            else:
                record({"kind": "frida-send", "payload": payload})
        else:
            record({"kind": "frida-message", "message": message})

    script.on("message", on_message)
    script.load()

    # Give the injected agent a moment to resolve its signature and report.
    ready_deadline = time.time() + 5.0
    while not ready["value"] and time.time() < ready_deadline:
        time.sleep(0.05)

    if not ready["value"]:
        try:
            script.unload()
        finally:
            session.detach()
        raise SystemExit("ProtoSSL hook did not become ready; inspect the log above")

    print(
        "[PROTOSSL] READY - keep this window open, then retry FIFA's EA-server connection.",
        flush=True,
    )
    print(
        "[PROTOSSL] This hook disappears when this process exits or FIFA closes.",
        flush=True,
    )

    deadline = time.time() + max(1, args.seconds)
    try:
        while time.time() < deadline:
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            script.unload()
        except Exception:
            pass
        try:
            session.detach()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
