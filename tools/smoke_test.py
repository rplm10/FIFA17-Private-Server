from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8099"


def request(method: str, path: str, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def check(name: str, method: str, path: str, payload=None):
    status, body = request(method, path, payload)
    if status != 200:
        raise RuntimeError(f"{name}: expected 200, got {status}")
    print(f"[PASS] {name}: {json.dumps(body)[:240]}")
    return body


def main() -> int:
    try:
        check("health", "GET", "/health")
        club = check("club", "GET", "/api/v1/club")

        if int(club.get("coins", 0)) < 5000:
            check("grant test coins", "POST", "/api/v1/wallet/grant", {"coins": 10000})

        check(
            "rename club",
            "POST",
            "/api/v1/club",
            {"club_name": "University FC", "club_abbr": "UNI"},
        )
        pack = check(
            "open demo pack",
            "POST",
            "/api/v1/store/packs/open",
            {"pack_id": "gold-demo", "cost_type": "coins"},
        )
        if not pack.get("items"):
            raise RuntimeError("pack returned no items")

        check("inventory", "GET", "/api/v1/inventory")
        check("squads", "GET", "/api/v1/squads")
        check(
            "create market listing",
            "POST",
            "/api/v1/market/list",
            {
                "item_type": "player",
                "definition_id": 170003,
                "name": "Local Player C",
                "start_price": 500,
                "buy_now_price": 750,
            },
        )
        check("market", "GET", "/api/v1/market")
    except urllib.error.URLError as exc:
        print(f"[FAIL] server is not reachable at {BASE}: {exc}")
        print("Start it first with: python -m server.main")
        return 1
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1

    print("\nAll foundation smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
