"""add_user_phone_number

Revision ID: b1298461cd12
Revises: 7a47994329ec
Create Date: 2026-08-11 21:15:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1298461cd12'
down_revision: Union[str, None] = '7a47994329ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'users' in tables:
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'phone_number' not in cols:
            op.add_column('users', sa.Column('phone_number', sa.String(length=50), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'users' in tables:
        cols = [c['name'] for c in inspector.get_columns('users')]
        if 'phone_number' in cols:
            try:
                op.drop_column('users', 'phone_number')
            except Exception:
                pass
