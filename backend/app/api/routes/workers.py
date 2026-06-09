from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import marketplace as marketplace_service

router = APIRouter(prefix="/api", tags=["workers"])


@router.get("/service-categories")
def service_categories():
    return {"categories": marketplace_service.SERVICE_CATEGORIES}


@router.get("/workers")
def workers(category: str | None = None, location: str | None = None):
    return {"workers": marketplace_service.list_workers(category, location)}


@router.get("/workers/{worker_id}")
def worker_detail(worker_id: int):
    worker = next((item for item in marketplace_service.WORKERS if item["id"] == worker_id), None)
    if worker is None:
        raise HTTPException(status_code=404, detail="not_found")
    return worker


@router.get("/workers/{worker_id}/portfolio")
def worker_portfolio(worker_id: int):
    _ = worker_detail(worker_id)
    return {
        "worker_id": worker_id,
        "portfolio": [
            {
                "id": 1,
                "title": "Post-construction cleaning",
                "media_url": "https://images.unsplash.com/photo-1588167056547-c183313da47c?auto=format&fit=crop&w=900&q=80",
                "description": "Window, floor, and balcony cleaning for a newly completed duplex.",
            },
            {
                "id": 2,
                "title": "Short-let turnover",
                "media_url": "https://images.unsplash.com/photo-1561518605-1e0e8639d027?auto=format&fit=crop&w=900&q=80",
                "description": "Fast Airbnb reset with linen change and proof photos.",
            },
        ],
    }


@router.get("/workers/{worker_id}/reviews")
def worker_reviews(worker_id: int):
    _ = worker_detail(worker_id)
    return {
        "worker_id": worker_id,
        "reviews": [
            {
                "id": 1,
                "rating": 5,
                "author": "Chijoke N.",
                "body": "Clear quote, arrived on time, and uploaded proof before requesting release.",
            },
            {
                "id": 2,
                "rating": 4,
                "author": "Kurt K.",
                "body": "Good work and responsive in chat. Needed one extra image for validation.",
            },
        ],
    }
