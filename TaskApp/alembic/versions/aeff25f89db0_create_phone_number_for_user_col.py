"""create phone number for user col

Revision ID: aeff25f89db0
Revises: 
Create Date: 2023-08-28 19:59:25.616334

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aeff25f89db0'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if inspector.has_table("users") and "phone_number" not in {
        column["name"] for column in inspector.get_columns("users")
    }:
        op.add_column('users', sa.Column('phone_number', sa.String(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    if inspector.has_table("users") and "phone_number" in {
        column["name"] for column in inspector.get_columns("users")
    }:
        op.drop_column('users', 'phone_number')
