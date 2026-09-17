from __future__ import annotations

import json
import random
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .db import Database

PACKS = [
    {"id": "bronze-demo", "name": "Bronze Demo Pack", "coins": 400, "points": 0, "items": 4},
    {"id": "silver-demo", "name": "Silver Demo Pack", "coins": 2500, "points": 0, "items": 6},
    {"id": "gold-demo", "name": "Gold Demo Pack", "coins": 5000, "points": 100, "items": 8},
]

SAMPLE_ITEMS = [
    {"definition_id": 170001, "item_type": "player", "name": "Local Player A", "rating": 72, "rarity": "bronze"},
    {"definition_id": 170002, "item_type": "player", "name": "Local Player B", "rating": 76, "rarity": "silver"},
    {"definition_id": 170003, "item_type": "player", "name": "Local Player C", "rating": 81, "rarity": "gold"},
    {"definition_id": 170004, "item_type": "consumable", "name": "Contract", "rating": None, "rarity": "common"},
    {"definition_id": 170005, "item_type": "club", "name": "Local FC Home Kit", "rating": None, "rarity": "common"},
]


class FutHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], db: Database):
        super().__init__(server_address, FutRequestHandler)
        self.db = db


class FutRequestHandler(BaseHTTPRequestHandler):
    server: FutHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[HTTP] {self.client_address[0]} {fmt % args}")

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, payload: Any) -> None:
        self._send(HTTPStatus.OK, payload)

    def _error(self, status: int, message: str) -> None:
        self._send(status, {"error": message})

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        db = self.server.db

        if path == "/health":
            self._ok({"status": "ok", "service": "fifa17-local-fut", "phase": "foundation"})
            return

        if path in ("/api/v1/profile", "/api/v1/club"):
            self._ok(db.get_profile())
            return

        if path == "/api/v1/inventory":
            self._ok({"items": db.list_inventory()})
            return

        if path == "/api/v1/squads":
            self._ok({"squads": db.list_squads()})
            return

        if path == "/api/v1/store/packs":
            self._ok({"packs": PACKS})
            return

        if path == "/api/v1/market":
            self._ok({"listings": db.list_active_market(int(time.time()))})
            return

        if path == "/api/v1/debug/routes":
            self._ok(
                {
                    "routes": [
                        "GET /health",
                        "GET /api/v1/club",
                        "POST /api/v1/club",
                        "POST /api/v1/wallet/grant",
                        "GET /api/v1/inventory",
                        "GET /api/v1/squads",
                        "GET /api/v1/store/packs",
                        "POST /api/v1/store/packs/open",
                        "GET /api/v1/market",
                        "POST /api/v1/market/list",
                    ]
                }
            )
            return

        self._error(HTTPStatus.NOT_FOUND, f"unknown route: {path}")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        db = self.server.db
        try:
            body = self._json_body()

            if path == "/api/v1/club":
                profile = db.update_club(body.get("club_name"), body.get("club_abbr"))
                self._ok(profile)
                return

            if path == "/api/v1/wallet/grant":
                profile = db.adjust_wallet(
                    coins_delta=int(body.get("coins", 0)),
                    points_delta=int(body.get("points", 0)),
                )
                self._ok(profile)
                return

            if path == "/api/v1/store/packs/open":
                self._open_pack(body)
                return

            if path == "/api/v1/market/list":
                listing = db.create_listing(
                    item_type=str(body.get("item_type", "player")),
                    definition_id=int(body.get("definition_id", 0)),
                    name=str(body.get("name", "Unknown Item")),
                    start_price=int(body.get("start_price", 150)),
                    buy_now_price=int(body.get("buy_now_price", 200)),
                    expires_at=int(body.get("expires_at", int(time.time()) + 3600)),
                    seller=str(body.get("seller", "BOT")),
                    inventory_id=body.get("inventory_id"),
                    metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else None,
                )
                self._ok(listing)
                return

            self._error(HTTPStatus.NOT_FOUND, f"unknown route: {path}")
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # keep probe server alive during reverse engineering
            print(f"[HTTP] unhandled error: {exc!r}")
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error")

    def _open_pack(self, body: dict[str, Any]) -> None:
        db = self.server.db
        pack_id = str(body.get("pack_id", "gold-demo"))
        pack = next((p for p in PACKS if p["id"] == pack_id), None)
        if pack is None:
            raise ValueError("unknown pack_id")

        cost_type = str(body.get("cost_type", "coins"))
        if cost_type not in ("coins", "points", "free"):
            raise ValueError("cost_type must be coins, points, or free")

        cost = 0
        if cost_type == "coins":
            cost = int(pack["coins"])
            db.adjust_wallet(coins_delta=-cost)
        elif cost_type == "points":
            cost = int(pack["points"])
            if cost <= 0:
                raise ValueError("this demo pack cannot be purchased with points")
            db.adjust_wallet(points_delta=-cost)

        created: list[dict[str, Any]] = []
        for _ in range(int(pack["items"])):
            item = random.choice(SAMPLE_ITEMS)
            created.append(
                db.add_inventory_item(
                    item_type=str(item["item_type"]),
                    definition_id=int(item["definition_id"]),
                    name=str(item["name"]),
                    rating=item["rating"],
                    rarity=str(item["rarity"]),
                    tradeable=True,
                    metadata={"source": pack_id, "demo": True},
                )
            )

        db.log_pack_open(pack_id, cost_type, cost, created)
        self._ok({"pack": pack, "cost_type": cost_type, "cost": cost, "items": created, "profile": db.get_profile()})
