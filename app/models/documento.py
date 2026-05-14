from datetime import datetime
from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


class TipoDocumento:
    MQ = 'MQ'
    PA = 'PA'
    PT = 'PT'
    IT = 'IT'
    FOR_ADM = 'FOR ADM'
    FOR_TEC = 'FOR TEC'
    NORMA_EXTERNA = 'Norma Externa'
    PORTARIA = 'Portaria'
    RESOLUCAO = 'Resolução'
    NIT = 'NIT'
    DOQ = 'DOQ'
    NIE = 'NIE'

    # Types available for new SGQ internal documents
    TODOS = [MQ, PA, PT, IT, FOR_ADM, FOR_TEC]

    LABELS = {
        MQ: 'MQ – Manual da Qualidade',
        PA: 'PA – Procedimento Administrativo',
        PT: 'PT – Procedimento Técnico',
        IT: 'IT – Instrução de Trabalho',
        FOR_ADM: 'FOR ADM – Formulário Administrativo',
        FOR_TEC: 'FOR TEC – Formulário Técnico',
        NORMA_EXTERNA: 'Norma Externa',
        PORTARIA: 'Portaria',
        RESOLUCAO: 'Resolução',
        NIT: 'NIT',
        DOQ: 'DOQ',
        NIE: 'NIE',
    }


class StatusDocumento:
    RASCUNHO = 'Rascunho'
    EM_REVISAO = 'Em revisão'
    AGUARDANDO_REVISAO = 'Aguardando revisão'
    AGUARDANDO_APROVACAO = 'Aguardando aprovação'
    APROVADO = 'Aprovado'
    VIGENTE = 'Vigente'
    OBSOLETO = 'Obsoleto'
    CANCELADO = 'Cancelado'

    TODOS = [
        RASCUNHO, EM_REVISAO, AGUARDANDO_REVISAO, AGUARDANDO_APROVACAO,
        APROVADO, VIGENTE, OBSOLETO, CANCELADO,
    ]

    # Bootstrap badge colour for each status
    BADGE = {
        RASCUNHO: 'secondary',
        EM_REVISAO: 'warning',
        AGUARDANDO_REVISAO: 'info',
        AGUARDANDO_APROVACAO: 'primary',
        APROVADO: 'success',
        VIGENTE: 'success',
        OBSOLETO: 'dark',
        CANCELADO: 'danger',
    }


class Documento(db.Model):
    __tablename__ = 'documentos'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False, index=True)
    titulo = db.Column(db.String(200), nullable=False)
    tipo_documento = db.Column(db.String(20), nullable=False)
    revisao_atual = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(
        db.String(30), default=StatusDocumento.RASCUNHO, nullable=False, index=True
    )
    data_aprovacao = db.Column(db.DateTime, nullable=True)
    data_publicacao = db.Column(db.DateTime, nullable=True)

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

    # ── File paths ─────────────────────────────────────────────────────────────
    caminho_docx_editavel = db.Column(db.String(500), nullable=True)
    caminho_pdf_vigente = db.Column(db.String(500), nullable=True)
    caminho_obsoleto = db.Column(db.String(500), nullable=True)

    # ── Online editor content ──────────────────────────────────────────────────
    # content_mode: 'uploaded_file' | 'online_editor'
    content_html = db.Column(db.Text, nullable=True)
    content_mode = db.Column(db.String(20), nullable=True)

    # ── Revision history metadata ──────────────────────────────────────────────
    descricao_alteracao = db.Column(db.Text, nullable=True)
    item_alterado = db.Column(db.String(200), nullable=True)

    # ── Distribution & training ────────────────────────────────────────────────
    distribuicao_tecnica = db.Column(db.Boolean, default=False, nullable=False)
    distribuicao_administrativa = db.Column(db.Boolean, default=False, nullable=False)
    requer_treinamento = db.Column(db.Boolean, default=False, nullable=False)

    # ── Metadata ───────────────────────────────────────────────────────────────
    requisito_relacionado = db.Column(db.Text, nullable=True)
    matriz_correlacao_json = db.Column(db.Text, nullable=True)
    observacao = db.Column(db.Text, nullable=True)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=agora_brasilia, nullable=False)
    atualizado_em = db.Column(
        db.DateTime,
        default=agora_brasilia,
        onupdate=agora_brasilia,
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    revisoes = db.relationship(
        'RevisaoDocumento',
        backref='documento',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    historico = db.relationship(
        'HistoricoEvento',
        backref='documento',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    distribuicoes = db.relationship(
        'DistribuicaoDocumento',
        backref='documento',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    correlacoes = db.relationship(
        'MatrizCorrelacao',
        backref='documento',
        lazy='dynamic',
    )

    # ── Naming helpers ─────────────────────────────────────────────────────────
    def _titulo_seguro(self, max_len: int = 50) -> str:
        return (
            self.titulo.replace(' ', '_')
            .replace('/', '-')
            .replace('\\', '-')[:max_len]
        )

    def nome_arquivo_pdf(self) -> str:
        return f"{self.codigo}_Rev{self.revisao_atual:02d}_{self._titulo_seguro()}.pdf"

    def nome_arquivo_docx(self) -> str:
        return f"{self.codigo}_Rev{self.revisao_atual:02d}_{self._titulo_seguro()}.docx"

    def nome_arquivo_obsoleto(self, numero_revisao: int) -> str:
        return (
            f"{self.codigo}_Rev{numero_revisao:02d}_{self._titulo_seguro()}_OBSOLETO.pdf"
        )

    @property
    def badge_status(self) -> str:
        return StatusDocumento.BADGE.get(self.status, 'secondary')

    @property
    def revisao_formatada(self) -> str:
        return f"Rev{self.revisao_atual:02d}"

    def __repr__(self) -> str:
        return f'<Documento {self.codigo} Rev{self.revisao_atual:02d} [{self.status}]>'
