from datetime import datetime
from flask_login import UserMixin
from app.extensions import db


class Organization(db.Model):
    __tablename__ = "organizations"

    id        = db.Column(db.Integer, primary_key=True)
    slug      = db.Column(db.String(50), unique=True, nullable=False)
    name      = db.Column(db.String(120), nullable=False)
    plan      = db.Column(db.String(20), default="starter")
    settings  = db.Column(db.JSON, default=dict)
    ativo     = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    users = db.relationship("User", backref="organization", lazy=True)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    org_id        = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    nome          = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    # SUPERADMIN | ADMIN | OPERACIONAL | FINANCEIRO | VIEWER
    role          = db.Column(db.String(20), default="VIEWER")
    ativo         = db.Column(db.Boolean, default=True)
    criado_em     = db.Column(db.DateTime, default=datetime.utcnow)

    def has_role(self, *roles):
        return self.role in roles


class FaturamentoNota(db.Model):
    __tablename__ = "faturamento_notas"

    id               = db.Column(db.Integer, primary_key=True)
    org_id           = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    nr               = db.Column(db.Integer, nullable=False)
    emissao          = db.Column(db.Date, nullable=False)
    contrato         = db.Column(db.String(80))
    orgao            = db.Column(db.String(120))
    municipio        = db.Column(db.String(120))
    tipo             = db.Column(db.String(60))
    bruto            = db.Column(db.Numeric(14, 2), default=0)
    inss             = db.Column(db.Numeric(14, 2), default=0)
    ir               = db.Column(db.Numeric(14, 2), default=0)
    iss              = db.Column(db.Numeric(14, 2), default=0)
    liquido          = db.Column(db.Numeric(14, 2), default=0)
    recebido         = db.Column(db.Boolean, default=False)
    data_recebimento = db.Column(db.Date, nullable=True)
    criado_em        = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("org_id", "nr", name="uq_faturamento_org_nr"),
    )


class MedicaoRecord(db.Model):
    __tablename__ = "medicao_records"

    id          = db.Column(db.Integer, primary_key=True)
    org_id      = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    gerado_por  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    tipo        = db.Column(db.String(40))   # 'parcial' | 'reajustamento'
    contrato    = db.Column(db.String(80))
    periodo     = db.Column(db.String(40))
    docx_r2_key = db.Column(db.String(255))  # key no R2 para download
    criado_em   = db.Column(db.DateTime, default=datetime.utcnow)


class UsinagemRegistro(db.Model):
    __tablename__ = "usinagem_registros"

    id            = db.Column(db.Integer, primary_key=True)
    org_id        = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    ticket        = db.Column(db.String(40))
    data_operacao = db.Column(db.Date)
    placa         = db.Column(db.String(20))
    motorista     = db.Column(db.String(120))
    peso_bruto    = db.Column(db.Numeric(10, 3))
    tara          = db.Column(db.Numeric(10, 3))
    peso_liquido  = db.Column(db.Numeric(10, 3))
    regiao        = db.Column(db.String(60))   # 'AEGEA' | 'GUARIROBA' | etc
    contrato      = db.Column(db.String(80))
    criado_em     = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("org_id", "ticket", name="uq_usinagem_org_ticket"),
    )


class OperacaoProducao(db.Model):
    __tablename__ = "operacoes_producao"

    id              = db.Column(db.Integer, primary_key=True)
    org_id          = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    modo            = db.Column(db.String(10))   # 'tb' | 'qm'
    data_operacao   = db.Column(db.Date, nullable=False)
    ticket_inicio   = db.Column(db.Integer)
    ticket_fim      = db.Column(db.Integer)
    total_caminhoes = db.Column(db.Integer, default=0)
    criado_por      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    criado_em       = db.Column(db.DateTime, default=datetime.utcnow)

    registros = db.relationship(
        "RegistroProducao", backref="operacao", lazy=True, cascade="all, delete-orphan"
    )


class RegistroProducao(db.Model):
    __tablename__ = "registros_producao"

    id          = db.Column(db.Integer, primary_key=True)
    operacao_id = db.Column(db.Integer, db.ForeignKey("operacoes_producao.id"), nullable=False)
    org_id      = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    placa       = db.Column(db.String(20))
    motorista   = db.Column(db.String(120))
    entrada     = db.Column(db.String(10))
    saida       = db.Column(db.String(10))
    tara        = db.Column(db.Numeric(10, 3))
    peso        = db.Column(db.Numeric(10, 3))
    regiao      = db.Column(db.String(80))


class ChecklistTemplate(db.Model):
    __tablename__ = "checklist_template"

    id           = db.Column(db.Integer, primary_key=True)
    org_id       = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    nome         = db.Column(db.String(120), nullable=False)
    itens        = db.Column(db.JSON, nullable=False, default=list)
    criado_em    = db.Column(db.DateTime, default=datetime.utcnow)

    equipamentos = db.relationship("Equipamento", backref="template", lazy=True)


class Equipamento(db.Model):
    __tablename__ = "equipamento"

    id           = db.Column(db.Integer, primary_key=True)
    org_id       = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    nome         = db.Column(db.String(120), nullable=False)
    tipo         = db.Column(db.String(60))
    modelo       = db.Column(db.String(120))
    ano          = db.Column(db.Integer)
    numero_serie = db.Column(db.String(80))
    placa        = db.Column(db.String(20))
    foto_url     = db.Column(db.String(500))
    template_id  = db.Column(db.Integer, db.ForeignKey("checklist_template.id"), nullable=True)
    ativo        = db.Column(db.Boolean, default=True)
    criado_em    = db.Column(db.DateTime, default=datetime.utcnow)

    execucoes    = db.relationship("ChecklistExecucao", backref="equipamento", lazy=True)


class ChecklistExecucao(db.Model):
    __tablename__ = "checklist_execucao"

    id             = db.Column(db.Integer, primary_key=True)
    org_id         = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False)
    equipamento_id = db.Column(db.Integer, db.ForeignKey("equipamento.id"), nullable=False)
    template_id    = db.Column(db.Integer, db.ForeignKey("checklist_template.id"), nullable=False)
    operador_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    data_execucao  = db.Column(db.Date, nullable=False)
    respostas      = db.Column(db.JSON, nullable=False, default=dict)
    status         = db.Column(db.String(20), default="COMPLETO")  # COMPLETO | COM_PENDENCIA
    latitude       = db.Column(db.Float, nullable=True)
    longitude      = db.Column(db.Float, nullable=True)
    criado_em      = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("equipamento_id", "data_execucao", name="uq_checklist_por_dia"),
    )
