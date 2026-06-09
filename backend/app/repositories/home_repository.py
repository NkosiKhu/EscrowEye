from __future__ import annotations

import sqlite3
from typing import Any, Callable


class HomeRepository:
    def __init__(self, conn: sqlite3.Connection, one: Callable):
        self.conn = conn
        self.one = one

    def list_home_ids_for_owner(self, owner_user_id: int) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT id FROM homes WHERE owner_user_id = ? ORDER BY id", (owner_user_id,)).fetchall()

    def get_home(self, home_id: int, owner_user_id: int | None = None) -> sqlite3.Row:
        if owner_user_id is None:
            return self.one(self.conn, "SELECT * FROM homes WHERE id = ?", (home_id,))
        return self.one(self.conn, "SELECT * FROM homes WHERE id = ? AND owner_user_id = ?", (home_id, owner_user_id))

    def list_rooms(self, home_id: int) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT id, name, sq_meters FROM rooms WHERE home_id = ? ORDER BY id", (home_id,)).fetchall()

    def create_home(self, owner_user_id: int, name: str, address: str, now: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO homes (owner_user_id, name, address, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (owner_user_id, name, address, now, now),
        )
        return cur.lastrowid

    def update_home(self, home_id: int, owner_user_id: int, name: str, address: str, now: str) -> None:
        self.get_home(home_id, owner_user_id)
        self.conn.execute("UPDATE homes SET name = ?, address = ?, updated_at = ? WHERE id = ?", (name, address, now, home_id))

    def delete_home(self, home_id: int, owner_user_id: int) -> None:
        self.get_home(home_id, owner_user_id)
        self.conn.execute("DELETE FROM homes WHERE id = ?", (home_id,))

    def create_room(self, home_id: int, owner_user_id: int, name: str, sq_meters: float | None) -> sqlite3.Row:
        self.get_home(home_id, owner_user_id)
        cur = self.conn.execute("INSERT INTO rooms (home_id, name, sq_meters) VALUES (?, ?, ?)", (home_id, name, sq_meters))
        return self.one(self.conn, "SELECT id, name, sq_meters FROM rooms WHERE id = ?", (cur.lastrowid,))

    def delete_room(self, home_id: int, room_id: int, owner_user_id: int) -> None:
        self.get_home(home_id, owner_user_id)
        self.one(self.conn, "SELECT id FROM rooms WHERE id = ? AND home_id = ?", (room_id, home_id))
        self.conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
