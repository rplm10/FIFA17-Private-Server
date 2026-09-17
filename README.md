# FIFA 17 Private Server / Local FUT

University reverse-engineering and preservation project for rebuilding discontinued FIFA 17 Ultimate Team services as a local server emulator.

## Current milestone: Phase 0 / MVP foundation

This repository currently provides:

- a local HTTP/FUT service scaffold;
- SQLite persistence for a local club/profile;
- health, club, wallet, pack and market test endpoints;
- TCP probe listeners for discovering FIFA 17 client traffic;
- structured logging for protocol captures;
- a configuration file for host/port mapping;
- Windows-friendly startup commands.

It does **not** bypass game ownership, EA App/Origin entitlement checks, DRM, or account authentication. Use a legitimate FIFA 17 installation.

## Requirements

- Windows 10/11
- Python 3.11+
- A legitimate FIFA 17 installation

No third-party Python packages are required for the initial scaffold.

## Quick start

```powershell
git pull
python -m server.main
```

Then, in another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8099/health
Invoke-RestMethod http://127.0.0.1:8099/api/v1/club
```

Expected health response:

```json
{
  "status": "ok",
  "service": "fifa17-local-fut",
  "phase": "foundation"
}
```

## Architecture

```text
FIFA17.exe
    |
    +--> discovery / TCP probes
    |        |
    |        +--> logs/captures
    |
    +--> FUT HTTP emulator :8099
             |
             +--> local profile / club
             +--> wallet
             +--> packs
             +--> transfer market
             +--> SQLite persistence
```

The next milestone is wiring the actual FIFA 17 client traffic to the local services and implementing the protocol contracts it expects.

## Useful commands

Reset the local database:

```powershell
Remove-Item .\data\fut17.sqlite3 -ErrorAction SilentlyContinue
python -m server.main
```

Run the smoke test:

```powershell
python tools\smoke_test.py
```

## Project scope

The goal is protocol emulation and preservation of retired online functionality. The project intentionally excludes DRM/license bypassing and access to live EA services.
