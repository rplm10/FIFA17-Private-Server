from __future__ import annotations

import datetime as dt
import socket
from pathlib import Path

from server.tls_hello import parse_client_hello, render_client_hello

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR = ROOT / "logs" / "captures"
HOST = "127.0.0.1"
PORT = 42230


def main() -> int:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        listener.listen(1)
        print(f"[CLIENTHELLO] listening on {HOST}:{PORT}")
        print("[CLIENTHELLO] launch FIFA 17 now; this probe exits after one connection")

        conn, addr = listener.accept()
        with conn:
            conn.settimeout(5.0)
            data = conn.recv(16384)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    raw_path = CAPTURE_DIR / f"redirector_clienthello_{stamp}.bin"
    txt_path = CAPTURE_DIR / f"redirector_clienthello_{stamp}.txt"
    raw_path.write_bytes(data)

    info = parse_client_hello(data)
    if info is None:
        report = f"peer={addr[0]}:{addr[1]}\nbytes={len(data)}\nparse=failed\nhex={data.hex()}\n"
        print(report)
        txt_path.write_text(report, encoding="utf-8")
        return 1

    rendered = render_client_hello(info)
    report = f"peer={addr[0]}:{addr[1]}\nbytes={len(data)}\n{rendered}\n"
    txt_path.write_text(report, encoding="utf-8")
    print("[CLIENTHELLO] captured FIFA TLS offer:")
    print(rendered)
    print(f"[CLIENTHELLO] saved -> {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
