"""add firlds to user model

Revision ID: 014414ae43b5
Revises: a10280353da3
Create Date: 2023-10-19 03:31:29.112488

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '014414ae43b5'
down_revision = 'a10280353da3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('github_username', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('github_token', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('note_path', sa.String(length=300), nullable=True))
    op.add_column('users', sa.Column('notes_repository', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('notes_branch', sa.String(length=50), nullable=True))
    op.create_unique_constraint(None, 'users', ['user_id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'users', type_='unique')
    op.drop_column('users', 'notes_branch')
    op.drop_column('users', 'notes_repository')
    op.drop_column('users', 'note_path')
    op.drop_column('users', 'github_token')
    op.drop_column('users', 'github_username')
    # ### end Alembic commands ###
