"""Fase 2.2 — invite_tokens table

Revision ID: a8c3d2e1f0b4
Revises: d1e5f3a9b72c
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'a8c3d2e1f0b4'
down_revision = 'd1e5f3a9b72c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('invite_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(120), nullable=False),
        sa.Column('role', sa.String(20), nullable=True),
        sa.Column('usado', sa.Boolean(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('criado_por', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['criado_por'], ['users.id']),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )


def downgrade():
    op.drop_table('invite_tokens')
