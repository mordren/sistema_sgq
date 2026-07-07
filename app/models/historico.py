from datetime import datetime
from app.extensions import db
from app.utils.datetime_utils import agora_brasilia


class AcaoEvento:
    DOCUMENTO_CADASTRADO = 'Documento cadastrado'
    REVISAO_ABERTA = 'Revisão aberta'
    DOCUMENTO_EDITADO = 'Documento editado'
    ENVIADO_PARA_REVISAO = 'Enviado para revisão'
    REVISADO = 'Revisado'
    ENVIADO_PARA_APROVACAO = 'Enviado para aprovação'
    APROVADO = 'Aprovado'
    PUBLICADO_VIGENTE = 'Publicado como vigente'
    REVISAO_ANTERIOR_OBSOLETA = 'Revisão anterior movida para obsoleto'
    PDF_GERADO = 'PDF gerado'
    LISTA_MESTRA_ATUALIZADA = 'Lista Mestra atualizada automaticamente'
    DOCUMENTO_CANCELADO = 'Documento cancelado'
    USUARIO_CRIADO = 'Usuário criado'
    USUARIO_EDITADO = 'Usuário editado'
    ARQUIVO_ENVIADO = 'Arquivo enviado'
    DISTRIBUICAO_REGISTRADA = 'Distribuição registrada'
    CONTEUDO_EDITADO_ONLINE = 'Conteúdo editado online'
    REPROVADO = 'Revisão reprovada'
    DOCUMENTO_EXCLUIDO = 'Documento excluído permanentemente'
    DOCUMENTO_EXTERNO_ADICIONADO = 'Documento externo adicionado'
    DOCUMENTO_EXTERNO_EDITADO = 'Documento externo editado'
    DOCUMENTO_EXTERNO_EXCLUIDO = 'Documento externo excluído'
    SOFTWARE_ADICIONADO = 'Versão de software adicionada'
    SOFTWARE_EDITADO = 'Versão de software editada'
    SOFTWARE_EXCLUIDO = 'Versão de software excluída'
    MATRIZ_ATUALIZADA = 'Matriz de correlação atualizada'
    EXPORTACAO_PDFS_INICIADA = 'Exportação de PDFs em lote iniciada'
    EXPORTACAO_PDFS_CONCLUIDA = 'Exportação de PDFs em lote concluída'
    CONSULTA_REMOTA_VERIFICADA = 'Consulta remota verificada'

    # ── Correção (admin) ───────────────────────────────────────────────────────
    CORRECAO_ABERTA = 'Correção aberta (admin)'
    CORRECAO_EDITADA = 'Correção editada (admin)'
    CORRECAO_ENVIADA_APROVACAO = 'Correção enviada para aprovação'
    CORRECAO_APROVADA = 'Correção aprovada'
    CORRECAO_REPROVADA = 'Correção reprovada'
    CORRECAO_CANCELADA = 'Correção cancelada (admin)'

    # Bootstrap icon name for each action (used in history timeline)
    ICONE = {
        DOCUMENTO_CADASTRADO: 'file-earmark-plus',
        REVISAO_ABERTA: 'arrow-repeat',
        DOCUMENTO_EDITADO: 'pencil',
        ENVIADO_PARA_REVISAO: 'send',
        REVISADO: 'check-circle',
        ENVIADO_PARA_APROVACAO: 'send-check',
        APROVADO: 'patch-check',
        PUBLICADO_VIGENTE: 'journals',
        REVISAO_ANTERIOR_OBSOLETA: 'archive',
        PDF_GERADO: 'file-pdf',
        LISTA_MESTRA_ATUALIZADA: 'list-check',
        DOCUMENTO_CANCELADO: 'x-circle',
        ARQUIVO_ENVIADO: 'upload',
        DISTRIBUICAO_REGISTRADA: 'diagram-3',
        CONTEUDO_EDITADO_ONLINE: 'pencil-square',
        REPROVADO: 'x-octagon',
        DOCUMENTO_EXCLUIDO: 'trash',
        DOCUMENTO_EXTERNO_ADICIONADO: 'globe2',
        DOCUMENTO_EXTERNO_EDITADO: 'globe2',
        DOCUMENTO_EXTERNO_EXCLUIDO: 'globe2',
        SOFTWARE_ADICIONADO: 'cpu',
        SOFTWARE_EDITADO: 'cpu',
        SOFTWARE_EXCLUIDO: 'cpu',
        MATRIZ_ATUALIZADA: 'grid-3x3-gap',
        EXPORTACAO_PDFS_INICIADA: 'file-zip',
        EXPORTACAO_PDFS_CONCLUIDA: 'file-zip',
        CONSULTA_REMOTA_VERIFICADA: 'globe2',
        CORRECAO_ABERTA: 'pencil-square',
        CORRECAO_EDITADA: 'pencil',
        CORRECAO_ENVIADA_APROVACAO: 'send-check',
        CORRECAO_APROVADA: 'patch-check',
        CORRECAO_REPROVADA: 'x-octagon',
        CORRECAO_CANCELADA: 'x-circle',
    }

    # Bootstrap colour for the timeline icon
    COR = {
        DOCUMENTO_CADASTRADO: 'primary',
        REVISAO_ABERTA: 'warning',
        DOCUMENTO_EDITADO: 'info',
        ENVIADO_PARA_REVISAO: 'info',
        REVISADO: 'success',
        ENVIADO_PARA_APROVACAO: 'primary',
        APROVADO: 'success',
        PUBLICADO_VIGENTE: 'success',
        REVISAO_ANTERIOR_OBSOLETA: 'dark',
        PDF_GERADO: 'danger',
        LISTA_MESTRA_ATUALIZADA: 'success',
        DOCUMENTO_CANCELADO: 'danger',
        ARQUIVO_ENVIADO: 'secondary',
        DISTRIBUICAO_REGISTRADA: 'info',
        CONTEUDO_EDITADO_ONLINE: 'primary',
        REPROVADO: 'danger',
        DOCUMENTO_EXCLUIDO: 'danger',
        DOCUMENTO_EXTERNO_ADICIONADO: 'info',
        DOCUMENTO_EXTERNO_EDITADO: 'info',
        DOCUMENTO_EXTERNO_EXCLUIDO: 'danger',
        SOFTWARE_ADICIONADO: 'primary',
        SOFTWARE_EDITADO: 'primary',
        SOFTWARE_EXCLUIDO: 'danger',
        MATRIZ_ATUALIZADA: 'warning',
        EXPORTACAO_PDFS_INICIADA: 'warning',
        EXPORTACAO_PDFS_CONCLUIDA: 'success',
        CONSULTA_REMOTA_VERIFICADA: 'success',
        CORRECAO_ABERTA: 'warning',
        CORRECAO_EDITADA: 'info',
        CORRECAO_ENVIADA_APROVACAO: 'primary',
        CORRECAO_APROVADA: 'success',
        CORRECAO_REPROVADA: 'danger',
        CORRECAO_CANCELADA: 'danger',
    }


class HistoricoEvento(db.Model):
    __tablename__ = 'historico_eventos'

    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(
        db.Integer, db.ForeignKey('documentos.id'), nullable=True, index=True
    )
    usuario_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=False
    )
    acao = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    data_evento = db.Column(
        db.DateTime, default=agora_brasilia, nullable=False, index=True
    )
    # IPv4 or IPv6 address
    ip_usuario = db.Column(db.String(45), nullable=True)

    @property
    def icone(self) -> str:
        return AcaoEvento.ICONE.get(self.acao, 'info-circle')

    @property
    def cor(self) -> str:
        return AcaoEvento.COR.get(self.acao, 'secondary')

    def __repr__(self) -> str:
        return f'<HistoricoEvento doc_id={self.documento_id} [{self.acao}]>'
