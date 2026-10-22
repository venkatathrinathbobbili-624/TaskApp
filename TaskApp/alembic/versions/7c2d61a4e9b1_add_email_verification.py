"""add email verification fields

Revision ID: 7c2d61a4e9b1
Revises: aeff25f89db0
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c2d61a4e9b1"
down_revision: Union[str, None] = "aeff25f89db0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_email_verified" not in columns:
        op.add_column(
            "users",
            sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    if "email_verification_token_hash" not in columns:
        op.add_column(
            "users",
            sa.Column("email_verification_token_hash", sa.String(), nullable=True)
        )
    if "email_verification_expires_at" not in columns:
        op.add_column(
            "users",
            sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("users"):
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    for column_name in (
        "email_verification_expires_at",
        "email_verification_token_hash",
        "is_email_verified",
    ):
        if column_name in columns:
            op.drop_column("users", column_name)
