# FIFA 17 Private Server / Local FUT

University reverse-engineering and preservation project for rebuilding discontinued FIFA 17 Ultimate Team services as a local server emulator.

## Current milestone: FIFA 17 redirector discovery

This repository currently provides:

- a local HTTP/FUT service scaffold;
- SQLite persistence for a local club/profile;
- health, club, wallet, pack and market test endpoints;
- a working HTTPS redirector endpoint on port `42230`;
- local TLS certificate generation for `winter15.gosredirector.ea.com`;
- Windows HOSTS + local CA installation/removal scripts;
- TCP probe listeners for capturing the next FIFA 17 network stage;
- structured logging for protocol captures;
- a configuration file for host/port mapping.

It does **not** bypass game ownership, EA App/Origin entitlement checks, DRM, or live EA authentication. Use a legitimate FIFA 17 installation.

## What the FIFA 17 executable told us

The current executable scan confirms the client contains:

- `winter15.gosredirector.ea.com`
- `redirector/getServerInstance`
- Blaze Redirector structures
- Blaze Util `PreAuthRequest` / `PreAuthResponse`
- Blaze Authentication structures
- `FUT_RS4_BASE_URL`
- EASW session/token headers

The immediate goal is therefore:

```text
FIFA17.exe
    |
    | HTTPS :42230
    v
winter15.gosredirector.ea.com
    |
    | serverinstanceinfo -> 127.0.0.1:10051
    v
local Blaze capture probe
    |
    v
logs/captures
```

Once the client reaches `10051`, the captured TLS/Blaze traffic becomes the basis for the FIRE2/TDF implementation.

## Requirements

- Windows 10/11
- Python 3.11+
- A legitimate FIFA 17 installation

Python dependency installation is handled by the setup script, or manually with:

```powershell
python -m pip install -r requirements.txt
```

## First-time Windows setup

Open **PowerShell as Administrator**:

```powershell
cd "C:\Users\Administrator\Desktop\FIFA17-Private-Server"
git pull
powershell -ExecutionPolicy Bypass -File .\tools\install_local_redirector.ps1
```

This does three local-machine development changes:

1. generates a private local development CA and redirector certificate;
2. trusts that CA in the Windows Local Machine Root store;
3. adds `127.0.0.1 winter15.gosredirector.ea.com` to the HOSTS file.

Only use these certificates for this local test environment. Private keys under `certs/` are ignored by git.

## Start the emulator

```powershell
python -m server.main
```

Expected startup includes lines similar to:

```text
[HTTP]  http://127.0.0.1:8099/health
[REDIRECTOR] HTTPS listening on 127.0.0.1:42230
[ROUTE] winter15.gosredirector.ea.com:42230 -> 127.0.0.1:10051
[PROBE:10051] listening on 127.0.0.1:10051
[READY] Press Ctrl+C to stop.
```

## Validate the redirector before starting FIFA

With the server running, open a second PowerShell window:

```powershell
cd "C:\Users\Administrator\Desktop\FIFA17-Private-Server"
python tools\test_redirector.py
```

Expected final line:

```text
[PASS] redirector returned local Blaze target 127.0.0.1:10051
```

You can also run the FUT backend smoke test:

```powershell
python tools\smoke_test.py
```

## FIFA 17 test

Keep `python -m server.main` running and launch your legitimate FIFA 17 installation normally.

Watch the server console for one of these outcomes:

```text
[REDIRECTOR] captured request -> redirector_....txt
[REDIRECTOR] client request: ...
[REDIRECTOR] returned 127.0.0.1:10051 secure=1
[PROBE:10051] connection from (...)
[PROBE:10051] captured ... bytes -> port_10051_....bin/.txt
```

If a `port_10051_*.txt` capture appears, send that file for the next implementation step.

## Captures

All protocol discovery output is written under:

```text
logs/captures/
```

The most useful files after a FIFA launch are:

```text
redirector_*.txt
port_10051_*.txt
port_10051_*.bin
```

## Local FUT backend

The independent local backend remains available on port `8099` and currently includes:

- local profile / club;
- Coins / Points wallet;
- inventory;
- squads;
- packs;
- basic market listings;
- SQLite persistence.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8099/health
```

## Remove local redirector changes

Open **PowerShell as Administrator**:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\remove_local_redirector.ps1
```

This removes the HOSTS entry and the local development CA from the Windows Root store.

## Reset local club data

```powershell
Remove-Item .\data\fut17.sqlite3 -ErrorAction SilentlyContinue
python -m server.main
```

## Project scope

The goal is protocol emulation and preservation of retired online functionality. The project intentionally excludes DRM/license bypassing and access to live EA services.
