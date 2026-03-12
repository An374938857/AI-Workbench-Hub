from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.custom_command import CustomCommand
from app.schemas.command import CommandCreate
from app.models.user import User
from app.schemas.base import ApiResponse

router = APIRouter(prefix="/api/commands", tags=["commands"])

@router.get("")
def get_custom_commands(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取用户的自定义指令列表"""
    commands = db.query(CustomCommand).filter(
        CustomCommand.user_id == current_user.id
    ).order_by(CustomCommand.created_at.desc()).all()
    return ApiResponse.success(data=[
        {
            "id": c.id,
            "user_id": c.user_id,
            "name": c.name,
            "description": c.description,
            "action_type": c.action_type,
            "action_params": c.action_params,
            "created_at": c.created_at.isoformat()
        }
        for c in commands
    ])

@router.post("")
def create_command(
    command: CommandCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建自定义指令"""
    # 检查指令名称是否已存在
    existing = db.query(CustomCommand).filter(
        CustomCommand.user_id == current_user.id,
        CustomCommand.name == command.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="指令名称已存在")
    
    db_command = CustomCommand(
        user_id=current_user.id,
        name=command.name,
        description=command.description,
        action_type=command.action_type,
        action_params=command.action_params
    )
    db.add(db_command)
    db.commit()
    db.refresh(db_command)
    return ApiResponse.success(data={
        "id": db_command.id,
        "user_id": db_command.user_id,
        "name": db_command.name,
        "description": db_command.description,
        "action_type": db_command.action_type,
        "action_params": db_command.action_params,
        "created_at": db_command.created_at.isoformat()
    }, message="指令创建成功")

@router.delete("/{command_id}")
def delete_command(
    command_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除自定义指令"""
    command = db.query(CustomCommand).filter(
        CustomCommand.id == command_id,
        CustomCommand.user_id == current_user.id
    ).first()
    if not command:
        raise HTTPException(status_code=404, detail="指令不存在")
    
    db.delete(command)
    db.commit()
    return ApiResponse.success(message="删除成功")
