from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


class ControleVersaoSoftware(db.Model):
    """Controle de versão de software por equipamento."""

    __tablename__ = 'controle_versao_software'

    id = db.Column(db.Integer, primary_key=True)
    equipamento = db.Column(db.String(200), nullable=False)
    software = db.Column(db.String(200), nullable=False)
    versao = db.Column(db.String(100), nullable=False)

    criado_em = db.Column(db.DateTime, default=agora_brasilia, nullable=False)
    atualizado_em = db.Column(
        db.DateTime,
        default=agora_brasilia,
        onupdate=agora_brasilia,
        nullable=False,
    )

    def __repr__(self):
        return f'<ControleVersaoSoftware {self.equipamento} – {self.software} v{self.versao}>'
