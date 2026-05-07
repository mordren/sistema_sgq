from datetime import datetime
from app.extensions import db


class Area:
    TECNICA = 'Técnica'
    ADMINISTRATIVA = 'Administrativa'
    DIRECAO = 'Direção'
    RECEPCAO = 'Recepção'
    INSPECAO = 'Inspeção'
    QUALIDADE = 'Qualidade'

    TODAS = [TECNICA, ADMINISTRATIVA, DIRECAO, RECEPCAO, INSPECAO, QUALIDADE]


class TipoDistribuicao:
    FISICA = 'Física'
    ELETRONICA = 'Eletrônica'
    AMBAS = 'Ambas'

    TODOS = [FISICA, ELETRONICA, AMBAS]


class DistribuicaoDocumento(db.Model):
    __tablename__ = 'distribuicoes_documentos'

    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(
        db.Integer, db.ForeignKey('documentos.id'), nullable=False, index=True
    )
    area = db.Column(db.String(30), nullable=False)
    tipo_distribuicao = db.Column(db.String(20), nullable=True)

    # The person who acknowledged receipt
    responsavel_ciencia_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    data_ciencia = db.Column(db.DateTime, nullable=True)
    observacao = db.Column(db.Text, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    responsavel_ciencia = db.relationship(
        'Usuario',
        foreign_keys=[responsavel_ciencia_id],
        backref='distribuicoes_ciencia',
    )

    def __repr__(self) -> str:
        return f'<DistribuicaoDocumento doc_id={self.documento_id} area={self.area}>'
