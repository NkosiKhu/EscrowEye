from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.home_repository import HomeRepository


class HomeService:
    def __init__(self, session: AsyncSession, now_iso: Callable[[], str], room_payload: Callable):
        self.repo = HomeRepository(session)
        self.session = session
        self.now_iso = now_iso
        self.room_payload = room_payload

    async def home_with_rooms(self, home_id: int, owner_id: int | None = None) -> dict[str, Any]:
        home = await self.repo.get_home(home_id, owner_id)
        if home is None:
            raise HTTPException(status_code=404, detail="not_found")
        rooms = await self.repo.list_rooms(home_id)
        return {
            "id": home.id,
            "name": home.name,
            "address": home.address,
            "rooms": [self.room_payload({"id": r.id, "name": r.name, "sq_meters": r.sq_meters}) for r in rooms],
        }

    async def list_homes(self, owner_user_id: int) -> dict[str, Any]:
        homes = await self.repo.list_home_ids_for_owner(owner_user_id)
        result = []
        for home in homes:
            rooms = await self.repo.list_rooms(home.id)
            result.append({
                "id": home.id,
                "name": home.name,
                "address": home.address,
                "rooms": [self.room_payload({"id": r.id, "name": r.name, "sq_meters": r.sq_meters}) for r in rooms],
            })
        return {"homes": result}

    async def create_home(self, owner_user_id: int, name: str, address: str) -> dict[str, Any]:
        home_id = await self.repo.create_home(owner_user_id, name, address, self.now_iso())
        return await self.home_with_rooms(home_id, owner_user_id)

    async def get_home(self, home_id: int, owner_user_id: int) -> dict[str, Any]:
        return await self.home_with_rooms(home_id, owner_user_id)

    async def update_home(self, home_id: int, owner_user_id: int, name: str, address: str) -> dict[str, Any]:
        now = self.now_iso()
        updated = await self.repo.update_home(home_id, owner_user_id, name, address, now)
        if updated is None:
            raise HTTPException(status_code=404, detail="not_found")
        return {"id": home_id, "name": name, "address": address}

    async def delete_home(self, home_id: int, owner_user_id: int) -> None:
        deleted = await self.repo.delete_home(home_id, owner_user_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="not_found")

    async def create_room(self, home_id: int, owner_user_id: int, name: str, sq_meters: float | None) -> dict[str, Any] | None:
        room = await self.repo.create_room(home_id, owner_user_id, name, sq_meters)
        if room is None:
            raise HTTPException(status_code=404, detail="not_found")
        return self.room_payload(room)

    async def delete_room(self, home_id: int, room_id: int, owner_user_id: int) -> None:
        deleted = await self.repo.delete_room(home_id, room_id, owner_user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="not_found")
