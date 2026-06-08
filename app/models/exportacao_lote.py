from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


class ExportacaoLote(db.Model):
    """Tracks background PDF export jobs (ZIP of all vigente PDFs)."""

    __tablename__ = 'exportacoes_lote'

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(
        db.String(20), default='processando', nullable=False
    )  # processando | concluido | falhou
    arquivo_zip = db.Column(db.String(500), nullable=True)
    total_documentos = db.Column(db.Integer, default=0, nullable=False)
    tamanho_bytes = db.Column(db.Integer, default=0, nullable=False)
    erro = db.Column(db.Text, nullable=True)

    criado_em = db.Column(db.DateTime, default=agora_brasilia, nullable=False)
    concluido_em = db.Column(db.DateTime, nullable=True)

    criado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    criado_por = db.relationship('Usuario', foreign_keys=[criado_por_id])

    @property
    def status_label(self) -> str:
        labels = {
            'processando': 'Processando...',
            'concluido': 'Concluído',
            'falhou': 'Falhou',
        }
        return labels.get(self.status, self.status)

    @property
    def tamanho_formatado(self) -> str:
        if not self.tamanho_bytes:
            return '—'
        size = self.tamanho_bytes
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} TB'

    def __repr__(self):
        return f'<ExportacaoLote #{self.id} {self.status}>'
