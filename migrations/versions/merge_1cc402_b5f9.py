"""merge heads for calendar and timezone migrations"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "merge_1cc402_b5f9"
# down_revision is a tuple of parent revisions
down_revision = ("1cc402932217", "b5f9c9e1d2a3")
branch_labels = None
depends_on = None

def upgrade():
    # No schema changes; just merging branches
    pass

def downgrade():
    # No schema changes to revert
    pass
