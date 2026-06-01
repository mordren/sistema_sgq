"""
Alert system for user-facing notifications.

Alerts persist on the dashboard for a configurable period (default 7 days)
and can be dismissed by users.  Used for events such as:
- "PT X was updated — update OS revisions"
- Important system-wide notices.
"""

from datetime import datetime

from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


class Alerta(db.Model):
    __tablename__ = 'alertas'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mensagem = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(20), default='warning')  # warning, danger, info
    categoria = db.Column(db.String(50), default='')      # e.g. 'pt_alterado'
    criado_em = db.Column(db.DateTime, nullable=False, default=agora_brasilia)
    descartado_por = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    descartado_em = db.Column(db.DateTime, nullable=True)

    # Relationships
    usuario_descarte = db.relationship('Usuario', backref='alertas_descartados', lazy=True)

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def ativo(self):
        """True se não foi descartado."""
        return self.descartado_em is None

    @classmethod
    def alertas_ativos(cls):
        """Retorna alertas dos últimos 7 dias, não-descartados, do mais recente."""
        from datetime import timedelta
        sete_dias_atras = agora_brasilia() - timedelta(days=7)
        return (
            cls.query
            .filter(
                cls.descartado_em.is_(None),
                cls.criado_em >= sete_dias_atras,
            )
            .order_by(cls.criado_em.desc())
            .all()
        )

    @classmethod
    def criar(cls, mensagem, tipo='warning', categoria=''):
        """Cria e persiste um novo alerta."""
        alerta = cls(mensagem=mensagem, tipo=tipo, categoria=categoria)
        db.session.add(alerta)
        db.session.commit()
        return alerta

    def descartar(self, usuario_id):
        """Marca o alerta como descartado pelo usuário."""
        self.descartado_por = usuario_id
        self.descartado_em = agora_brasilia()
        db.session.commit()

    def __repr__(self):
        return f'<Alerta {self.id} [{self.tipo}] {self.mensagem[:50]}...>'
