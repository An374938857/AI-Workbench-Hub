from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.base import ApiResponse
from app.utils.security import verify_password, create_access_token, hash_password

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=50)
    role: str = Field("user", pattern="^(user|provider|admin)$")


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ResetMyPasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        return ApiResponse.error(40001, "用户名或密码错误")
    if not user.is_approved:
        return ApiResponse.error(40006, "账号审核中，请联系管理员审核")
    if not user.is_active:
        return ApiResponse.error(40002, "账号已停用，请联系管理员")

    token = create_access_token(user.id, user.role)
    return ApiResponse.success(data={
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
        },
    })


@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        return ApiResponse.error(40200, f"用户名 '{body.username}' 已存在")

    need_approval = body.role != "user"
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
        is_approved=not need_approval,
    )
    db.add(user)
    db.commit()

    if need_approval:
        return ApiResponse.success(message="注册成功，您选择的角色需要管理员审核，请耐心等待")
    return ApiResponse.success(message="注册成功，请使用新账号登录")


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return ApiResponse.success(data={
        "id": current_user.id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
    })


@router.post("/change-password")
def change_password_on_login(body: ResetMyPasswordRequest, db: Session = Depends(get_db)):
    """登录页修改密码，通过用户名+旧密码验证身份"""
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.old_password, user.password_hash):
        return ApiResponse.error(40001, "用户名或原密码错误")
    if not user.is_active:
        return ApiResponse.error(40002, "账号已停用，请联系管理员")
    if body.new_password == body.old_password:
        return ApiResponse.error(40004, "新密码不能与原密码相同")
    if len(body.new_password) < 6:
        return ApiResponse.error(40005, "新密码长度不能少于6位")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return ApiResponse.success(message="密码修改成功，请使用新密码登录")


@router.put("/me/password")
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.old_password, current_user.password_hash):
        return ApiResponse.error(40003, "原密码错误")
    current_user.password_hash = hash_password(body.new_password)
    db.commit()
    return ApiResponse.success(message="密码修改成功")
