"""add timezone column to users table"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b5f9c9e1d2a3"
down_revision = "e7c73386549e"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('timezone', sa.String(length=64), nullable=False, server_default='UTC'))

def downgrade():
    op.drop_column('users', 'timezone')
