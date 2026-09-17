from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from pathlib import Path

from .db import Database
from .http_server import FutHTTPServer
from .probe import start_probe_servers

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="FIFA 17 Local FUT foundation server")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    parser.add_argument("--no-probes", action="store_true", help="start only the HTTP service")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)

    bind_host = str(config.get("bind_host", "127.0.0.1"))
    http_port = int(config.get("http_port", 8099))
    db_path = Path(config.get("database_path", "data/fut17.sqlite3"))
    if not db_path.is_absolute():
        db_path = ROOT / db_path

    capture_dir = Path(config.get("capture_dir", "logs/captures"))
    if not capture_dir.is_absolute():
        capture_dir = ROOT / capture_dir

    db = Database(
        db_path,
        identity=dict(config.get("identity", {})),
        starting_coins=int(config.get("starting_coins", 0)),
        starting_points=int(config.get("starting_points", 0)),
    )

    http_server = FutHTTPServer((bind_host, http_port), db)
    http_thread = threading.Thread(target=http_server.serve_forever, name="fut-http", daemon=True)
    http_thread.start()

    print("=" * 68)
    print(" FIFA 17 Local FUT - foundation server")
    print("=" * 68)
    print(f"[HTTP]  http://{bind_host}:{http_port}/health")
    print(f"[DB]    {db_path}")

    probes = []
    if not args.no_probes:
        ports = [int(p) for p in config.get("probe_ports", []) if int(p) != http_port]
        probes = start_probe_servers(bind_host, ports, capture_dir)
        print(f"[CAP]   {capture_dir}")

    stop = threading.Event()

    def request_stop(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    print("[READY] Press Ctrl+C to stop.")
    try:
        while not stop.is_set():
            time.sleep(0.25)
    finally:
        print("\n[STOP] shutting down")
        http_server.shutdown()
        http_server.server_close()
        for probe in probes:
            probe.shutdown()
            probe.server_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
