"""fase-2.7: checklist_template, equipamento, checklist_execucao

Revision ID: c4f9a21b0e38
Revises: b1acbb622e52
Create Date: 2026-06-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4f9a21b0e38'
down_revision = 'b1acbb622e52'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('checklist_template',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('itens', sa.JSON(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('equipamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('tipo', sa.String(length=60), nullable=True),
    sa.Column('modelo', sa.String(length=120), nullable=True),
    sa.Column('ano', sa.Integer(), nullable=True),
    sa.Column('numero_serie', sa.String(length=80), nullable=True),
    sa.Column('placa', sa.String(length=20), nullable=True),
    sa.Column('foto_url', sa.String(length=500), nullable=True),
    sa.Column('template_id', sa.Integer(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['template_id'], ['checklist_template.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('checklist_execucao',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('org_id', sa.Integer(), nullable=False),
    sa.Column('equipamento_id', sa.Integer(), nullable=False),
    sa.Column('template_id', sa.Integer(), nullable=False),
    sa.Column('operador_id', sa.Integer(), nullable=True),
    sa.Column('data_execucao', sa.Date(), nullable=False),
    sa.Column('respostas', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('criado_em', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['equipamento_id'], ['equipamento.id'], ),
    sa.ForeignKeyConstraint(['operador_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ),
    sa.ForeignKeyConstraint(['template_id'], ['checklist_template.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('equipamento_id', 'data_execucao', name='uq_checklist_por_dia')
    )


def downgrade():
    op.drop_table('checklist_execucao')
    op.drop_table('equipamento')
    op.drop_table('checklist_template')
