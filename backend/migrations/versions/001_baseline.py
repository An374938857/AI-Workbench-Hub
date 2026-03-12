"""baseline schema

Revision ID: 001
Revises:
Create Date: 2026-03-13
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Build the full v1.0 schema from SQLAlchemy models.
    import app.models  # noqa: F401
    from app.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    import app.models  # noqa: F401
    from app.database import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
