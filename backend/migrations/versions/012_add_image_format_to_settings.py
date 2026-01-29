"""Add image_format to settings

Revision ID: 012_add_image_format_to_settings
Revises: 011_add_user_template_thumb
Create Date: 2026-01-23
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012_add_image_format_to_settings'
down_revision = 'c294bfaa0ec2'
branch_labels = None
depends_on = None


def upgrade():
    # Add image_format column to settings table
    op.add_column('settings', sa.Column('image_format', sa.String(10), nullable=False, server_default='PNG'))


def downgrade():
    # Remove image_format column from settings table
    op.drop_column('settings', 'image_format')
