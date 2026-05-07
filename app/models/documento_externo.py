from datetime import datetime, date
from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


class DocumentoExterno(db.Model):
    """External normative documents (standards, regulations, portarias, etc.)."""

    __tablename__ = 'documentos_externos'

    id = db.Column(db.Integer, primary_key=True)
    # "Identificação do Documento" — e.g. "Portaria 149/2022", "NBR 14040:2023"
    codigo = db.Column(db.String(50), nullable=True)
    titulo = db.Column(db.String(200), nullable=False)
    orgao_emissor = db.Column(db.String(100), nullable=True)
    revisao = db.Column(db.String(20), nullable=True)
    data_publicacao = db.Column(db.Date, nullable=True)
    # "Vigente" or "Obsoleto"
    status = db.Column(db.String(30), default='Vigente', nullable=False)

    # Link to the original online source
    link_origem = db.Column(db.String(500), nullable=True)
    # Filename of the stored file (in EXTERNOS_DIR)
    arquivo_pdf = db.Column(db.String(500), nullable=True)

    aplicavel = db.Column(db.Boolean, default=True, nullable=False)
    observacao = db.Column(db.Text, nullable=True)

    # Distribution
    distribuicao_tecnica = db.Column(db.Boolean, default=False, nullable=False)
    distribuicao_administrativa = db.Column(db.Boolean, default=False, nullable=False)

    # Who uploaded and when
    enviado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    data_envio = db.Column(db.DateTime, default=agora_brasilia, nullable=False)

    criado_em = db.Column(db.DateTime, default=agora_brasilia, nullable=False)
    atualizado_em = db.Column(
        db.DateTime,
        default=agora_brasilia,
        onupdate=agora_brasilia,
        nullable=False,
    )

    # Relationships
    enviado_por = db.relationship('Usuario', foreign_keys=[enviado_por_id])

    # ── Computed helpers ───────────────────────────────────────────────────────

    @property
    def revisao_ou_na(self) -> str:
        """Return the revision string or 'N/A' when blank."""
        return self.revisao.strip() if self.revisao and self.revisao.strip() else 'N/A'

    @property
    def distribuicao_formatada(self) -> str:
        """Human-readable distribution label."""
        if self.distribuicao_tecnica and self.distribuicao_administrativa:
            return 'Técnica / Administrativa'
        if self.distribuicao_tecnica:
            return 'Técnica'
        if self.distribuicao_administrativa:
            return 'Administrativa'
        return '—'

    def __repr__(self) -> str:
        return f'<DocumentoExterno {self.codigo} – {self.titulo}>'
