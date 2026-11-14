"""seed roles client and coach"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "d3f1a2b9c4e5"
branch_labels = None
depends_on = None

def upgrade():
    # Insert roles if they don't exist
    conn = op.get_bind()
    existing = conn.execute(sa.text("SELECT name FROM roles WHERE name IN ('client','coach')"))
    existing_names = {row[0] for row in existing}
    to_insert = []
    if 'client' not in existing_names:
        to_insert.append({'name': 'client'})
    if 'coach' not in existing_names:
        to_insert.append({'name': 'coach'})
    if to_insert:
        op.bulk_insert(sa.Table('roles', sa.MetaData(),
                               sa.Column('id', sa.Integer, primary_key=True),
                               sa.Column('name', sa.String(64))),
                         [{'name': r['name']} for r in to_insert])

def downgrade():
    op.execute(sa.text("DELETE FROM roles WHERE name IN ('client','coach')"))
