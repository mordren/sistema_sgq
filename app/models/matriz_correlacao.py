from datetime import datetime
from app.extensions import db


class MatrizCorrelacao(db.Model):
    """
    Maps ISO/IEC 17020 normative requirements to internal SGQ documents.

    Example:
        requisito            = 'ISO/IEC 17020 item 8.3'
        descricao_requisito  = 'Controle de documentos'
        documento_id         → PA-02
        formulario_relacionado = 'FOR ADM 05'
        evidencia            = 'Lista Mestra e controle de documentos'
    """

    __tablename__ = 'matriz_correlacao'

    id = db.Column(db.Integer, primary_key=True)
    requisito = db.Column(db.String(100), nullable=False, index=True)
    descricao_requisito = db.Column(db.Text, nullable=True)

    documento_id = db.Column(
        db.Integer, db.ForeignKey('documentos.id'), nullable=True
    )
    formulario_relacionado = db.Column(db.String(100), nullable=True)
    evidencia = db.Column(db.Text, nullable=True)
    observacao = db.Column(db.Text, nullable=True)

    atualizado_em = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f'<MatrizCorrelacao {self.requisito}>'
