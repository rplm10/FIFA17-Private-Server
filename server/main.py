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
from .redirector import start_redirector_server

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_root_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description="FIFA 17 Local FUT foundation server")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    parser.add_argument("--no-probes", action="store_true", help="start only HTTP/redirector services")
    parser.add_argument("--no-redirector", action="store_true", help="do not start the HTTPS redirector")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)

    bind_host = str(config.get("bind_host", "127.0.0.1"))
    http_port = int(config.get("http_port", 8099))
    db_path = resolve_root_path(str(config.get("database_path", "data/fut17.sqlite3")))
    capture_dir = resolve_root_path(str(config.get("capture_dir", "logs/captures")))

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

    redirector_server = None
    redirector_cfg = dict(config.get("redirector", {}))
    redirector_enabled = bool(redirector_cfg.get("enabled", False)) and not args.no_redirector
    if redirector_enabled:
        cert_path = resolve_root_path(str(redirector_cfg.get("cert_path", "certs/redirector.crt")))
        key_path = resolve_root_path(str(redirector_cfg.get("key_path", "certs/redirector.key")))
        try:
            redirector_server, _ = start_redirector_server(
                bind_host,
                int(redirector_cfg.get("port", 42230)),
                backend_host=str(redirector_cfg.get("backend_host", "127.0.0.1")),
                backend_port=int(redirector_cfg.get("backend_port", 10051)),
                backend_secure=bool(redirector_cfg.get("backend_secure", True)),
                cert_path=cert_path,
                key_path=key_path,
                capture_dir=capture_dir,
            )
            print(
                "[ROUTE] "
                f"{redirector_cfg.get('hostname', 'winter15.gosredirector.ea.com')}:{redirector_cfg.get('port', 42230)} "
                f"-> {redirector_cfg.get('backend_host', '127.0.0.1')}:{redirector_cfg.get('backend_port', 10051)}"
            )
        except (OSError, FileNotFoundError) as exc:
            print(f"[REDIRECTOR] not started: {exc}")
            print("[REDIRECTOR] run: python tools/generate_certs.py")

    probes = []
    if not args.no_probes:
        blocked_ports = {http_port}
        if redirector_enabled:
            blocked_ports.add(int(redirector_cfg.get("port", 42230)))
        ports = [int(p) for p in config.get("probe_ports", []) if int(p) not in blocked_ports]
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
        if redirector_server is not None:
            redirector_server.shutdown()
            redirector_server.server_close()
        for probe in probes:
            probe.shutdown()
            probe.server_close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
