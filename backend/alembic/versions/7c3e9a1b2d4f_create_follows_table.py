"""create follows table

Revision ID: 7c3e9a1b2d4f
Revises: f5f4ae3d212e
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3e9a1b2d4f'
down_revision: Union[str, Sequence[str], None] = 'f5f4ae3d212e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'follows',
        sa.Column('follower_id', sa.UUID(), nullable=False),
        sa.Column('following_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('follower_id <> following_id', name='ck_follows_no_self'),
        sa.ForeignKeyConstraint(['follower_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['following_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('follower_id', 'following_id'),
    )
    op.create_index(op.f('ix_follows_following_id'), 'follows', ['following_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_follows_following_id'), table_name='follows')
    op.drop_table('follows')
