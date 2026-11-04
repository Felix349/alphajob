import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.application import CalendarEventOut, EventOut, EventUpdate
from app.services import applications as service

router = APIRouter(prefix="/events", tags=["events"])

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="日程不存在")


@router.get("", response_model=list[CalendarEventOut])
async def list_events(
    start: AwareDatetime,
    end: AwareDatetime,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """日历视图：查询 [start, end) 时间范围内开始的所有日程。"""
    try:
        return await service.list_calendar(db, user, start, end)
    except service.InvalidRange as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: uuid.UUID,
    data: EventUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.update_event(db, user, event_id, data)
    except service.NotFound:
        raise NOT_FOUND from None
    except service.InvalidRange as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        await service.delete_event(db, user, event_id)
    except service.NotFound:
        raise NOT_FOUND from None
