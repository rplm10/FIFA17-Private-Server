from __future__ import annotations

import datetime as dt
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree as ET


class RedirectorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        backend_host: str,
        backend_port: int,
        backend_secure: bool,
        capture_dir: Path,
        tls_context: ssl.SSLContext,
    ) -> None:
        self.backend_host = backend_host
        self.backend_port = int(backend_port)
        self.backend_secure = bool(backend_secure)
        self.capture_dir = capture_dir
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.tls_context = tls_context
        super().__init__(address, RedirectorHandler)

    def get_request(self):  # type: ignore[override]
        """Accept raw TCP first so failed TLS handshakes are visible in the log."""
        while True:
            raw_sock, client_address = self.socket.accept()
            peer = f"{client_address[0]}:{client_address[1]}"
            print(f"[REDIRECTOR/TCP] accepted {peer}")
            raw_sock.settimeout(5.0)

            try:
                tls_sock = self.tls_context.wrap_socket(
                    raw_sock,
                    server_side=True,
                    do_handshake_on_connect=True,
                )
                cipher = tls_sock.cipher()
                cipher_name = cipher[0] if cipher else "unknown"
                print(
                    f"[REDIRECTOR/TLS] handshake OK from {peer}: "
                    f"protocol={tls_sock.version()} cipher={cipher_name}"
                )
                tls_sock.settimeout(None)
                return tls_sock, client_address
            except ssl.SSLError as exc:
                self._capture_tls_failure(client_address, exc)
                print(f"[REDIRECTOR/TLS] handshake FAILED from {peer}: {exc}")
                try:
                    raw_sock.close()
                except OSError:
                    pass
            except OSError as exc:
                self._capture_tls_failure(client_address, exc)
                print(f"[REDIRECTOR/TLS] socket FAILED from {peer}: {exc}")
                try:
                    raw_sock.close()
                except OSError:
                    pass

    def _capture_tls_failure(self, client_address: tuple[str, int], exc: BaseException) -> None:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.capture_dir / f"redirector_tls_failure_{stamp}.txt"
        path.write_text(
            "\n".join(
                [
                    f"peer={client_address[0]}:{client_address[1]}",
                    f"exception_type={type(exc).__name__}",
                    f"exception={exc}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )


class RedirectorHandler(BaseHTTPRequestHandler):
    server: RedirectorHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[REDIRECTOR] {self.client_address[0]}:{self.client_address[1]} - {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/redirector/getServerInstance":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        self._capture_request(body)
        self._print_request_summary(body)

        ip_number = 2130706433 if self.server.backend_host in {"127.0.0.1", "localhost"} else 0
        secure = 1 if self.server.backend_secure else 0
        response = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<serverinstanceinfo>"
            '<address member="0"><valu>'
            f"<hostname>{self.server.backend_host}</hostname>"
            f"<ip>{ip_number}</ip>"
            f"<port>{self.server.backend_port}</port>"
            "</valu></address>"
            f"<secure>{secure}</secure>"
            "<trialservicename></trialservicename>"
            "<defaultdnsaddress>0</defaultdnsaddress>"
            "<messages><warnMessage>FIFA17 Local FUT development server</warnMessage></messages>"
            "</serverinstanceinfo>"
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(response)
        self.close_connection = True
        print(
            f"[REDIRECTOR] returned {self.server.backend_host}:{self.server.backend_port} "
            f"secure={secure}"
        )

    def _capture_request(self, body: bytes) -> None:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        base = self.server.capture_dir / f"redirector_{stamp}"
        base.with_suffix(".bin").write_bytes(body)
        headers = "\n".join(f"{k}: {v}" for k, v in self.headers.items())
        text = f"POST {self.path}\n{headers}\n\n" + body.decode("utf-8", errors="replace")
        base.with_suffix(".txt").write_text(text, encoding="utf-8")
        print(f"[REDIRECTOR] captured request -> {base.name}.txt")

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    def _print_request_summary(self, body: bytes) -> None:
        if not body:
            print("[REDIRECTOR] empty request body")
            return
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            print(f"[REDIRECTOR] request body is not XML ({len(body)} bytes)")
            return

        wanted = {
            "blazesdkversion",
            "blazesdkbuilddate",
            "clientname",
            "clienttype",
            "clientplatform",
            "clientskuid",
            "clientversion",
            "dirtysdkversion",
            "environment",
            "clientlocale",
            "name",
            "platform",
            "connectionprofile",
            "istrial",
        }
        values: dict[str, str] = {}
        for elem in root.iter():
            key = self._local_name(elem.tag)
            if key in wanted and elem.text:
                values[key] = elem.text.strip()
        if values:
            rendered = ", ".join(f"{k}={v}" for k, v in values.items())
            print(f"[REDIRECTOR] client request: {rendered}")


def start_redirector_server(
    bind_host: str,
    port: int,
    *,
    backend_host: str,
    backend_port: int,
    backend_secure: bool,
    cert_path: str | Path,
    key_path: str | Path,
    capture_dir: str | Path,
) -> tuple[RedirectorHTTPServer, threading.Thread]:
    cert = Path(cert_path)
    key = Path(key_path)
    if not cert.exists() or not key.exists():
        raise FileNotFoundError(
            f"redirector TLS certificate missing: cert={cert} key={key}; run python tools/generate_certs.py"
        )

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

    # FIFA 17's 2016-era Blaze client offers cipher suites that modern
    # OpenSSL/Python security defaults may reject. This listener is loopback-only
    # and dedicated to the preservation emulator, so allow the legacy TLS 1.0-1.2
    # cipher range here rather than weakening system-wide TLS settings.
    if hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1
        context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers("ALL:@SECLEVEL=0")
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))

    enabled_ciphers = context.get_ciphers()
    print(
        f"[REDIRECTOR/TLS] compatibility mode: TLSv1-TLSv1.2, "
        f"{len(enabled_ciphers)} cipher entries enabled"
    )

    def log_sni(ssl_sock: ssl.SSLSocket, server_name: str | None, _context: ssl.SSLContext) -> None:
        try:
            peer = ssl_sock.getpeername()
            peer_text = f"{peer[0]}:{peer[1]}"
        except OSError:
            peer_text = "unknown"
        print(f"[REDIRECTOR/TLS] SNI from {peer_text}: {server_name or '<none>'}")

    context.set_servername_callback(log_sni)

    server = RedirectorHTTPServer(
        (bind_host, int(port)),
        backend_host=backend_host,
        backend_port=int(backend_port),
        backend_secure=backend_secure,
        capture_dir=Path(capture_dir),
        tls_context=context,
    )

    thread = threading.Thread(target=server.serve_forever, name="redirector-https", daemon=True)
    thread.start()
    print(f"[REDIRECTOR] HTTPS listening on {bind_host}:{port}")
    return server, thread
