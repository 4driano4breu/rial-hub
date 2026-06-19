"""fase 2.8 e 2.6: dados formularios audit

Revision ID: d1e5f3a9b72c
Revises: c4f9a21b0e38
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = 'd1e5f3a9b72c'
down_revision = 'c4f9a21b0e38'
branch_labels = None
depends_on = None


def upgrade():
    # Soft-delete em usinagem_registros
    op.add_column('usinagem_registros', sa.Column('excluido', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('usinagem_registros', sa.Column('excluido_em', sa.DateTime(), nullable=True))
    op.add_column('usinagem_registros', sa.Column('excluido_por', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_usinagem_excluido_por', 'usinagem_registros', 'users', ['excluido_por'], ['id'])

    # Soft-delete em faturamento_notas
    op.add_column('faturamento_notas', sa.Column('excluido', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('faturamento_notas', sa.Column('excluido_em', sa.DateTime(), nullable=True))
    op.add_column('faturamento_notas', sa.Column('excluido_por', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_faturamento_excluido_por', 'faturamento_notas', 'users', ['excluido_por'], ['id'])

    # Tabela formulario_template
    op.create_table('formulario_template',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('slug', sa.String(80), nullable=False),
        sa.Column('nome', sa.String(120), nullable=False),
        sa.Column('descricao', sa.String(255), nullable=True),
        sa.Column('campos', sa.JSON(), nullable=False),
        sa.Column('aceita_anonimo', sa.Boolean(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'slug', name='uq_formulario_org_slug'),
    )

    # Tabela formulario_resposta
    op.create_table('formulario_resposta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('formulario_template.id'), nullable=False),
        sa.Column('dados', sa.JSON(), nullable=False),
        sa.Column('enviado_por', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('dispositivo', sa.String(200), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # Tabela audit_log
    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('org_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('acao', sa.String(20), nullable=True),
        sa.Column('modulo', sa.String(40), nullable=True),
        sa.Column('registro_id', sa.Integer(), nullable=True),
        sa.Column('campos', sa.JSON(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('audit_log')
    op.drop_table('formulario_resposta')
    op.drop_table('formulario_template')
    op.drop_constraint('fk_faturamento_excluido_por', 'faturamento_notas', type_='foreignkey')
    op.drop_column('faturamento_notas', 'excluido_por')
    op.drop_column('faturamento_notas', 'excluido_em')
    op.drop_column('faturamento_notas', 'excluido')
    op.drop_constraint('fk_usinagem_excluido_por', 'usinagem_registros', type_='foreignkey')
    op.drop_column('usinagem_registros', 'excluido_por')
    op.drop_column('usinagem_registros', 'excluido_em')
    op.drop_column('usinagem_registros', 'excluido')
