from __future__ import annotations

import http.client
import ssl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CA_CERT = ROOT / "certs" / "fifa17_local_ca.crt"

REQUEST = b'''<?xml version="1.0" encoding="UTF-8"?>
<serverinstancerequest>
  <blazesdkversion>test</blazesdkversion>
  <blazesdkbuilddate>test</blazesdkbuilddate>
  <clientname>FIFA17-pc</clientname>
  <clienttype>0</clienttype>
  <clientplatform>pc</clientplatform>
  <clientskuid>test</clientskuid>
  <clientversion>test</clientversion>
  <dirtysdkversion>test</dirtysdkversion>
  <environment>prod</environment>
  <clientlocale>1701727834</clientlocale>
  <name>fifa-17-pc</name>
  <platform>Windows</platform>
  <connectionprofile>standardSecure_v3</connectionprofile>
  <istrial>0</istrial>
</serverinstancerequest>
'''


def main() -> int:
    if not CA_CERT.exists():
        raise SystemExit("CA certificate missing. Run: python tools/generate_certs.py")

    context = ssl.create_default_context(cafile=str(CA_CERT))
    if hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers(
        "AES256-GCM-SHA384:AES128-GCM-SHA256:"
        "AES256-SHA256:AES128-SHA256:AES256-SHA:AES128-SHA:@SECLEVEL=0"
    )

    connection = http.client.HTTPSConnection("127.0.0.1", 42230, context=context, timeout=5)
    connection.request(
        "POST",
        "/redirector/getServerInstance",
        body=REQUEST,
        headers={"Content-Type": "application/xml", "Content-Length": str(len(REQUEST))},
    )
    response = connection.getresponse()
    body = response.read().decode("utf-8", errors="replace")
    print(f"status={response.status}")
    print(body)
    connection.close()

    if response.status != 200 or "<port>10051</port>" not in body:
        return 1
    print("[PASS] redirector returned local Blaze target 127.0.0.1:10051")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
