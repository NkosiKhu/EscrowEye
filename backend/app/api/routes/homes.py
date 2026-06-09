from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.home_service import HomeService


class HomeIn(BaseModel):
    name: str
    address: str


class RoomIn(BaseModel):
    name: str
    sq_meters: float | None = None


def create_homes_router(
    *,
    db: Callable,
    now_iso: Callable[[], str],
    current_user: Callable,
    room_payload: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/api/homes", tags=["homes"])

    @router.get("")
    async def list_homes(user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            service = HomeService(session, now_iso, room_payload)
            return await service.list_homes(user["id"])

    @router.post("")
    async def create_home(body: HomeIn, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            service = HomeService(session, now_iso, room_payload)
            return await service.create_home(user["id"], body.name, body.address)

    @router.get("/{home_id}")
    async def get_home(home_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            service = HomeService(session, now_iso, room_payload)
            return await service.get_home(home_id, user["id"])

    @router.put("/{home_id}")
    async def update_home(home_id: int, body: HomeIn, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            service = HomeService(session, now_iso, room_payload)
            return await service.update_home(home_id, user["id"], body.name, body.address)

    @router.delete("/{home_id}", status_code=204)
    async def delete_home(home_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            service = HomeService(session, now_iso, room_payload)
            await service.delete_home(home_id, user["id"])
        return Response(status_code=204)

    @router.post("/{home_id}/rooms")
    async def create_room(home_id: int, body: RoomIn, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            service = HomeService(session, now_iso, room_payload)
            return await service.create_room(home_id, user["id"], body.name, body.sq_meters)

    @router.delete("/{home_id}/rooms/{room_id}", status_code=204)
    async def delete_room(home_id: int, room_id: int, user: dict[str, Any] = Depends(current_user)):
        async with db() as session:
            service = HomeService(session, now_iso, room_payload)
            await service.delete_room(home_id, room_id, user["id"])
        return Response(status_code=204)

    return router
