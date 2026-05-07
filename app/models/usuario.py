from datetime import datetime
from app.extensions import db, login_manager
from app.utils.datetime_utils import agora_brasilia
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class Perfil:
    ADMINISTRADOR = 'Administrador'
    RESPONSAVEL_QUALIDADE = 'Responsável da Qualidade'
    RESPONSAVEL_TECNICO = 'Responsável Técnico'
    APROVADOR = 'Aprovador'
    COLABORADOR_CONSULTA = 'Colaborador Consulta'
    AUDITOR_EXTERNO = 'Auditor Externo / Técnico'

    TODOS = [
        ADMINISTRADOR,
        RESPONSAVEL_QUALIDADE,
        RESPONSAVEL_TECNICO,
        APROVADOR,
        COLABORADOR_CONSULTA,
        AUDITOR_EXTERNO,
    ]


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(256), nullable=False)
    perfil = db.Column(
        db.String(50), nullable=False, default=Perfil.COLABORADOR_CONSULTA
    )
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=agora_brasilia, nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────────
    documentos_elaborados = db.relationship(
        'Documento',
        foreign_keys='Documento.elaborado_por_id',
        backref='elaborado_por',
        lazy='dynamic',
    )
    documentos_revisados = db.relationship(
        'Documento',
        foreign_keys='Documento.revisado_por_id',
        backref='revisado_por',
        lazy='dynamic',
    )
    documentos_aprovados = db.relationship(
        'Documento',
        foreign_keys='Documento.aprovado_por_id',
        backref='aprovado_por',
        lazy='dynamic',
    )
    historico_eventos = db.relationship(
        'HistoricoEvento', backref='usuario', lazy='dynamic'
    )

    # ── Password helpers ───────────────────────────────────────────────────────
    def set_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    # ── Permission helpers ─────────────────────────────────────────────────────
    def pode_abrir_revisao(self) -> bool:
        return self.perfil in [Perfil.ADMINISTRADOR, Perfil.RESPONSAVEL_QUALIDADE]

    def pode_revisar(self) -> bool:
        return self.perfil in [
            Perfil.ADMINISTRADOR,
            Perfil.RESPONSAVEL_QUALIDADE,
            Perfil.RESPONSAVEL_TECNICO,
        ]

    def pode_aprovar(self) -> bool:
        return self.perfil in [Perfil.APROVADOR, Perfil.ADMINISTRADOR]

    def pode_editar_documentos(self) -> bool:
        return self.perfil in [
            Perfil.ADMINISTRADOR,
            Perfil.RESPONSAVEL_QUALIDADE,
            Perfil.RESPONSAVEL_TECNICO,
        ]

    def pode_gerenciar_usuarios(self) -> bool:
        return self.perfil == Perfil.ADMINISTRADOR

    def pode_exportar(self) -> bool:
        return self.perfil in [
            Perfil.ADMINISTRADOR,
            Perfil.RESPONSAVEL_QUALIDADE,
            Perfil.RESPONSAVEL_TECNICO,
            Perfil.APROVADOR,
        ]

    def __repr__(self) -> str:
        return f'<Usuario {self.nome} [{self.perfil}]>'


@login_manager.user_loader
def load_user(user_id: str):
    return Usuario.query.get(int(user_id))
