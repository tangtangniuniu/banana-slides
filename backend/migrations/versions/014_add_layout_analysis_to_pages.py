"""add layout_analysis and confirmed_element_ids to pages

Revision ID: 014_add_layout_analysis
Revises: 38be7ac05f65
Create Date: 2026-02-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '014_add_layout_analysis'
down_revision = '38be7ac05f65'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add layout_analysis and confirmed_element_ids columns to pages table."""
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = [col['name'] for col in inspector.get_columns('pages')]

    if 'layout_analysis' not in columns:
        op.add_column('pages', sa.Column('layout_analysis', sa.Text(), nullable=True))

    if 'confirmed_element_ids' not in columns:
        op.add_column('pages', sa.Column('confirmed_element_ids', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('pages', 'confirmed_element_ids')
    op.drop_column('pages', 'layout_analysis')
