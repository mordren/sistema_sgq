from datetime import datetime
from app.extensions import db
from app.models.documento import StatusDocumento


class RevisaoDocumento(db.Model):
    __tablename__ = 'revisoes_documentos'

    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(
        db.Integer, db.ForeignKey('documentos.id'), nullable=False, index=True
    )
    numero_revisao = db.Column(db.Integer, nullable=False)

    # ── Change description ─────────────────────────────────────────────────────
    motivo_alteracao = db.Column(db.String(500), nullable=True)
    descricao_alteracao = db.Column(db.Text, nullable=True)

    # ── File paths for this revision ───────────────────────────────────────────
    arquivo_docx = db.Column(db.String(500), nullable=True)
    arquivo_pdf = db.Column(db.String(500), nullable=True)
    # ── Online editor content ─────────────────────────────────────────────────
    # content_mode: 'uploaded_file' | 'online_editor'
    content_html = db.Column(db.Text, nullable=True)
    content_mode = db.Column(db.String(20), nullable=True)

    # ── Revision history metadata ─────────────────────────────────────────────
    item_alterado = db.Column(db.String(200), nullable=True)

    status = db.Column(
        db.String(30), default=StatusDocumento.RASCUNHO, nullable=False
    )

    # ── Responsible users ──────────────────────────────────────────────────────
    elaborado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    revisado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    aprovado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )

    # ── Dates ──────────────────────────────────────────────────────────────────
    data_elaboracao = db.Column(db.DateTime, nullable=True)
    data_revisao = db.Column(db.DateTime, nullable=True)
    data_aprovacao = db.Column(db.DateTime, nullable=True)
    data_publicacao = db.Column(db.DateTime, nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────────
    elaborado_por = db.relationship(
        'Usuario', foreign_keys=[elaborado_por_id], backref='revisoes_elaboradas'
    )
    revisado_por = db.relationship(
        'Usuario', foreign_keys=[revisado_por_id], backref='revisoes_revisadas'
    )
    aprovado_por = db.relationship(
        'Usuario', foreign_keys=[aprovado_por_id], backref='revisoes_aprovadas'
    )

    @property
    def revisao_formatada(self) -> str:
        return f"Rev{self.numero_revisao:02d}"

    @property
    def badge_status(self) -> str:
        from app.models.documento import StatusDocumento
        return StatusDocumento.BADGE.get(self.status, 'secondary')

    def __repr__(self) -> str:
        return (
            f'<RevisaoDocumento doc_id={self.documento_id} '
            f'Rev{self.numero_revisao:02d} [{self.status}]>'
        )
