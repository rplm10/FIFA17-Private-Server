from __future__ import annotations

import datetime as dt
import socket
import socketserver
import threading
from pathlib import Path


class CaptureHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server: CaptureServer = self.server  # type: ignore[assignment]
        peer = f"{self.client_address[0]}_{self.client_address[1]}"
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base = server.capture_dir / f"port_{server.server_address[1]}_{stamp}_{peer}"

        print(f"[PROBE:{server.server_address[1]}] connection from {self.client_address}")
        self.request.settimeout(1.5)
        chunks: list[bytes] = []
        total = 0
        try:
            while total < server.max_capture_bytes:
                chunk = self.request.recv(min(8192, server.max_capture_bytes - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
        except (socket.timeout, ConnectionResetError, OSError):
            pass

        payload = b"".join(chunks)
        if payload:
            base.with_suffix(".bin").write_bytes(payload)
            base.with_suffix(".txt").write_text(_render_capture(payload), encoding="utf-8")
            print(f"[PROBE:{server.server_address[1]}] captured {len(payload)} bytes -> {base.name}.*")
        else:
            print(f"[PROBE:{server.server_address[1]}] no payload received")


class CaptureServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], capture_dir: Path, max_capture_bytes: int = 262144):
        self.capture_dir = capture_dir
        self.max_capture_bytes = max_capture_bytes
        super().__init__(address, CaptureHandler)


def _render_capture(data: bytes) -> str:
    lines = [f"length={len(data)}", "", "offset    hex                                              ascii"]
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk).ljust(47)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset:08x}  {hex_part}  {ascii_part}")
    return "\n".join(lines) + "\n"


def start_probe_servers(bind_host: str, ports: list[int], capture_dir: str | Path) -> list[CaptureServer]:
    path = Path(capture_dir)
    path.mkdir(parents=True, exist_ok=True)
    servers: list[CaptureServer] = []

    for port in ports:
        try:
            server = CaptureServer((bind_host, int(port)), path)
        except OSError as exc:
            print(f"[PROBE:{port}] unable to listen: {exc}")
            continue
        thread = threading.Thread(target=server.serve_forever, name=f"probe-{port}", daemon=True)
        thread.start()
        servers.append(server)
        print(f"[PROBE:{port}] listening on {bind_host}:{port}")

    return servers
