"""add is_email_confirmed column to users table"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d3f1a2b9c4e5"
down_revision = "merge_1cc402_b5f9"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users',
        sa.Column('is_email_confirmed', sa.Boolean(), nullable=False, server_default=sa.text('0')))

def downgrade():
    op.drop_column('users', 'is_email_confirmed')
