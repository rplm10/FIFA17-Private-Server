from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_id INTEGER NOT NULL,
    persona_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    club_name TEXT NOT NULL DEFAULT 'Local FC',
    club_abbr TEXT NOT NULL DEFAULT 'LFC',
    coins INTEGER NOT NULL DEFAULT 0,
    points INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL,
    definition_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    rating INTEGER,
    rarity TEXT,
    quantity INTEGER NOT NULL DEFAULT 1,
    tradeable INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS squads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    formation TEXT NOT NULL DEFAULT '4-4-2',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS squad_slots (
    squad_id INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    inventory_id INTEGER,
    PRIMARY KEY (squad_id, slot),
    FOREIGN KEY (squad_id) REFERENCES squads(id) ON DELETE CASCADE,
    FOREIGN KEY (inventory_id) REFERENCES inventory(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS market_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_id INTEGER,
    item_type TEXT NOT NULL,
    definition_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    start_price INTEGER NOT NULL,
    buy_now_price INTEGER NOT NULL,
    current_bid INTEGER NOT NULL DEFAULT 0,
    seller TEXT NOT NULL DEFAULT 'BOT',
    expires_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inventory_id) REFERENCES inventory(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS pack_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id TEXT NOT NULL,
    cost_type TEXT NOT NULL,
    cost INTEGER NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: str | Path, identity: dict[str, Any], starting_coins: int = 0, starting_points: int = 0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.identity = identity
        self.starting_coins = starting_coins
        self.starting_points = starting_points
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                """
                INSERT OR IGNORE INTO profile
                    (id, user_id, persona_id, display_name, coins, points)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    int(self.identity.get("user_id", 1)),
                    int(self.identity.get("persona_id", 1)),
                    str(self.identity.get("display_name", "LocalPlayer")),
                    int(self.starting_coins),
                    int(self.starting_points),
                ),
            )
            count = conn.execute("SELECT COUNT(*) AS c FROM squads").fetchone()["c"]
            if count == 0:
                conn.execute("INSERT INTO squads (name, formation, is_active) VALUES ('Main Squad', '4-4-2', 1)")

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def get_profile(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM profile WHERE id=1").fetchone()
        return self._row(row) or {}

    def update_club(self, club_name: str | None = None, club_abbr: str | None = None) -> dict[str, Any]:
        fields: list[str] = []
        values: list[Any] = []
        if club_name is not None:
            fields.append("club_name=?")
            values.append(club_name[:40])
        if club_abbr is not None:
            fields.append("club_abbr=?")
            values.append(club_abbr[:4].upper())
        if fields:
            fields.append("updated_at=CURRENT_TIMESTAMP")
            with self.connect() as conn:
                conn.execute(f"UPDATE profile SET {', '.join(fields)} WHERE id=1", values)
        return self.get_profile()

    def adjust_wallet(self, coins_delta: int = 0, points_delta: int = 0) -> dict[str, Any]:
        with self.connect() as conn:
            profile = conn.execute("SELECT coins, points FROM profile WHERE id=1").fetchone()
            if profile is None:
                raise RuntimeError("profile not initialized")
            new_coins = int(profile["coins"]) + int(coins_delta)
            new_points = int(profile["points"]) + int(points_delta)
            if new_coins < 0 or new_points < 0:
                raise ValueError("insufficient balance")
            conn.execute(
                "UPDATE profile SET coins=?, points=?, updated_at=CURRENT_TIMESTAMP WHERE id=1",
                (new_coins, new_points),
            )
        return self.get_profile()

    def add_inventory_item(
        self,
        item_type: str,
        definition_id: int,
        name: str,
        rating: int | None = None,
        rarity: str | None = None,
        tradeable: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO inventory
                    (item_type, definition_id, name, rating, rarity, tradeable, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_type,
                    int(definition_id),
                    name,
                    rating,
                    rarity,
                    1 if tradeable else 0,
                    json.dumps(metadata or {}, separators=(",", ":")),
                ),
            )
            row = conn.execute("SELECT * FROM inventory WHERE id=?", (cur.lastrowid,)).fetchone()
        result = self._row(row) or {}
        result["metadata"] = json.loads(result.pop("metadata_json", "{}"))
        return result

    def list_inventory(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM inventory ORDER BY id DESC").fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json", "{}"))
            result.append(item)
        return result

    def list_squads(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            squads = [dict(r) for r in conn.execute("SELECT * FROM squads ORDER BY id").fetchall()]
            for squad in squads:
                slots = conn.execute(
                    """
                    SELECT ss.slot, i.*
                    FROM squad_slots ss
                    LEFT JOIN inventory i ON i.id = ss.inventory_id
                    WHERE ss.squad_id=?
                    ORDER BY ss.slot
                    """,
                    (squad["id"],),
                ).fetchall()
                squad["slots"] = [dict(r) for r in slots]
        return squads

    def create_listing(
        self,
        item_type: str,
        definition_id: int,
        name: str,
        start_price: int,
        buy_now_price: int,
        expires_at: int,
        seller: str = "BOT",
        inventory_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if start_price < 0 or buy_now_price < start_price:
            raise ValueError("invalid listing price")
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO market_listings
                    (inventory_id, item_type, definition_id, name, start_price, buy_now_price, seller, expires_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inventory_id,
                    item_type,
                    int(definition_id),
                    name,
                    int(start_price),
                    int(buy_now_price),
                    seller,
                    int(expires_at),
                    json.dumps(metadata or {}, separators=(",", ":")),
                ),
            )
            row = conn.execute("SELECT * FROM market_listings WHERE id=?", (cur.lastrowid,)).fetchone()
        result = self._row(row) or {}
        result["metadata"] = json.loads(result.pop("metadata_json", "{}"))
        return result

    def list_active_market(self, now_epoch: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            conn.execute(
                "UPDATE market_listings SET status='expired' WHERE status='active' AND expires_at <= ?",
                (int(now_epoch),),
            )
            rows = conn.execute(
                "SELECT * FROM market_listings WHERE status='active' ORDER BY expires_at, id"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json", "{}"))
            result.append(item)
        return result

    def log_pack_open(self, pack_id: str, cost_type: str, cost: int, result: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO pack_history (pack_id, cost_type, cost, result_json) VALUES (?, ?, ?, ?)",
                (pack_id, cost_type, int(cost), json.dumps(result, separators=(",", ":"))),
            )
