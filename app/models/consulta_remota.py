from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


class ConsultaRemota(db.Model):
    __tablename__ = 'consultas_remotas'
    __table_args__ = (
        db.UniqueConstraint('ano', 'mes', 'quinzena', name='uq_consulta_ano_mes_quinzena'),
    )

    id               = db.Column(db.Integer, primary_key=True)
    ano              = db.Column(db.Integer, nullable=False, index=True)
    mes              = db.Column(db.Integer, nullable=False)   # 1–12
    quinzena         = db.Column(db.Integer, nullable=False)   # 1 ou 2
    verificado       = db.Column(db.Boolean, default=False, nullable=False)
    verificado_em    = db.Column(db.DateTime, nullable=True)
    verificado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    criado_em        = db.Column(db.DateTime, default=agora_brasilia, nullable=False)
    atualizado_em    = db.Column(
        db.DateTime, default=agora_brasilia, onupdate=agora_brasilia, nullable=False
    )

    verificado_por = db.relationship('Usuario', foreign_keys=[verificado_por_id])

    def __repr__(self):
        return f'<ConsultaRemota {self.ano}/{self.mes:02d} Q{self.quinzena}>'
