from __future__ import annotations

import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
CERT_DIR = ROOT / "certs"
CA_KEY = CERT_DIR / "fifa17_local_ca.key"
CA_CERT = CERT_DIR / "fifa17_local_ca.crt"
CA_THUMBPRINT = CERT_DIR / "fifa17_local_ca_thumbprint.txt"
SERVER_KEY = CERT_DIR / "redirector.key"
SERVER_CERT = CERT_DIR / "redirector.crt"
PROFILE_MARKER = CERT_DIR / "gos_profile_v1.txt"
REDIRECTOR_HOST = "winter15.gosredirector.ea.com"


def write_private_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def main() -> int:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)

    # Match the certificate *shape* used by legacy GOS/DirtySDK services while
    # generating brand-new local keys. These are development certificates only.
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    ca_name = x509.Name(
        [
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, "GOSDirtysockSupport@ea.com"),
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Electronic Arts, Inc."),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Global Online Studio"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Redwood City"),
            x509.NameAttribute(NameOID.COMMON_NAME, "GOS 2015 Certificate Authority"),
        ]
    )
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    server_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Electronic Arts, Inc. Ltd"),
            x509.NameAttribute(NameOID.COMMON_NAME, REDIRECTOR_HOST),
        ]
    )
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(REDIRECTOR_HOST),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    write_private_key(CA_KEY, ca_key)
    write_private_key(SERVER_KEY, server_key)
    CA_CERT.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    SERVER_CERT.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))

    thumbprint = ca_cert.fingerprint(hashes.SHA1()).hex().upper()
    CA_THUMBPRINT.write_text(thumbprint + "\n", encoding="ascii")
    PROFILE_MARKER.write_text("gos2015-v1\n", encoding="ascii")

    print(f"Generated CA:       {CA_CERT}")
    print(f"Generated server:   {SERVER_CERT}")
    print(f"Generated key:      {SERVER_KEY}")
    print(f"CA subject:         {ca_cert.subject.rfc4514_string()}")
    print(f"Server subject:     {server_cert.subject.rfc4514_string()}")
    print(f"CA SHA1:            {thumbprint}")
    print("These use locally generated keys and are only for the localhost preservation server.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
