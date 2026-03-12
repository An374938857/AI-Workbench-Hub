"""Create default admin account if not exists."""

import os
import sys

from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.utils.security import hash_password


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_DISPLAY_NAME = "管理员"


def init_admin() -> None:
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == DEFAULT_ADMIN_USERNAME).first()
        if existing:
            print("Admin already exists, skip.")
            return

        admin = User(
            username=DEFAULT_ADMIN_USERNAME,
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            display_name=DEFAULT_ADMIN_DISPLAY_NAME,
            role="admin",
            is_active=True,
            is_approved=True,
            auto_route_enabled=True,
        )
        db.add(admin)
        db.commit()
        print("Admin created: admin / admin123")
    finally:
        db.close()


if __name__ == "__main__":
    init_admin()
