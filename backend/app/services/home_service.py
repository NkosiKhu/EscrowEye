from __future__ import annotations

import sqlite3
from typing import Any, Callable

from app.repositories.home_repository import HomeRepository


class HomeService:
    def __init__(self, conn: sqlite3.Connection, one: Callable, now_iso: Callable[[], str], room_payload: Callable):
        self.repo = HomeRepository(conn, one)
        self.now_iso = now_iso
        self.room_payload = room_payload

    def home_with_rooms(self, home_id: int, owner_id: int | None = None) -> dict[str, Any]:
        home = self.repo.get_home(home_id, owner_id)
        rooms = self.repo.list_rooms(home_id)
        return {"id": home["id"], "name": home["name"], "address": home["address"], "rooms": [self.room_payload(row) for row in rooms]}

    def list_homes(self, owner_user_id: int) -> dict[str, Any]:
        homes = self.repo.list_home_ids_for_owner(owner_user_id)
        return {"homes": [self.home_with_rooms(row["id"], owner_user_id) for row in homes]}

    def create_home(self, owner_user_id: int, name: str, address: str) -> dict[str, Any]:
        home_id = self.repo.create_home(owner_user_id, name, address, self.now_iso())
        return self.home_with_rooms(home_id, owner_user_id)

    def get_home(self, home_id: int, owner_user_id: int) -> dict[str, Any]:
        return self.home_with_rooms(home_id, owner_user_id)

    def update_home(self, home_id: int, owner_user_id: int, name: str, address: str) -> dict[str, Any]:
        self.repo.update_home(home_id, owner_user_id, name, address, self.now_iso())
        return {"id": home_id, "name": name, "address": address}

    def delete_home(self, home_id: int, owner_user_id: int) -> None:
        self.repo.delete_home(home_id, owner_user_id)

    def create_room(self, home_id: int, owner_user_id: int, name: str, sq_meters: float | None) -> dict[str, Any] | None:
        return self.room_payload(self.repo.create_room(home_id, owner_user_id, name, sq_meters))

    def delete_room(self, home_id: int, room_id: int, owner_user_id: int) -> None:
        self.repo.delete_room(home_id, room_id, owner_user_id)
