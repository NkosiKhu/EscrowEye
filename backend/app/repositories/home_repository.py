from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Home, Room


class HomeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_home_ids_for_owner(self, owner_user_id: int) -> list[Home]:
        result = await self.session.execute(
            select(Home).where(Home.owner_user_id == owner_user_id).order_by(Home.id)
        )
        return list(result.scalars().all())

    async def get_home(self, home_id: int, owner_user_id: int | None = None) -> Home | None:
        query = select(Home).where(Home.id == home_id)
        if owner_user_id is not None:
            query = query.where(Home.owner_user_id == owner_user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_rooms(self, home_id: int) -> list[Room]:
        result = await self.session.execute(
            select(Room).where(Room.home_id == home_id).order_by(Room.id)
        )
        return list(result.scalars().all())

    async def create_home(self, owner_user_id: int, name: str, address: str, now: str) -> int:
        home = Home(
            owner_user_id=owner_user_id,
            name=name,
            address=address,
            created_at=now,
            updated_at=now,
        )
        self.session.add(home)
        await self.session.flush()
        return home.id

    async def update_home(self, home_id: int, owner_user_id: int, name: str, address: str, now: str) -> Home | None:
        home = await self.get_home(home_id, owner_user_id)
        if home is None:
            return None
        home.name = name
        home.address = address
        home.updated_at = now
        return home

    async def delete_home(self, home_id: int, owner_user_id: int) -> Home | None:
        home = await self.get_home(home_id, owner_user_id)
        if home:
            await self.session.delete(home)
        return home

    async def create_room(self, home_id: int, owner_user_id: int, name: str, sq_meters: float | None) -> dict[str, Any] | None:
        home = await self.get_home(home_id, owner_user_id)
        if home is None:
            return None
        room = Room(home_id=home_id, name=name, sq_meters=sq_meters)
        self.session.add(room)
        await self.session.flush()
        return {"id": room.id, "name": room.name, "sq_meters": room.sq_meters}

    async def delete_room(self, home_id: int, room_id: int, owner_user_id: int) -> bool:
        home = await self.get_home(home_id, owner_user_id)
        if home is None:
            return False
        result = await self.session.execute(
            select(Room).where(Room.id == room_id, Room.home_id == home_id)
        )
        room = result.scalar_one_or_none()
        if room is None:
            return False
        await self.session.delete(room)
        return True
