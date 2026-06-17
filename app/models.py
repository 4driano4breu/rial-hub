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
