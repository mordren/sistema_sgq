from datetime import datetime
from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


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
    norma_17020 = db.Column(db.String(100), nullable=True, index=True)
    nit_diois_019 = db.Column(db.String(100), nullable=True)
    nit_diois_008 = db.Column(db.String(100), nullable=True)
    mq = db.Column(db.String(100), nullable=True)
    requisito = db.Column(db.String(100), nullable=False, index=True)
    descricao_requisito = db.Column(db.Text, nullable=True)

    documento_id = db.Column(
        db.Integer, db.ForeignKey('documentos.id'), nullable=True
    )
    procedimentos = db.Column(db.Text, nullable=True)
    formulario_relacionado = db.Column(db.String(100), nullable=True)
    formularios = db.Column(db.Text, nullable=True)
    evidencia = db.Column(db.Text, nullable=True)
    observacao = db.Column(db.Text, nullable=True)

    atualizado_em = db.Column(
        db.DateTime,
        default=agora_brasilia,
        onupdate=agora_brasilia,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f'<MatrizCorrelacao {self.requisito}>'
