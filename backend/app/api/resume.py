from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import User
from app.schemas.resume import ResumeIn, ResumeOut
from app.services import resume as service

router = APIRouter(prefix="/resume", tags=["resume"])


@router.get("", response_model=ResumeOut | None)
async def get_resume(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """还没有简历时返回 null（而不是 404）：“没有简历”是正常状态，不是错误。"""
    return await service.get_resume(db, user)


@router.put("", response_model=ResumeOut)
async def save_resume(
    data: ResumeIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.save_resume(db, user, data.content_md.strip())


@router.post("/upload", response_model=ResumeOut)
async def upload_resume(
    file: UploadFile, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """上传 PDF / Markdown / 文本文件，提取成文本后保存。原文件不保存，只保存提取出的文本。"""
    # 多读 1 字节：超过上限就能判断出来，又不会把超大文件整个读进内存
    data = await file.read(service.MAX_UPLOAD_BYTES + 1)
    try:
        text = await service.extract_text(file.filename or "", data)
    except service.ResumeParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    source = "pdf" if (file.filename or "").lower().endswith(".pdf") else "manual"
    return await service.save_resume(db, user, text, source=source, filename=file.filename)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await service.delete_resume(db, user)
