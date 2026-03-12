"""用户排序偏好路由"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.user import User
from app.models.user_sort_preference import UserSortPreference
from app.schemas.base import ApiResponse
from app.schemas.sort_preference import SortPreferenceUpdate

router = APIRouter()


@router.put("")
def update_sort_preferences(
    body: SortPreferenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    for item in body.items:
        existing = (
            db.query(UserSortPreference)
            .filter(
                UserSortPreference.user_id == current_user.id,
                UserSortPreference.target_type == body.target_type,
                UserSortPreference.target_id == item.id,
            )
            .first()
        )
        if existing:
            existing.sort_order = item.sort_order
        else:
            pref = UserSortPreference(
                user_id=current_user.id,
                target_type=body.target_type,
                target_id=item.id,
                sort_order=item.sort_order,
            )
            db.add(pref)

    db.commit()
    return ApiResponse.success(message="排序已更新")


@router.get("/{target_type}")
def get_sort_preferences(
    target_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if target_type not in ("skill", "mcp", "conversation"):
        return ApiResponse.error(40000, "无效的 target_type")

    prefs = (
        db.query(UserSortPreference)
        .filter(
            UserSortPreference.user_id == current_user.id,
            UserSortPreference.target_type == target_type,
        )
        .order_by(UserSortPreference.sort_order)
        .all()
    )
    return ApiResponse.success(data=[
        {"target_id": p.target_id, "sort_order": p.sort_order}
        for p in prefs
    ])
