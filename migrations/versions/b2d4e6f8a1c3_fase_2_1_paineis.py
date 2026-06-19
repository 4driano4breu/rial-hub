"""Fase 2.1 — paineis table

Revision ID: b2d4e6f8a1c3
Revises: a8c3d2e1f0b4
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2d4e6f8a1c3'
down_revision = 'a8c3d2e1f0b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('paineis',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(80), nullable=False),
        sa.Column('nome', sa.String(120), nullable=False),
        sa.Column('descricao', sa.String(255), nullable=True),
        sa.Column('modulo_fonte', sa.String(40), nullable=False),
        sa.Column('filtros', sa.JSON(), nullable=True),
        sa.Column('config_visual', sa.JSON(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'slug', name='uq_painel_org_slug'),
    )


def downgrade():
    op.drop_table('paineis')
