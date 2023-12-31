"""delete github_username field

Revision ID: 34da6f777142
Revises: 014414ae43b5
Create Date: 2023-10-23 02:59:14.628844

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '34da6f777142'
down_revision = '014414ae43b5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'github_username')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('github_username', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
    # ### end Alembic commands ###
