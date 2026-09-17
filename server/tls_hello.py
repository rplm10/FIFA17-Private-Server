from __future__ import annotations

from dataclasses import dataclass


TLS_VERSIONS = {
    0x0301: "TLS1.0",
    0x0302: "TLS1.1",
    0x0303: "TLS1.2",
    0x0304: "TLS1.3",
}

CIPHERS = {
    0x0005: "TLS_RSA_WITH_RC4_128_SHA",
    0x000A: "TLS_RSA_WITH_3DES_EDE_CBC_SHA",
    0x002F: "TLS_RSA_WITH_AES_128_CBC_SHA",
    0x0035: "TLS_RSA_WITH_AES_256_CBC_SHA",
    0x003C: "TLS_RSA_WITH_AES_128_CBC_SHA256",
    0x003D: "TLS_RSA_WITH_AES_256_CBC_SHA256",
    0x009C: "TLS_RSA_WITH_AES_128_GCM_SHA256",
    0x009D: "TLS_RSA_WITH_AES_256_GCM_SHA384",
    0xC013: "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA",
    0xC014: "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA",
    0xC027: "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256",
    0xC028: "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA384",
    0xC02F: "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
    0xC030: "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
}

SIG_ALGS = {
    0x0201: "rsa_pkcs1_sha1",
    0x0202: "dsa_sha1",
    0x0203: "ecdsa_sha1",
    0x0401: "rsa_pkcs1_sha256",
    0x0403: "ecdsa_secp256r1_sha256",
    0x0501: "rsa_pkcs1_sha384",
    0x0503: "ecdsa_secp384r1_sha384",
    0x0601: "rsa_pkcs1_sha512",
    0x0603: "ecdsa_secp521r1_sha512",
}

GROUPS = {
    0x0017: "secp256r1",
    0x0018: "secp384r1",
    0x0019: "secp521r1",
    0x001D: "x25519",
}


@dataclass
class ClientHelloInfo:
    record_version: int
    client_version: int
    ciphers: list[int]
    signature_algorithms: list[int]
    supported_groups: list[int]
    supported_versions: list[int]
    server_name: str | None


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "big")


def parse_client_hello(data: bytes) -> ClientHelloInfo | None:
    if len(data) < 11 or data[0] != 22:
        return None
    record_version = _u16(data, 1)
    record_len = _u16(data, 3)
    if len(data) < 5 + record_len or data[5] != 1:
        return None

    p = 9
    if p + 34 > len(data):
        return None
    client_version = _u16(data, p)
    p += 2 + 32

    if p >= len(data):
        return None
    session_len = data[p]
    p += 1 + session_len
    if p + 2 > len(data):
        return None

    cipher_len = _u16(data, p)
    p += 2
    if p + cipher_len > len(data):
        return None
    ciphers = [_u16(data, i) for i in range(p, p + cipher_len, 2)]
    p += cipher_len

    if p >= len(data):
        return ClientHelloInfo(record_version, client_version, ciphers, [], [], [], None)
    compression_len = data[p]
    p += 1 + compression_len
    if p + 2 > len(data):
        return ClientHelloInfo(record_version, client_version, ciphers, [], [], [], None)

    ext_total = _u16(data, p)
    p += 2
    end = min(len(data), p + ext_total)

    sig_algs: list[int] = []
    groups: list[int] = []
    versions: list[int] = []
    server_name: str | None = None

    while p + 4 <= end:
        ext_type = _u16(data, p)
        ext_len = _u16(data, p + 2)
        p += 4
        ext = data[p : p + ext_len]
        p += ext_len

        if ext_type == 0 and len(ext) >= 5:
            name_len = _u16(ext, 3)
            if 5 + name_len <= len(ext):
                server_name = ext[5 : 5 + name_len].decode("ascii", errors="replace")
        elif ext_type == 10 and len(ext) >= 2:
            n = min(_u16(ext, 0), len(ext) - 2)
            groups = [_u16(ext, i) for i in range(2, 2 + n, 2)]
        elif ext_type == 13 and len(ext) >= 2:
            n = min(_u16(ext, 0), len(ext) - 2)
            sig_algs = [_u16(ext, i) for i in range(2, 2 + n, 2)]
        elif ext_type == 43 and len(ext) >= 1:
            n = min(ext[0], len(ext) - 1)
            versions = [_u16(ext, i) for i in range(1, 1 + n, 2)]

    return ClientHelloInfo(
        record_version=record_version,
        client_version=client_version,
        ciphers=ciphers,
        signature_algorithms=sig_algs,
        supported_groups=groups,
        supported_versions=versions,
        server_name=server_name,
    )


def _names(values: list[int], table: dict[int, str]) -> str:
    return ", ".join(table.get(v, f"0x{v:04X}") for v in values) or "<none>"


def render_client_hello(info: ClientHelloInfo) -> str:
    return "\n".join(
        [
            f"record_version={TLS_VERSIONS.get(info.record_version, f'0x{info.record_version:04X}')}",
            f"client_version={TLS_VERSIONS.get(info.client_version, f'0x{info.client_version:04X}')}",
            f"server_name={info.server_name or '<none>'}",
            f"supported_versions={_names(info.supported_versions, TLS_VERSIONS)}",
            f"ciphers={_names(info.ciphers, CIPHERS)}",
            f"signature_algorithms={_names(info.signature_algorithms, SIG_ALGS)}",
            f"supported_groups={_names(info.supported_groups, GROUPS)}",
        ]
    )
