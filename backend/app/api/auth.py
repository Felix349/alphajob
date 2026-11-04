from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=create_access_token(user.id),
        max_age=settings.jwt_expire_minutes * 60,
        httponly=True,  # JS 读不到，XSS 无法窃取 token
        secure=settings.cookie_secure,  # 上线 https 后必须为 True
        samesite="lax",  # 跨站的 POST 请求不带 cookie，防 CSRF
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.register(db, data)
    except auth_service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="该邮箱已注册") from None
    _set_auth_cookie(response, user)  # 注册后直接登录
    return user


@router.post("/login", response_model=UserOut)
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.authenticate(db, data)
    except auth_service.InvalidCredentials:
        # 不区分“账号不存在”和“密码错误”，避免泄露哪些邮箱注册过
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误") from None
    _set_auth_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    response.delete_cookie(get_settings().cookie_name, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
