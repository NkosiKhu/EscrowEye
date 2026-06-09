from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from app.services.home_service import HomeService


class HomeIn(BaseModel):
    name: str
    address: str


class RoomIn(BaseModel):
    name: str
    sq_meters: Optional[float] = None


def create_homes_router(
    *,
    db: Callable,
    one: Callable,
    now_iso: Callable[[], str],
    current_user: Callable,
    room_payload: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/api/homes", tags=["homes"])

    def service(conn) -> HomeService:
        return HomeService(conn, one, now_iso, room_payload)

    @router.get("")
    def list_homes(user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).list_homes(user["id"])

    @router.post("")
    def create_home(body: HomeIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).create_home(user["id"], body.name, body.address)

    @router.get("/{home_id}")
    def get_home(home_id: int, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).get_home(home_id, user["id"])

    @router.put("/{home_id}")
    def update_home(home_id: int, body: HomeIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).update_home(home_id, user["id"], body.name, body.address)

    @router.delete("/{home_id}", status_code=204)
    def delete_home(home_id: int, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            service(conn).delete_home(home_id, user["id"])
        return Response(status_code=204)

    @router.post("/{home_id}/rooms")
    def create_room(home_id: int, body: RoomIn, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            return service(conn).create_room(home_id, user["id"], body.name, body.sq_meters)

    @router.delete("/{home_id}/rooms/{room_id}", status_code=204)
    def delete_room(home_id: int, room_id: int, user: dict[str, Any] = Depends(current_user)):
        with db() as conn:
            service(conn).delete_room(home_id, room_id, user["id"])
        return Response(status_code=204)

    return router
