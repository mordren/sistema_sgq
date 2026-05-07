from datetime import datetime
from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


class ListaMestraConfig(db.Model):
    """Single-row table that stores the header metadata for the Lista Mestra document.

    There is always exactly one row (id=1).  Use ListaMestraConfig.get() to
    load it, creating it with defaults if it doesn't exist yet.
    """
    __tablename__ = 'lista_mestra_config'

    id = db.Column(db.Integer, primary_key=True)

    titulo = db.Column(
        db.String(200),
        nullable=False,
        default='Lista Mestra de Documentos',
    )
    codigo = db.Column(db.String(50), nullable=False, default='LM-01')
    revisao_num = db.Column(db.Integer, nullable=False, default=0)

    elaborado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    revisado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    aprovado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )

    data_aprovacao = db.Column(db.DateTime, nullable=True)
    atualizado_em = db.Column(
        db.DateTime, nullable=False, default=agora_brasilia
    )

    elaborado_por = db.relationship(
        'Usuario', foreign_keys=[elaborado_por_id], backref='lm_elaboradas'
    )
    revisado_por = db.relationship(
        'Usuario', foreign_keys=[revisado_por_id], backref='lm_revisadas'
    )
    aprovado_por = db.relationship(
        'Usuario', foreign_keys=[aprovado_por_id], backref='lm_aprovadas'
    )

    @property
    def revisao_formatada(self):
        return f'Rev{self.revisao_num:02d}'

    @classmethod
    def get(cls):
        """Return the single config row, creating it with defaults if absent."""
        cfg = cls.query.get(1)
        if cfg is None:
            cfg = cls(
                id=1,
                titulo='Lista Mestra de Documentos',
                codigo='LM-01',
                revisao_num=0,
            )
            db.session.add(cfg)
            db.session.commit()
        return cfg
