import io
import json
import os
import re
import uuid
from datetime import datetime
from types import SimpleNamespace

from flask import (
    render_template, redirect, url_for, flash,
    request, abort, send_file, current_app, Response, jsonify,
)
from flask_login import login_required, current_user
from sqlalchemy import or_, text

from app.documentos import documentos
from werkzeug.utils import secure_filename

from app.documentos.forms import (
    NovoDocumentoForm, EditarDocumentoForm,
    UploadDocxForm, UploadPdfForm, PublicarVigenteForm,
    AbrirRevisaoForm, EnviarAprovacaoForm,
    AprovarRevisaoForm, ReprovarRevisaoForm, PublicarRevisaoForm,
    EditorConteudoForm, ListaMestraConfigForm,
    DocumentoExternoForm,
)
from app.documentos.exportar import (
    gerar_excel_lista_mestra, gerar_pdf_lista_mestra, gerar_csv_lista_mestra,
)
from app.extensions import db
from app.models import Documento, Usuario, HistoricoEvento, RevisaoDocumento, MatrizCorrelacao
from app.models.documento_externo import DocumentoExterno
from app.models.lista_mestra_config import ListaMestraConfig
from app.models.documento import TipoDocumento, StatusDocumento
from app.models.historico import AcaoEvento
from app.models.usuario import Perfil
from app.utils.file_utils import (
    salvar_upload, caminho_seguro, arquivo_existe,
    nome_pdf_vigente, nome_docx_editavel,
    caminho_vigente_pdf, caminho_editavel_docx,
    caminho_em_revisao, caminho_obsoleto, mover_arquivo, copiar_arquivo,
)
from app.utils.datetime_utils import agora_brasilia
from app.utils.historico import registrar_evento


# ── Helpers ────────────────────────────────────────────────────────────────────

def _choices_usuarios(include_empty: bool = True) -> list:
    """Return user choices for WTForms SelectField."""
    usuarios = Usuario.query.filter_by(ativo=True).order_by(Usuario.nome).all()
    choices = [(0, '— Selecione —')] if include_empty else []
    choices += [(u.id, f'{u.nome}  ({u.perfil})') for u in usuarios]
    return choices


def _choices_tipos() -> list:
    return [(t, TipoDocumento.LABELS.get(t, t)) for t in TipoDocumento.TODOS]


def _populate_user_selects(form) -> None:
    """Assign choices to all three user SelectFields."""
    choices = _choices_usuarios()
    form.elaborado_por_id.choices = choices
    form.revisado_por_id.choices = choices
    form.aprovado_por_id.choices = choices


def _ensure_documento_matriz_schema() -> None:
    rows = db.session.execute(text('PRAGMA table_info(documentos)')).fetchall()
    existing = {row[1] for row in rows}
    if 'matriz_correlacao_json' not in existing:
        db.session.execute(
            text('ALTER TABLE documentos ADD COLUMN matriz_correlacao_json TEXT')
        )
        db.session.commit()


def _formularios_choices():
    return (
        Documento.query
        .filter(
            Documento.ativo == True,
            Documento.tipo_documento.in_([TipoDocumento.FOR_ADM, TipoDocumento.FOR_TEC]),
            Documento.status != StatusDocumento.OBSOLETO,
        )
        .order_by(Documento.tipo_documento, Documento.codigo)
        .all()
    )


def _normalize_matriz_json(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        rows = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(rows, list):
        return None

    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {
            'norma_17020': str(row.get('norma_17020') or '').strip(),
            'nit_diois_019': str(row.get('nit_diois_019') or '').strip(),
            'nit_diois_008': str(row.get('nit_diois_008') or '').strip(),
            'mq': str(row.get('mq') or '').strip(),
            'requisito': str(row.get('requisito') or '').strip(),
            'formularios': [],
        }
        formularios = row.get('formularios') or []
        if isinstance(formularios, str):
            formularios = [formularios]
        vistos = set()
        for formulario in formularios:
            codigo = str(formulario or '').strip()
            if codigo and codigo.casefold() not in vistos:
                item['formularios'].append(codigo)
                vistos.add(codigo.casefold())
        if any(item[key] for key in ['norma_17020', 'nit_diois_019', 'nit_diois_008', 'mq', 'requisito']):
            normalized.append(item)

    if not normalized:
        return None
    return json.dumps(normalized, ensure_ascii=False)


def _resumo_requisitos_matriz(matriz_json: str | None, fallback: str | None = None) -> str | None:
    if not matriz_json:
        return (fallback or '').strip() or None
    try:
        rows = json.loads(matriz_json)
    except (TypeError, ValueError):
        return (fallback or '').strip() or None

    requisitos = []
    vistos = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        requisito = str(row.get('requisito') or row.get('mq') or row.get('norma_17020') or '').strip()
        if requisito and requisito.casefold() not in vistos:
            requisitos.append(requisito)
            vistos.add(requisito.casefold())
    return '\n'.join(requisitos) or None


# ── Document list ──────────────────────────────────────────────────────────────

@documentos.route('/', methods=['GET'])
@login_required
def lista():
    tipo_f = request.args.get('tipo', '').strip()
    status_f = request.args.get('status', '').strip()
    q_f = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Documento.query.filter_by(ativo=True)

    if tipo_f:
        query = query.filter(Documento.tipo_documento == tipo_f)
    if status_f:
        query = query.filter(Documento.status == status_f)
    if q_f:
        query = query.filter(
            or_(
                Documento.codigo.ilike(f'%{q_f}%'),
                Documento.titulo.ilike(f'%{q_f}%'),
            )
        )

    pagination = (
        query.order_by(Documento.tipo_documento, Documento.codigo)
        .paginate(page=page, per_page=20, error_out=False)
    )

    return render_template(
        'documentos/lista.html',
        title='Documentos',
        documentos=pagination.items,
        pagination=pagination,
        tipos=TipoDocumento.TODOS,
        status_list=StatusDocumento.TODOS,
        tipo_f=tipo_f,
        status_f=status_f,
        q_f=q_f,
        TipoDocumento=TipoDocumento,
        StatusDocumento=StatusDocumento,
    )


# ── Obsolete documents ─────────────────────────────────────────────────────────

def _parse_obsoleto_filename(filename: str) -> dict:
    match = re.match(
        r'^(?P<codigo>.+?)_Rev(?P<revisao>\d{2})_(?P<titulo>.+?)_OBSOLETO\.pdf$',
        filename,
        flags=re.IGNORECASE,
    )
    if not match:
        return {
            'codigo': '',
            'revisao': '',
            'titulo': os.path.splitext(filename)[0],
        }

    return {
        'codigo': match.group('codigo'),
        'revisao': int(match.group('revisao')),
        'titulo': match.group('titulo').replace('_', ' '),
    }


def _tipo_from_codigo(codigo: str) -> str:
    if not codigo:
        return ''
    for tipo in sorted(TipoDocumento.TODOS, key=len, reverse=True):
        if codigo.upper().startswith(tipo.upper()):
            return tipo
    return codigo.split('-', 1)[0]


def _pdf_obsoleto_com_tarja(caminho_pdf: str):
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception:
        try:
            import PyPDF2
            PdfReader = PyPDF2.PdfReader
            PdfWriter = PyPDF2.PdfWriter
        except Exception:
            return None

    try:
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return None

    try:
        reader = PdfReader(caminho_pdf)
        writer = PdfWriter()

        for page in reader.pages:
            try:
                media = page.mediabox
                width = float(media.width)
                height = float(media.height)
            except Exception:
                from reportlab.lib.pagesizes import A4
                width, height = A4

            packet = io.BytesIO()
            c = rl_canvas.Canvas(packet, pagesize=(width, height))
            c.saveState()
            try:
                c.translate(width / 2, height / 2)
                c.rotate(35)
                c.setFillColorRGB(0.75, 0, 0, alpha=0.18)
                c.setStrokeColorRGB(0.75, 0, 0, alpha=0.35)
                c.setLineWidth(2)
                font_size = min(width, height) * 0.16
                c.setFont('Helvetica-Bold', font_size)
                text = 'OBSOLETO'
                text_width = c.stringWidth(text, 'Helvetica-Bold', font_size)
                pad_x = font_size * 0.28
                pad_y = font_size * 0.22
                c.rect(
                    -text_width / 2 - pad_x,
                    -font_size / 2 - pad_y,
                    text_width + (2 * pad_x),
                    font_size + (2 * pad_y),
                    stroke=1,
                    fill=1,
                )
                c.setFillColorRGB(0.75, 0, 0, alpha=0.55)
                c.drawCentredString(0, -font_size * 0.35, text)
            finally:
                c.restoreState()
            c.save()
            packet.seek(0)

            overlay_page = PdfReader(packet).pages[0]
            try:
                page.merge_page(overlay_page)
            except Exception:
                try:
                    page.mergePage(overlay_page)
                except Exception:
                    pass

            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        return output
    except Exception:
        current_app.logger.exception('Erro ao aplicar tarja de obsoleto')
        return None


@documentos.route('/obsoletos', methods=['GET'])
@login_required
def obsoletos():
    q_f = request.args.get('q', '').strip()
    tipo_f = request.args.get('tipo', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    obsoletos_dir = current_app.config['OBSOLETOS_DIR']
    os.makedirs(obsoletos_dir, exist_ok=True)

    docs_por_codigo = {
        doc.codigo: doc
        for doc in Documento.query.filter_by(ativo=True).all()
    }

    arquivos = []
    for filename in os.listdir(obsoletos_dir):
        if not filename.lower().endswith('.pdf'):
            continue

        caminho = os.path.join(obsoletos_dir, filename)
        if not os.path.isfile(caminho):
            continue

        meta = _parse_obsoleto_filename(filename)
        doc = docs_por_codigo.get(meta['codigo'])
        tipo = doc.tipo_documento if doc else _tipo_from_codigo(meta['codigo'])
        titulo = doc.titulo if doc else meta['titulo']
        stat = os.stat(caminho)

        item = {
            'filename': filename,
            'codigo': meta['codigo'],
            'revisao': meta['revisao'],
            'titulo': titulo,
            'titulo_arquivo': meta['titulo'],
            'tipo_documento': tipo,
            'tamanho': stat.st_size,
            'modificado_em': datetime.fromtimestamp(stat.st_mtime),
            'doc': doc,
        }

        if tipo_f and item['tipo_documento'] != tipo_f:
            continue

        if q_f:
            haystack = ' '.join([
                item['filename'],
                item['codigo'] or '',
                item['titulo'] or '',
                item['titulo_arquivo'] or '',
                item['tipo_documento'] or '',
            ]).lower()
            if q_f.lower() not in haystack:
                continue

        arquivos.append(item)

    arquivos.sort(
        key=lambda item: (
            item['tipo_documento'] or '',
            item['codigo'] or '',
            item['revisao'] if item['revisao'] != '' else -1,
            item['filename'],
        )
    )

    total = len(arquivos)
    pages = max((total + per_page - 1) // per_page, 1)
    if page < 1:
        page = 1
    if page > pages:
        page = pages

    start = (page - 1) * per_page
    itens = arquivos[start:start + per_page]

    return render_template(
        'documentos/obsoletos.html',
        title='Documentos Obsoletos',
        arquivos=itens,
        total=total,
        page=page,
        pages=pages,
        has_prev=page > 1,
        has_next=page < pages,
        prev_num=page - 1,
        next_num=page + 1,
        tipos=TipoDocumento.TODOS,
        tipo_f=tipo_f,
        q_f=q_f,
    )


@documentos.route('/obsoletos/download/<path:filename>', methods=['GET'])
@login_required
def download_obsoleto(filename):
    try:
        caminho = caminho_seguro(current_app.config['OBSOLETOS_DIR'], filename)
    except ValueError:
        abort(400)

    if not arquivo_existe(caminho):
        flash('Arquivo obsoleto não encontrado.', 'danger')
        return redirect(url_for('documentos.obsoletos'))

    pdf_com_tarja = _pdf_obsoleto_com_tarja(caminho)

    return send_file(
        pdf_com_tarja or caminho,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=os.path.basename(filename),
    )


# ── Matriz de Correlação ───────────────────────────────────────────────────────

def _ensure_matriz_correlacao_schema() -> None:
    required_columns = {
        'norma_17020': 'VARCHAR(100)',
        'nit_diois_019': 'VARCHAR(100)',
        'nit_diois_008': 'VARCHAR(100)',
        'mq': 'VARCHAR(100)',
        'procedimentos': 'TEXT',
        'formularios': 'TEXT',
    }
    rows = db.session.execute(text('PRAGMA table_info(matriz_correlacao)')).fetchall()
    existing = {row[1] for row in rows}
    for column, column_type in required_columns.items():
        if column not in existing:
            db.session.execute(
                text(f'ALTER TABLE matriz_correlacao ADD COLUMN {column} {column_type}')
            )
    db.session.commit()


def _matriz_documentos_choices():
    return (
        Documento.query
        .filter(
            Documento.ativo == True,
            Documento.status != StatusDocumento.OBSOLETO,
        )
        .order_by(Documento.tipo_documento, Documento.codigo)
        .all()
    )


def _split_requisitos_relacionados(valor: str | None) -> list[str]:
    if not valor:
        return []

    requisitos = []
    vistos = set()
    for linha in re.split(r'[\r\n;]+', valor):
        requisito = linha.strip()
        if not requisito or requisito.lower() in {'n/a', 'na', 'não aplicável', 'nao aplicavel'}:
            continue
        chave = requisito.casefold()
        if chave not in vistos:
            requisitos.append(requisito)
            vistos.add(chave)
    return requisitos


def _doc_matriz_label(doc: Documento) -> str:
    return f'{doc.codigo} - {doc.titulo}'


def _add_unique(lista: list[str], valor: str) -> None:
    if valor and valor not in lista:
        lista.append(valor)


def _classificar_documento_na_matriz(doc: Documento, requisito: str, linha: dict) -> None:
    codigo = (doc.codigo or '').upper()
    titulo = (doc.titulo or '').upper()
    tipo = doc.tipo_documento
    label = _doc_matriz_label(doc)

    if tipo == TipoDocumento.MQ:
        _add_unique(linha['mq'], label)
    elif tipo in {TipoDocumento.PA, TipoDocumento.PT, TipoDocumento.IT}:
        _add_unique(linha['procedimentos'], label)
    elif tipo in {TipoDocumento.FOR_ADM, TipoDocumento.FOR_TEC}:
        _add_unique(linha['formularios'], label)
    elif tipo == TipoDocumento.NORMA_EXTERNA and '17020' in f'{codigo} {titulo}':
        _add_unique(linha['norma_17020'], requisito)
    elif tipo == TipoDocumento.NIT and '019' in f'{codigo} {titulo}':
        _add_unique(linha['nit_diois_019'], requisito)
    elif tipo == TipoDocumento.NIT and '008' in f'{codigo} {titulo}':
        _add_unique(linha['nit_diois_008'], requisito)
    elif tipo == TipoDocumento.NIT:
        _add_unique(linha['nit_diois_019'], f'{doc.codigo}: {requisito}')
    else:
        _add_unique(linha['procedimentos'], label)


def _gerar_matriz_correlacao_automatica(q_f: str = '', doc_f: int = 0) -> list[SimpleNamespace]:
    _ensure_documento_matriz_schema()
    documentos = (
        Documento.query
        .filter(
            Documento.ativo == True,
            Documento.status != StatusDocumento.OBSOLETO,
        )
        .order_by(Documento.tipo_documento, Documento.codigo)
        .all()
    )

    linhas = {}
    for doc in documentos:
        if doc_f and doc.id != doc_f:
            continue

        structured_rows = []
        if doc.matriz_correlacao_json:
            try:
                loaded_rows = json.loads(doc.matriz_correlacao_json)
            except (TypeError, ValueError):
                loaded_rows = []
            if isinstance(loaded_rows, list):
                structured_rows = [row for row in loaded_rows if isinstance(row, dict)]

        if structured_rows:
            iterable_rows = structured_rows
        else:
            iterable_rows = [
                {'requisito': requisito}
                for requisito in _split_requisitos_relacionados(doc.requisito_relacionado)
            ]

        for row in iterable_rows:
            requisito = str(row.get('requisito') or row.get('mq') or row.get('norma_17020') or '').strip()
            if not requisito:
                continue
            norma_17020 = str(row.get('norma_17020') or '').strip()
            nit_diois_019 = str(row.get('nit_diois_019') or '').strip()
            nit_diois_008 = str(row.get('nit_diois_008') or '').strip()
            mq = str(row.get('mq') or '').strip()
            formularios = row.get('formularios') or []
            if isinstance(formularios, str):
                formularios = [formularios]

            chave = '|'.join([
                norma_17020.casefold(),
                nit_diois_019.casefold(),
                nit_diois_008.casefold(),
                mq.casefold(),
                requisito.casefold(),
            ])
            linha = linhas.setdefault(
                chave,
                {
                    'norma_17020': [],
                    'nit_diois_019': [],
                    'nit_diois_008': [],
                    'mq': [],
                    'requisito': requisito,
                    'descricao_requisito': '',
                    'procedimentos': [],
                    'formularios': [],
                },
            )
            _add_unique(linha['norma_17020'], norma_17020)
            _add_unique(linha['nit_diois_019'], nit_diois_019)
            _add_unique(linha['nit_diois_008'], nit_diois_008)
            _add_unique(linha['mq'], mq)
            _classificar_documento_na_matriz(doc, requisito, linha)
            for formulario in formularios:
                _add_unique(linha['formularios'], str(formulario or '').strip())

    itens = []
    busca = q_f.casefold()
    for linha in linhas.values():
        item = SimpleNamespace(
            norma_17020='\n'.join(linha['norma_17020']),
            nit_diois_019='\n'.join(linha['nit_diois_019']),
            nit_diois_008='\n'.join(linha['nit_diois_008']),
            mq='\n'.join(linha['mq']),
            requisito=linha['requisito'],
            descricao_requisito=linha['descricao_requisito'],
            procedimentos='\n'.join(linha['procedimentos']),
            formularios='\n'.join(linha['formularios']),
        )
        if busca:
            haystack = '\n'.join([
                item.norma_17020,
                item.nit_diois_019,
                item.nit_diois_008,
                item.mq,
                item.requisito,
                item.procedimentos,
                item.formularios,
            ]).casefold()
            if busca not in haystack:
                continue
        itens.append(item)

    return sorted(
        itens,
        key=lambda item: (
            item.norma_17020 or item.requisito,
            item.mq or '',
            item.requisito,
        ),
    )


@documentos.route('/matriz-correlacao', methods=['GET', 'POST'])
@login_required
def matriz_correlacao():
    _ensure_matriz_correlacao_schema()
    _ensure_documento_matriz_schema()

    if request.method == 'POST':
        flash('A matriz é gerada automaticamente pelos requisitos cadastrados nos documentos.', 'info')
        return redirect(url_for('documentos.matriz_correlacao'))

    q_f = request.args.get('q', '').strip()
    doc_f = request.args.get('documento_id', type=int)

    documentos_choices = _matriz_documentos_choices()
    itens = _gerar_matriz_correlacao_automatica(q_f=q_f, doc_f=doc_f or 0)

    return render_template(
        'documentos/matriz_correlacao.html',
        title='Matriz de Correlação',
        itens=itens,
        documentos_choices=documentos_choices,
        q_f=q_f,
        doc_f=doc_f or 0,
        pode_editar=current_user.pode_editar_documentos(),
    )


@documentos.route('/matriz-correlacao/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_matriz_correlacao(id):
    if not current_user.pode_editar_documentos():
        abort(403)

    item = MatrizCorrelacao.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash('Item removido da matriz.', 'success')
    return redirect(url_for('documentos.matriz_correlacao'))


# ── Lista Mestra ───────────────────────────────────────────────────────────────

@documentos.route('/lista-mestra', methods=['GET'])
@login_required
def lista_mestra():
    # Show all documents that have a published PDF regardless of current
    # workflow state (a doc "Em revisão" still has its old Vigente PDF valid).
    _excluidos = [
        StatusDocumento.RASCUNHO,
        StatusDocumento.OBSOLETO,
        StatusDocumento.CANCELADO,
    ]
    docs = (
        Documento.query
        .filter(
            Documento.ativo == True,
            Documento.caminho_pdf_vigente.isnot(None),
            Documento.status.notin_(_excluidos),
        )
        .order_by(Documento.tipo_documento, Documento.codigo)
        .all()
    )
    cfg = ListaMestraConfig.get()
    pode_configurar = current_user.pode_aprovar() or current_user.perfil == Perfil.ADMINISTRADOR
    docs_externos = (
        DocumentoExterno.query
        .filter_by(status='Vigente')
        .order_by(DocumentoExterno.orgao_emissor, DocumentoExterno.codigo)
        .all()
    )
    return render_template(
        'documentos/lista_mestra.html',
        title='Lista Mestra',
        documentos=docs,
        total=len(docs),
        gerado_em=agora_brasilia(),
        TipoDocumento=TipoDocumento,
        cfg=cfg,
        pode_configurar=pode_configurar,
        docs_externos=docs_externos,
    )


@documentos.route('/lista-mestra/exportar/<formato>', methods=['GET'])
@login_required
def exportar_lista_mestra(formato):
    if not current_user.pode_exportar():
        abort(403)

    docs = (
        Documento.query
        .filter_by(status=StatusDocumento.VIGENTE, ativo=True)
        .order_by(Documento.tipo_documento, Documento.codigo)
        .all()
    )
    docs_externos_exp = (
        DocumentoExterno.query
        .filter_by(status='Vigente')
        .order_by(DocumentoExterno.orgao_emissor, DocumentoExterno.codigo)
        .all()
    )

    stamp = agora_brasilia().strftime('%Y%m%d_%H%M')
    fmt = formato.lower()
    cfg = ListaMestraConfig.get()

    if fmt == 'excel':
        output = gerar_excel_lista_mestra(docs, externos=docs_externos_exp)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'lista_mestra_{stamp}.xlsx',
        )
    elif fmt == 'pdf':
        output = gerar_pdf_lista_mestra(docs, cfg=cfg, externos=docs_externos_exp)
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'lista_mestra_{stamp}.pdf',
        )
    elif fmt == 'csv':
        csv_str = gerar_csv_lista_mestra(docs, externos=docs_externos_exp)
        return Response(
            csv_str.encode('utf-8-sig'),
            mimetype='text/csv; charset=utf-8-sig',
            headers={
                'Content-Disposition': f'attachment; filename=lista_mestra_{stamp}.csv'
            },
        )
    else:
        abort(404)


# ── Configurar Lista Mestra ────────────────────────────────────────────────────

@documentos.route('/lista-mestra/configurar', methods=['GET', 'POST'])
@login_required
def configurar_lista_mestra():
    """Edit the Lista Mestra document header metadata."""
    if not (current_user.pode_aprovar() or current_user.perfil == Perfil.ADMINISTRADOR):
        abort(403)

    cfg = ListaMestraConfig.get()
    todos_usuarios = (
        Usuario.query.filter(Usuario.ativo == True).order_by(Usuario.nome).all()
    )
    opcoes_usuario = [(0, '— Selecione —')] + [(u.id, u.nome) for u in todos_usuarios]

    form = ListaMestraConfigForm(obj=cfg)
    form.elaborado_por_id.choices = opcoes_usuario
    form.revisado_por_id.choices = opcoes_usuario
    form.aprovado_por_id.choices = opcoes_usuario

    if form.validate_on_submit():
        cfg.titulo = form.titulo.data.strip()
        cfg.codigo = form.codigo.data.strip().upper()
        cfg.revisao_num = form.revisao_num.data
        cfg.elaborado_por_id = form.elaborado_por_id.data or None
        cfg.revisado_por_id = form.revisado_por_id.data or None
        cfg.aprovado_por_id = form.aprovado_por_id.data or None
        cfg.atualizado_em = agora_brasilia()
        db.session.commit()
        flash('Configuração da Lista Mestra salva com sucesso!', 'success')
        return redirect(url_for('documentos.lista_mestra'))

    if request.method == 'GET':
        form.elaborado_por_id.data = cfg.elaborado_por_id or 0
        form.revisado_por_id.data = cfg.revisado_por_id or 0
        form.aprovado_por_id.data = cfg.aprovado_por_id or 0

    return render_template(
        'documentos/configurar_lista_mestra.html',
        title='Configurar Lista Mestra',
        form=form,
        cfg=cfg,
    )


# ── New document ───────────────────────────────────────────────────────────────

@documentos.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if not current_user.pode_editar_documentos():
        abort(403)

    _ensure_documento_matriz_schema()
    form = NovoDocumentoForm()
    form.tipo_documento.choices = _choices_tipos()
    _populate_user_selects(form)
    formularios_choices = _formularios_choices()

    if form.validate_on_submit():
        codigo = form.codigo.data.strip().upper()
        matriz_json = _normalize_matriz_json(form.matriz_correlacao_json.data)

        # Duplicate código check
        if Documento.query.filter_by(codigo=codigo).first():
            flash(f'Já existe um documento com o código {codigo}.', 'danger')
            return render_template(
                'documentos/novo.html',
                title='Novo Documento',
                form=form,
                formularios_choices=formularios_choices,
            )

        doc = Documento(
            codigo=codigo,
            titulo=form.titulo.data.strip(),
            tipo_documento=form.tipo_documento.data,
            revisao_atual=form.revisao_inicial.data,
            status=StatusDocumento.RASCUNHO,
            elaborado_por_id=form.elaborado_por_id.data or None,
            revisado_por_id=form.revisado_por_id.data or None,
            aprovado_por_id=form.aprovado_por_id.data or None,
            requisito_relacionado=_resumo_requisitos_matriz(
                matriz_json,
                form.requisito_relacionado.data,
            ),
            matriz_correlacao_json=matriz_json,
            distribuicao_tecnica=form.distribuicao_tecnica.data,
            distribuicao_administrativa=form.distribuicao_administrativa.data,
            requer_treinamento=form.requer_treinamento.data,
            observacao=form.observacao.data.strip() or None,
        )
        db.session.add(doc)
        db.session.flush()  # get doc.id before saving files

        # Handle DOCX upload
        if form.arquivo_docx.data and form.arquivo_docx.data.filename:
            nome_dx = nome_docx_editavel(doc.codigo, doc.revisao_atual, doc.titulo)
            salvar_upload(
                form.arquivo_docx.data,
                current_app.config['EDITAVEIS_DOCX_DIR'],
                nome_dx,
            )
            doc.caminho_docx_editavel = nome_dx
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.ARQUIVO_ENVIADO,
                f'DOCX enviado: {nome_dx}',
            )

        # Handle PDF upload
        if form.arquivo_pdf.data and form.arquivo_pdf.data.filename:
            nome_px = nome_pdf_vigente(doc.codigo, doc.revisao_atual, doc.titulo)
            salvar_upload(
                form.arquivo_pdf.data,
                current_app.config['VIGENTES_PDF_DIR'],
                nome_px,
            )
            doc.caminho_pdf_vigente = nome_px
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.ARQUIVO_ENVIADO,
                f'PDF enviado: {nome_px}',
            )

        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.DOCUMENTO_CADASTRADO,
            f'Documento {doc.codigo} cadastrado por {current_user.nome}.',
        )
        db.session.commit()

        flash(f'Documento {doc.codigo} cadastrado com sucesso!', 'success')
        return redirect(url_for('documentos.detalhe', id=doc.id))

    return render_template(
        'documentos/novo.html',
        title='Novo Documento',
        form=form,
        formularios_choices=formularios_choices,
    )


# ── Document detail ────────────────────────────────────────────────────────────

@documentos.route('/<int:id>', methods=['GET'])
@login_required
def detalhe(id):
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    historico = (
        HistoricoEvento.query
        .filter_by(documento_id=id)
        .order_by(HistoricoEvento.data_evento.desc())
        .all()
    )
    revisoes = (
        RevisaoDocumento.query
        .filter_by(documento_id=id)
        .order_by(RevisaoDocumento.numero_revisao.desc())
        .all()
    )

    # Active (in-progress) revision — the one not yet Vigente/Obsoleto/Cancelado
    _estados_finais = [
        StatusDocumento.VIGENTE, StatusDocumento.OBSOLETO, StatusDocumento.CANCELADO
    ]
    revisao_ativa = (
        RevisaoDocumento.query
        .filter(
            RevisaoDocumento.documento_id == id,
            RevisaoDocumento.status.notin_(_estados_finais),
        )
        .order_by(RevisaoDocumento.numero_revisao.desc())
        .first()
    )

    # ── Forms ──────────────────────────────────────────────────────────────────
    upload_docx_form = UploadDocxForm()
    upload_pdf_form = UploadPdfForm()
    publicar_form = PublicarVigenteForm()
    abrir_revisao_form = AbrirRevisaoForm()
    aprovar_form = AprovarRevisaoForm()
    reprovar_form = ReprovarRevisaoForm()
    publicar_revisao_form = PublicarRevisaoForm()

    aprovadores = (
        Usuario.query
        .filter(
            Usuario.ativo == True,
            Usuario.perfil.in_([Perfil.APROVADOR, Perfil.ADMINISTRADOR]),
        )
        .order_by(Usuario.nome)
        .all()
    )
    todos_usuarios = (
        Usuario.query
        .filter(Usuario.ativo == True)
        .order_by(Usuario.nome)
        .all()
    )
    publicar_form.aprovado_por_id.choices = [(u.id, u.nome) for u in aprovadores]
    aprovar_form.aprovado_por_id.choices = [(u.id, u.nome) for u in aprovadores]
    aprovar_form.elaborado_por_id.choices = [(u.id, u.nome) for u in todos_usuarios]
    aprovar_form.revisado_por_id.choices = [(u.id, u.nome) for u in todos_usuarios]

    # Pre-fill from existing revision data
    if revisao_ativa:
        if revisao_ativa.elaborado_por_id and not aprovar_form.elaborado_por_id.data:
            aprovar_form.elaborado_por_id.data = revisao_ativa.elaborado_por_id
        if revisao_ativa.revisado_por_id and not aprovar_form.revisado_por_id.data:
            aprovar_form.revisado_por_id.data = revisao_ativa.revisado_por_id
        if revisao_ativa.aprovado_por_id and not aprovar_form.aprovado_por_id.data:
            aprovar_form.aprovado_por_id.data = revisao_ativa.aprovado_por_id
    # Pre-fill approver for vigente publish form
    if doc.aprovado_por_id and not publicar_form.aprovado_por_id.data:
        publicar_form.aprovado_por_id.data = doc.aprovado_por_id

    # ── Permissions ────────────────────────────────────────────────────────────
    pode_editar = current_user.pode_editar_documentos()
    pode_publicar = (
        (current_user.pode_abrir_revisao() or current_user.pode_aprovar())
        and doc.status in [StatusDocumento.RASCUNHO, StatusDocumento.APROVADO]
        and revisao_ativa is None  # only for simple import path (Rascunho→Vigente)
    )
    pode_ver_docx = current_user.pode_editar_documentos()
    tem_aprovadores = len(aprovadores) > 0

    # Debug: log the publishability state to help diagnose client issues
    current_app.logger.debug(
        'detalhe page: pode_publicar=%s, tem_aprovadores=%s, caminho_pdf_vigente=%s, has_content_html=%s',
        pode_publicar, tem_aprovadores, doc.caminho_pdf_vigente, bool(doc.content_html),
    )

    return render_template(
        'documentos/detalhe.html',
        title=f'{doc.codigo} – {doc.titulo}',
        doc=doc,
        historico=historico,
        revisoes=revisoes,
        revisao_ativa=revisao_ativa,
        upload_docx_form=upload_docx_form,
        upload_pdf_form=upload_pdf_form,
        publicar_form=publicar_form,
        abrir_revisao_form=abrir_revisao_form,
        enviar_aprovacao_form=None,
        aprovar_form=aprovar_form,
        reprovar_form=reprovar_form,
        publicar_revisao_form=publicar_revisao_form,
        pode_editar=pode_editar,
        pode_publicar=pode_publicar,
        pode_ver_docx=pode_ver_docx,
        tem_aprovadores=tem_aprovadores,
        pode_abrir_revisao=current_user.pode_abrir_revisao(),
        pode_revisar=current_user.pode_revisar(),
        pode_aprovar_doc=current_user.pode_aprovar(),
        StatusDocumento=StatusDocumento,
        TipoDocumento=TipoDocumento,
    )


# ── Edit document metadata ─────────────────────────────────────────────────────

@documentos.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status == StatusDocumento.VIGENTE:
        flash(
            'Para alterar um documento vigente, abra uma nova revisão primeiro.',
            'warning',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    _ensure_documento_matriz_schema()
    form = EditarDocumentoForm(obj=doc)
    form.tipo_documento.choices = _choices_tipos()
    _populate_user_selects(form)
    formularios_choices = _formularios_choices()

    if form.validate_on_submit():
        matriz_json = _normalize_matriz_json(form.matriz_correlacao_json.data)
        doc.titulo = form.titulo.data.strip()
        doc.tipo_documento = form.tipo_documento.data
        doc.elaborado_por_id = form.elaborado_por_id.data or None
        doc.revisado_por_id = form.revisado_por_id.data or None
        doc.aprovado_por_id = form.aprovado_por_id.data or None
        doc.requisito_relacionado = _resumo_requisitos_matriz(
            matriz_json,
            form.requisito_relacionado.data,
        )
        doc.matriz_correlacao_json = matriz_json
        doc.distribuicao_tecnica = form.distribuicao_tecnica.data
        doc.distribuicao_administrativa = form.distribuicao_administrativa.data
        doc.requer_treinamento = form.requer_treinamento.data
        doc.observacao = form.observacao.data.strip() or None
        doc.atualizado_em = agora_brasilia()

        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.DOCUMENTO_EDITADO,
            f'Metadados editados por {current_user.nome}.',
        )
        db.session.commit()

        flash('Documento atualizado com sucesso!', 'success')
        return redirect(url_for('documentos.detalhe', id=id))

    if request.method == 'POST' and form.errors:
        erros = '; '.join(
            f'{field}: {', '.join(errs)}'
            for field, errs in form.errors.items()
        )
        current_app.logger.warning('editar validation failed: %s', erros)
        flash(f'Erro ao salvar: {erros}', 'danger')

    # Pre-populate optional selects with stored value (or 0 for empty)
    if request.method == 'GET':
        form.elaborado_por_id.data = doc.elaborado_por_id or 0
        form.revisado_por_id.data = doc.revisado_por_id or 0
        form.aprovado_por_id.data = doc.aprovado_por_id or 0
        form.matriz_correlacao_json.data = doc.matriz_correlacao_json or ''

    return render_template(
        'documentos/editar.html',
        title=f'Editar – {doc.codigo}',
        form=form,
        doc=doc,
        formularios_choices=formularios_choices,
    )


# ── Upload DOCX ────────────────────────────────────────────────────────────────

@documentos.route('/<int:id>/upload-docx', methods=['POST'])
@login_required
def upload_docx(id):
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status == StatusDocumento.VIGENTE:
        flash(
            'Não é possível substituir o DOCX de um documento vigente. '
            'Abra uma nova revisão.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    form = UploadDocxForm()
    if form.validate_on_submit():
        nome = nome_docx_editavel(doc.codigo, doc.revisao_atual, doc.titulo)
        salvar_upload(
            form.arquivo_docx.data,
            current_app.config['EDITAVEIS_DOCX_DIR'],
            nome,
        )
        doc.caminho_docx_editavel = nome
        doc.atualizado_em = agora_brasilia()

        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.ARQUIVO_ENVIADO,
            f'DOCX enviado/atualizado: {nome}',
        )
        db.session.commit()
        flash('Arquivo DOCX enviado com sucesso!', 'success')
    else:
        flash('Erro no envio: selecione um arquivo .docx válido.', 'danger')

    return redirect(url_for('documentos.detalhe', id=id))


# ── Upload PDF ─────────────────────────────────────────────────────────────────

@documentos.route('/<int:id>/upload-pdf', methods=['POST'])
@login_required
def upload_pdf(id):
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status == StatusDocumento.VIGENTE:
        flash(
            'Não é possível substituir o PDF de um documento vigente. '
            'Abra uma nova revisão.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    form = UploadPdfForm()
    if form.validate_on_submit():
        nome = nome_pdf_vigente(doc.codigo, doc.revisao_atual, doc.titulo)
        salvar_upload(
            form.arquivo_pdf.data,
            current_app.config['VIGENTES_PDF_DIR'],
            nome,
        )
        doc.caminho_pdf_vigente = nome
        doc.atualizado_em = agora_brasilia()

        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.ARQUIVO_ENVIADO,
            f'PDF enviado/atualizado: {nome}',
        )
        db.session.commit()
        flash('Arquivo PDF enviado com sucesso!', 'success')
    else:
        flash('Erro no envio: selecione um arquivo .pdf válido.', 'danger')

    return redirect(url_for('documentos.detalhe', id=id))


# ── Publicar como Vigente (Etapa 2 simplified import path) ────────────────────

@documentos.route('/<int:id>/publicar-vigente', methods=['POST'])
@login_required
def publicar_vigente(id):
    if not (current_user.pode_abrir_revisao() or current_user.pode_aprovar()):
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status not in [StatusDocumento.RASCUNHO, StatusDocumento.APROVADO]:
        flash(
            'Apenas documentos em Rascunho ou Aprovado podem ser publicados como Vigente.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    tem_conteudo = doc.caminho_pdf_vigente or (
        doc.content_mode == 'online_editor' and doc.content_html
    )
    if not tem_conteudo:
        flash(
            'É necessário enviar um PDF ou criar conteúdo pelo editor online '
            'antes de publicar como Vigente.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    aprovadores = (
        Usuario.query
        .filter(
            Usuario.ativo == True,
            Usuario.perfil.in_([Perfil.APROVADOR, Perfil.ADMINISTRADOR]),
        )
        .all()
    )

    form = PublicarVigenteForm()
    form.aprovado_por_id.choices = [(u.id, u.nome) for u in aprovadores]

    # Debug log incoming request/form to help diagnose silent failures
    current_app.logger.debug(
        'publicar_vigente called', extra={
            'user_id': getattr(current_user, 'id', None),
            'form_keys': list(request.form.keys()),
        }
    )

    if form.validate_on_submit():
        agora = agora_brasilia()

        # Generate PDF from online content if needed
        if doc.content_mode == 'online_editor' and doc.content_html:
            from app.utils.html_pdf import gerar_pdf_de_html, metadata_from_documento
            doc.aprovado_por_id = form.aprovado_por_id.data
            doc.data_aprovacao = agora
            meta = metadata_from_documento(doc)
            meta['status'] = StatusDocumento.VIGENTE
            meta['historico_revisoes'] = _build_historico_revisoes(doc)
            nome_pdf_out = nome_pdf_vigente(doc.codigo, doc.revisao_atual, doc.titulo)
            caminho_pdf_out = caminho_vigente_pdf(nome_pdf_out)
            ok = gerar_pdf_de_html(doc.content_html, meta, caminho_pdf_out)
            if ok:
                doc.caminho_pdf_vigente = nome_pdf_out
            else:
                flash('Aviso: não foi possível gerar o PDF automaticamente.', 'warning')

        doc.status = StatusDocumento.VIGENTE
        if not doc.aprovado_por_id:
            doc.aprovado_por_id = form.aprovado_por_id.data
        doc.data_aprovacao = doc.data_aprovacao or agora
        doc.data_publicacao = agora
        doc.atualizado_em = agora

        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.PUBLICADO_VIGENTE,
            form.motivo.data,
        )
        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.LISTA_MESTRA_ATUALIZADA,
            'Lista Mestra atualizada automaticamente após publicação.',
        )
        db.session.commit()

        flash(
            f'Documento {doc.codigo} publicado como Vigente com sucesso! '
            'A Lista Mestra foi atualizada automaticamente.',
            'success',
        )
    else:
        # Provide clearer feedback when validation fails or data missing
        if form.errors:
            erros = '; '.join(
                f'{field}: {", ".join(errs)}'
                for field, errs in form.errors.items()
            )
            current_app.logger.warning('publicar_vigente validation failed: %s; form=%s', erros, dict(request.form))
            flash(f'Erro na publicação: {erros}', 'danger')
        else:
            # No explicit errors — log form and notify user
            current_app.logger.warning('publicar_vigente submitted but not validated and no form.errors; form=%s', dict(request.form))
            flash('Falha ao publicar: dados do formulário inválidos ou ausentes. Verifique os campos e tente novamente.', 'danger')

    return redirect(url_for('documentos.detalhe', id=id))


# ── File downloads ─────────────────────────────────────────────────────────────

@documentos.route('/<int:id>/pdf', methods=['GET'])
@login_required
def download_pdf(id):
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if not doc.caminho_pdf_vigente:
        flash('Nenhum PDF vigente disponível para este documento.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    # Colaboradores e auditores externos só podem acessar PDFs de documentos publicados
    _status_com_pdf = [
        StatusDocumento.VIGENTE,
        StatusDocumento.EM_REVISAO,
        StatusDocumento.AGUARDANDO_REVISAO,
        StatusDocumento.AGUARDANDO_APROVACAO,
        StatusDocumento.APROVADO,
    ]
    if (
        current_user.perfil in [Perfil.COLABORADOR_CONSULTA, Perfil.AUDITOR_EXTERNO]
        and doc.status not in _status_com_pdf
    ):
        abort(403)

    try:
        caminho = caminho_seguro(
            current_app.config['VIGENTES_PDF_DIR'],
            doc.caminho_pdf_vigente,
        )
    except ValueError:
        abort(400)

    if not arquivo_existe(caminho):
        flash('Arquivo PDF não encontrado no servidor.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))
    # Try to overlay running header onto existing PDF (requires pypdf/PyPDF2 + reportlab)
    try:
        from app.utils.html_pdf import overlay_header_on_pdf, metadata_from_documento, gerar_pdf_de_html
    except Exception:
        overlay_header_on_pdf = None

    if overlay_header_on_pdf:
        meta = metadata_from_documento(doc)
        buf = overlay_header_on_pdf(caminho, meta)
        if buf:
            return send_file(
                buf,
                mimetype='application/pdf',
                as_attachment=False,
                download_name=doc.caminho_pdf_vigente,
            )

        # If overlay failed but we have HTML content, regenerate PDF with header
        if getattr(doc, 'content_html', None):
            try:
                tmp_path = caminho + '.tmp.pdf'
                ok = gerar_pdf_de_html(doc.content_html, metadata_from_documento(doc), tmp_path)
                if ok and os.path.exists(tmp_path):
                    return send_file(
                        tmp_path,
                        mimetype='application/pdf',
                        as_attachment=False,
                        download_name=doc.caminho_pdf_vigente,
                    )
            except Exception:
                current_app.logger.exception('Failed to regenerate PDF with header')

    # Fallback: serve stored PDF as-is
    return send_file(
        caminho,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=doc.caminho_pdf_vigente,
    )


@documentos.route('/<int:id>/docx', methods=['GET'])
@login_required
def download_docx(id):
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if not doc.caminho_docx_editavel:
        flash('Nenhum DOCX disponível para este documento.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    try:
        caminho = caminho_seguro(
            current_app.config['EDITAVEIS_DOCX_DIR'],
            doc.caminho_docx_editavel,
        )
    except ValueError:
        abort(400)

    if not arquivo_existe(caminho):
        flash('Arquivo DOCX não encontrado no servidor.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    return send_file(
        caminho,
        mimetype=(
            'application/vnd.openxmlformats-officedocument'
            '.wordprocessingml.document'
        ),
        as_attachment=True,
        download_name=doc.caminho_docx_editavel,
    )


# ══════════════════════════════════════════════════════════════════════════════
# REVISION WORKFLOW ROUTES
# ══════════════════════════════════════════════════════════════════════════════

# ── Abrir nova revisão ────────────────────────────────────────────────────────

@documentos.route('/<int:id>/abrir-revisao', methods=['POST'])
@login_required
def abrir_revisao(id):
    """Start a new revision from the current Vigente document."""
    if not current_user.pode_abrir_revisao():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status != StatusDocumento.VIGENTE:
        flash(
            'Só é possível abrir revisão em documentos com status Vigente.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    # Check no active revision already in progress
    revisao_ativa = (
        RevisaoDocumento.query
        .filter(
            RevisaoDocumento.documento_id == id,
            RevisaoDocumento.status.notin_([
                StatusDocumento.VIGENTE, StatusDocumento.OBSOLETO,
                StatusDocumento.CANCELADO,
            ]),
        )
        .first()
    )
    if revisao_ativa:
        flash(
            f'Já existe uma revisão em andamento '
            f'(Rev{revisao_ativa.numero_revisao:02d} – {revisao_ativa.status}).',
            'warning',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    form = AbrirRevisaoForm()
    if not form.validate_on_submit():
        flash('Informe o motivo da revisão.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    nova_revisao_num = doc.revisao_atual + 1
    nome_docx = nome_docx_editavel(doc.codigo, nova_revisao_num, doc.titulo)
    em_revisao_dir = current_app.config['EM_REVISAO_DIR']

    # Copy current DOCX to em_revisao/ (or create placeholder)
    origem_docx = None
    if doc.caminho_docx_editavel:
        origem_docx = caminho_seguro(
            current_app.config['EDITAVEIS_DOCX_DIR'],
            doc.caminho_docx_editavel,
        )

    destino_docx = os.path.join(em_revisao_dir, nome_docx)
    if origem_docx and arquivo_existe(origem_docx):
        copiar_arquivo(origem_docx, destino_docx)
    else:
        # No existing DOCX — user must upload one
        nome_docx = None

    revisao = RevisaoDocumento(
        documento_id=doc.id,
        numero_revisao=nova_revisao_num,
        status=StatusDocumento.EM_REVISAO,
        motivo_alteracao=form.motivo.data.strip(),
        elaborado_por_id=current_user.id,
        data_elaboracao=agora_brasilia(),
        arquivo_docx=nome_docx,
        content_html=doc.content_html if doc.content_mode == 'online_editor' else None,
        content_mode=doc.content_mode if doc.content_mode == 'online_editor' else None,
    )
    db.session.add(revisao)

    doc.status = StatusDocumento.EM_REVISAO
    doc.atualizado_em = agora_brasilia()

    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.REVISAO_ABERTA,
        f'Revisão Rev{nova_revisao_num:02d} aberta por {current_user.nome}. '
        f'Motivo: {form.motivo.data.strip()}',
    )
    db.session.commit()

    flash(
        f'Revisão Rev{nova_revisao_num:02d} aberta. '
        'O documento anterior continua vigente até a publicação da nova revisão.',
        'success',
    )
    return redirect(url_for('documentos.detalhe', id=id))


# ── Upload DOCX para revisão em andamento ─────────────────────────────────────

@documentos.route('/<int:id>/revisoes/<int:rev_id>/upload-docx', methods=['POST'])
@login_required
def upload_docx_revisao(id, rev_id):
    """Upload a DOCX file to an in-progress revision."""
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(
        id=rev_id, documento_id=id
    ).first_or_404()

    _editaveis = [StatusDocumento.EM_REVISAO, StatusDocumento.AGUARDANDO_APROVACAO, StatusDocumento.RASCUNHO]
    if revisao.status not in _editaveis:
        flash('Não é possível substituir o DOCX desta revisão no estado atual.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    form = UploadDocxForm()
    if form.validate_on_submit():
        nome = nome_docx_editavel(doc.codigo, revisao.numero_revisao, doc.titulo)
        salvar_upload(
            form.arquivo_docx.data,
            current_app.config['EM_REVISAO_DIR'],
            nome,
        )
        revisao.arquivo_docx = nome
        revisao.status = StatusDocumento.AGUARDANDO_APROVACAO
        doc.status = StatusDocumento.AGUARDANDO_APROVACAO
        doc.atualizado_em = agora_brasilia()
        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.ARQUIVO_ENVIADO,
            f'DOCX Rev{revisao.numero_revisao:02d} enviado por {current_user.nome}. Aguardando aprovação.',
        )
        db.session.commit()
        flash('DOCX enviado. Revisão encaminhada para aprovação.', 'success')
    else:
        flash('Erro no envio: selecione um arquivo .docx válido.', 'danger')

    return redirect(url_for('documentos.detalhe', id=id))


# ── Upload PDF para revisão em andamento ──────────────────────────────────────

@documentos.route('/<int:id>/revisoes/<int:rev_id>/upload-pdf', methods=['POST'])
@login_required
def upload_pdf_revisao(id, rev_id):
    """Upload a PDF file directly to an in-progress revision."""
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(
        id=rev_id, documento_id=id
    ).first_or_404()

    _editaveis = [StatusDocumento.EM_REVISAO, StatusDocumento.AGUARDANDO_APROVACAO, StatusDocumento.RASCUNHO]
    if revisao.status not in _editaveis:
        flash('Não é possível enviar PDF para esta revisão no estado atual.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    form = UploadPdfForm()
    if form.validate_on_submit():
        nome = nome_pdf_vigente(doc.codigo, revisao.numero_revisao, doc.titulo)
        salvar_upload(
            form.arquivo_pdf.data,
            current_app.config['EM_REVISAO_DIR'],
            nome,
        )
        revisao.arquivo_pdf = nome
        revisao.status = StatusDocumento.AGUARDANDO_APROVACAO
        doc.status = StatusDocumento.AGUARDANDO_APROVACAO
        doc.atualizado_em = agora_brasilia()
        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.ARQUIVO_ENVIADO,
            f'PDF Rev{revisao.numero_revisao:02d} enviado por {current_user.nome}. Aguardando aprovação.',
        )
        db.session.commit()
        flash('PDF enviado. Revisão encaminhada para aprovação.', 'success')
    else:
        flash('Erro no envio: selecione um arquivo .pdf válido.', 'danger')

    return redirect(url_for('documentos.detalhe', id=id))


# ── Enviar para aprovação ─────────────────────────────────────────────────────

@documentos.route('/<int:id>/revisoes/<int:rev_id>/enviar-aprovacao', methods=['POST'])
@login_required
def enviar_para_aprovacao(id, rev_id):
    """Transition: Em revisão / Rascunho / Aguardando revisão → Aguardando aprovação."""
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(
        id=rev_id, documento_id=id
    ).first_or_404()

    estados_validos = [
        StatusDocumento.EM_REVISAO,
        StatusDocumento.RASCUNHO,
        StatusDocumento.AGUARDANDO_REVISAO,
    ]
    if revisao.status not in estados_validos:
        flash('Esta revisão não pode ser enviada para aprovação no estado atual.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    revisao.status = StatusDocumento.AGUARDANDO_APROVACAO
    doc.status = StatusDocumento.AGUARDANDO_APROVACAO
    doc.atualizado_em = agora_brasilia()

    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.ENVIADO_PARA_APROVACAO,
        f'Rev{revisao.numero_revisao:02d} enviada para aprovação por {current_user.nome}.',
    )
    db.session.commit()
    flash('Revisão enviada para aprovação.', 'success')
    return redirect(url_for('documentos.detalhe', id=id))


# ── Aprovar revisão ───────────────────────────────────────────────────────────

@documentos.route('/<int:id>/revisoes/<int:rev_id>/aprovar', methods=['POST'])
@login_required
def aprovar_revisao(id, rev_id):
    """Approve and immediately publish revision (Aguardando aprovação → Vigente)."""
    if not current_user.pode_aprovar():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(
        id=rev_id, documento_id=id
    ).first_or_404()

    if revisao.status != StatusDocumento.AGUARDANDO_APROVACAO:
        flash('Esta revisão não está aguardando aprovação.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    form = AprovarRevisaoForm()
    todos_usuarios = (
        Usuario.query
        .filter(Usuario.ativo == True)
        .order_by(Usuario.nome)
        .all()
    )
    aprovadores = [
        u for u in todos_usuarios
        if u.perfil in [Perfil.APROVADOR, Perfil.ADMINISTRADOR]
    ]
    form.elaborado_por_id.choices = [(u.id, u.nome) for u in todos_usuarios]
    form.revisado_por_id.choices = [(u.id, u.nome) for u in todos_usuarios]
    form.aprovado_por_id.choices = [(u.id, u.nome) for u in aprovadores]

    if not form.validate_on_submit():
        flash('Preencha todos os campos de aprovação.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    agora = agora_brasilia()
    vigentes_dir = current_app.config['VIGENTES_PDF_DIR']
    em_revisao_dir = current_app.config['EM_REVISAO_DIR']
    obsoletos_dir = current_app.config['OBSOLETOS_DIR']
    editaveis_dir = current_app.config['EDITAVEIS_DOCX_DIR']

    # ── Set approval metadata ──────────────────────────────────────────────────
    revisao.elaborado_por_id = form.elaborado_por_id.data
    revisao.revisado_por_id = form.revisado_por_id.data
    revisao.aprovado_por_id = form.aprovado_por_id.data
    revisao.data_revisao = agora
    revisao.data_aprovacao = agora

    # ── Generate / copy PDF ────────────────────────────────────────────────────
    pdf_gerado = False
    nome_pdf_novo = nome_pdf_vigente(doc.codigo, revisao.numero_revisao, doc.titulo)

    if revisao.content_mode == 'online_editor' and revisao.content_html:
        from app.utils.html_pdf import gerar_pdf_de_html, metadata_from_revisao
        meta = metadata_from_revisao(doc, revisao)
        meta['status'] = StatusDocumento.VIGENTE
        meta['historico_revisoes'] = _build_historico_revisoes(doc)
        caminho_pdf_out = os.path.join(vigentes_dir, nome_pdf_novo)
        ok = gerar_pdf_de_html(revisao.content_html, meta, caminho_pdf_out)
        if ok:
            pdf_gerado = True
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.PDF_GERADO,
                f'PDF gerado a partir do editor online: {nome_pdf_novo}',
            )
        else:
            flash('Aviso: não foi possível gerar o PDF automaticamente.', 'warning')
    elif revisao.arquivo_pdf:
        src_pdf = os.path.join(em_revisao_dir, revisao.arquivo_pdf)
        if arquivo_existe(src_pdf):
            copiar_arquivo(src_pdf, os.path.join(vigentes_dir, nome_pdf_novo))
            pdf_gerado = True
    elif revisao.arquivo_docx:
        from app.utils.pdf_utils import converter_docx_para_pdf
        caminho_docx_src = os.path.join(em_revisao_dir, revisao.arquivo_docx)
        if arquivo_existe(caminho_docx_src):
            pdf_temp = converter_docx_para_pdf(caminho_docx_src, vigentes_dir)
            if pdf_temp:
                nome_gerado = os.path.basename(pdf_temp)
                if nome_gerado != nome_pdf_novo:
                    mover_arquivo(pdf_temp, os.path.join(vigentes_dir, nome_pdf_novo))
                pdf_gerado = True
                registrar_evento(
                    doc.id, current_user.id,
                    AcaoEvento.PDF_GERADO,
                    f'PDF gerado automaticamente: {nome_pdf_novo}',
                )
            else:
                flash(
                    'LibreOffice não encontrado. Publicação continuará sem PDF automático.',
                    'warning',
                )

    # ── Move previous PDF to obsoletos/ ───────────────────────────────────────
    if doc.caminho_pdf_vigente:
        pdf_anterior = os.path.join(vigentes_dir, doc.caminho_pdf_vigente)
        if arquivo_existe(pdf_anterior):
            nome_obs = doc.nome_arquivo_obsoleto(doc.revisao_atual)
            mover_arquivo(pdf_anterior, os.path.join(obsoletos_dir, nome_obs))
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.REVISAO_ANTERIOR_OBSOLETA,
                f'PDF Rev{doc.revisao_atual:02d} movido para obsoletos: {nome_obs}',
            )

    # ── Move DOCX to editaveis_docx/ ──────────────────────────────────────────
    nome_docx_novo = nome_docx_editavel(doc.codigo, revisao.numero_revisao, doc.titulo)
    if revisao.arquivo_docx:
        src_docx = os.path.join(em_revisao_dir, revisao.arquivo_docx)
        if arquivo_existe(src_docx):
            copiar_arquivo(src_docx, os.path.join(editaveis_dir, nome_docx_novo))

    # ── Update Documento → Vigente ─────────────────────────────────────────────
    revisao_anterior_num = doc.revisao_atual
    doc.revisao_atual = revisao.numero_revisao
    doc.status = StatusDocumento.VIGENTE
    doc.caminho_pdf_vigente = nome_pdf_novo if pdf_gerado else doc.caminho_pdf_vigente
    doc.caminho_docx_editavel = nome_docx_novo
    doc.elaborado_por_id = form.elaborado_por_id.data
    doc.revisado_por_id = form.revisado_por_id.data
    doc.aprovado_por_id = form.aprovado_por_id.data
    doc.data_aprovacao = agora
    doc.data_publicacao = agora
    doc.atualizado_em = agora
    if revisao.content_mode == 'online_editor':
        doc.content_html = revisao.content_html
        doc.content_mode = revisao.content_mode

    # ── Update revision ────────────────────────────────────────────────────────
    revisao.status = StatusDocumento.VIGENTE
    revisao.data_publicacao = agora

    # Mark previous revision as Obsoleto
    RevisaoDocumento.query.filter(
        RevisaoDocumento.documento_id == doc.id,
        RevisaoDocumento.id != revisao.id,
        RevisaoDocumento.numero_revisao == revisao_anterior_num,
    ).update({'status': StatusDocumento.OBSOLETO})

    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.APROVADO,
        f'Rev{revisao.numero_revisao:02d} aprovada por {current_user.nome}. '
        f'Elaborado: {revisao.elaborado_por.nome if revisao.elaborado_por else "-"}, '
        f'Revisado: {revisao.revisado_por.nome if revisao.revisado_por else "-"}, '
        f'Aprovado: {revisao.aprovado_por.nome if revisao.aprovado_por else "-"}.',
    )
    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.PUBLICADO_VIGENTE,
        f'Rev{revisao.numero_revisao:02d} publicada automaticamente após aprovação.',
    )
    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.LISTA_MESTRA_ATUALIZADA,
        'Lista Mestra atualizada automaticamente.',
    )
    db.session.commit()

    flash(
        f'Revisão Rev{revisao.numero_revisao:02d} aprovada e publicada como Vigente!',
        'success',
    )
    return redirect(url_for('documentos.detalhe', id=id))


# ── Reprovar revisão ──────────────────────────────────────────────────────────

@documentos.route('/<int:id>/revisoes/<int:rev_id>/reprovar', methods=['POST'])
@login_required
def reprovar_revisao(id, rev_id):
    """Transition: Aguardando aprovação → Em revisão (with reason)."""
    if not current_user.pode_aprovar():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(
        id=rev_id, documento_id=id
    ).first_or_404()

    if revisao.status != StatusDocumento.AGUARDANDO_APROVACAO:
        flash('Esta revisão não está aguardando aprovação.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    form = ReprovarRevisaoForm()
    if not form.validate_on_submit():
        flash('Informe o motivo da reprovação.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    revisao.status = StatusDocumento.EM_REVISAO
    doc.status = StatusDocumento.EM_REVISAO
    doc.atualizado_em = agora_brasilia()

    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.REPROVADO,
        f'Rev{revisao.numero_revisao:02d} reprovada por {current_user.nome}. '
        f'Motivo: {form.motivo.data.strip()}',
    )
    db.session.commit()
    flash('Revisão reprovada. O documento voltou para edição.', 'warning')
    return redirect(url_for('documentos.detalhe', id=id))


# ── Publicar revisão (gera PDF + obsoleta revisão anterior) ──────────────────

@documentos.route('/<int:id>/revisoes/<int:rev_id>/publicar', methods=['POST'])
@login_required
def publicar_revisao(id, rev_id):
    """
    Publish an Approved revision as the new Vigente document.
    - Converts DOCX to PDF (LibreOffice)
    - Moves previous PDF to obsoletos/
    - Updates Documento.revisao_atual and file paths
    - Sets document status to Vigente
    """
    if not (current_user.pode_abrir_revisao() or current_user.pode_aprovar()):
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(
        id=rev_id, documento_id=id
    ).first_or_404()

    if revisao.status != StatusDocumento.APROVADO:
        flash(
            'Somente revisões com status "Aprovado" podem ser publicadas.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    form = PublicarRevisaoForm()
    if not form.validate_on_submit():
        flash('Preencha a descrição das alterações.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    agora = agora_brasilia()
    vigentes_dir = current_app.config['VIGENTES_PDF_DIR']
    em_revisao_dir = current_app.config['EM_REVISAO_DIR']
    obsoletos_dir = current_app.config['OBSOLETOS_DIR']
    editaveis_dir = current_app.config['EDITAVEIS_DOCX_DIR']

    # ── 1. Generate PDF ────────────────────────────────────────────────────────
    pdf_gerado = False
    nome_pdf_novo = nome_pdf_vigente(doc.codigo, revisao.numero_revisao, doc.titulo)

    if revisao.content_mode == 'online_editor' and revisao.content_html:
        # Generate PDF from online HTML content
        from app.utils.html_pdf import gerar_pdf_de_html, metadata_from_revisao
        revisao.aprovado_por_id = revisao.aprovado_por_id  # already set
        meta = metadata_from_revisao(doc, revisao)
        meta['status'] = StatusDocumento.VIGENTE
        meta['historico_revisoes'] = _build_historico_revisoes(doc)
        caminho_pdf_out = os.path.join(vigentes_dir, nome_pdf_novo)
        ok = gerar_pdf_de_html(revisao.content_html, meta, caminho_pdf_out)
        if ok:
            pdf_gerado = True
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.PDF_GERADO,
                f'PDF gerado a partir do editor online: {nome_pdf_novo}',
            )
        else:
            flash(
                'Aviso: não foi possível gerar o PDF automaticamente a partir do conteúdo online.',
                'warning',
            )
    elif revisao.arquivo_pdf:
        # Use the PDF uploaded directly for this revision
        src_pdf = os.path.join(em_revisao_dir, revisao.arquivo_pdf)
        if arquivo_existe(src_pdf):
            destino_pdf = os.path.join(vigentes_dir, nome_pdf_novo)
            copiar_arquivo(src_pdf, destino_pdf)
            pdf_gerado = True
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.ARQUIVO_ENVIADO,
                f'PDF Rev{revisao.numero_revisao:02d} publicado a partir de upload direto: {nome_pdf_novo}',
            )
        else:
            flash('Arquivo PDF da revisão não encontrado. PDF não publicado.', 'warning')
    elif form.gerar_pdf.data and revisao.arquivo_docx:
        from app.utils.pdf_utils import converter_docx_para_pdf
        caminho_docx_src = os.path.join(em_revisao_dir, revisao.arquivo_docx)
        if arquivo_existe(caminho_docx_src):
            pdf_temp = converter_docx_para_pdf(caminho_docx_src, vigentes_dir)
            if pdf_temp:
                # Rename to canonical name
                nome_gerado = os.path.basename(pdf_temp)
                if nome_gerado != nome_pdf_novo:
                    destino_pdf = os.path.join(vigentes_dir, nome_pdf_novo)
                    mover_arquivo(pdf_temp, destino_pdf)
                pdf_gerado = True
                registrar_evento(
                    doc.id, current_user.id,
                    AcaoEvento.PDF_GERADO,
                    f'PDF gerado automaticamente: {nome_pdf_novo}',
                )
            else:
                flash(
                    'LibreOffice não encontrado ou falhou na conversão. '
                    'Instale o LibreOffice para gerar o PDF automaticamente. '
                    'Continuando publicação sem PDF automático.',
                    'warning',
                )
        else:
            flash('Arquivo DOCX da revisão não encontrado. PDF não gerado.', 'warning')

    # ── 2. Move previous PDF to obsoletos/ ────────────────────────────────────
    if doc.caminho_pdf_vigente:
        pdf_anterior = os.path.join(vigentes_dir, doc.caminho_pdf_vigente)
        if arquivo_existe(pdf_anterior):
            nome_obs = doc.nome_arquivo_obsoleto(doc.revisao_atual)
            destino_obs = os.path.join(obsoletos_dir, nome_obs)
            mover_arquivo(pdf_anterior, destino_obs)
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.REVISAO_ANTERIOR_OBSOLETA,
                f'PDF Rev{doc.revisao_atual:02d} movido para obsoletos: {nome_obs}',
            )

    # ── 3. Move DOCX to editaveis_docx/ ───────────────────────────────────────
    nome_docx_novo = nome_docx_editavel(doc.codigo, revisao.numero_revisao, doc.titulo)
    if revisao.arquivo_docx:
        src_docx = os.path.join(em_revisao_dir, revisao.arquivo_docx)
        if arquivo_existe(src_docx):
            dest_docx = os.path.join(editaveis_dir, nome_docx_novo)
            copiar_arquivo(src_docx, dest_docx)

    # ── 4. Update Documento ───────────────────────────────────────────────────
    revisao_anterior_num = doc.revisao_atual
    doc.revisao_atual = revisao.numero_revisao
    doc.status = StatusDocumento.VIGENTE
    doc.caminho_pdf_vigente = nome_pdf_novo if pdf_gerado else doc.caminho_pdf_vigente
    doc.caminho_docx_editavel = nome_docx_novo
    doc.elaborado_por_id = revisao.elaborado_por_id
    doc.revisado_por_id = revisao.revisado_por_id
    doc.aprovado_por_id = revisao.aprovado_por_id
    doc.data_aprovacao = revisao.data_aprovacao or agora
    doc.data_publicacao = agora
    doc.atualizado_em = agora
    # Carry online content to document record
    if revisao.content_mode == 'online_editor':
        doc.content_html = revisao.content_html
        doc.content_mode = revisao.content_mode

    # ── 5. Update revision ────────────────────────────────────────────────────
    revisao.status = StatusDocumento.VIGENTE
    revisao.data_publicacao = agora

    # Mark previous active revision as Obsoleto
    RevisaoDocumento.query.filter(
        RevisaoDocumento.documento_id == doc.id,
        RevisaoDocumento.id != revisao.id,
        RevisaoDocumento.numero_revisao == revisao_anterior_num,
    ).update({'status': StatusDocumento.OBSOLETO})

    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.PUBLICADO_VIGENTE,
        f'Rev{revisao.numero_revisao:02d} publicada como vigente por '
        f'{current_user.nome}. {form.motivo.data.strip()}',
    )
    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.LISTA_MESTRA_ATUALIZADA,
        'Lista Mestra atualizada automaticamente.',
    )
    db.session.commit()

    flash(
        f'Revisão Rev{revisao.numero_revisao:02d} publicada com sucesso! '
        'A Lista Mestra foi atualizada.',
        'success',
    )
    return redirect(url_for('documentos.detalhe', id=id))


# ── Revision history helper ────────────────────────────────────────────────────

def _build_historico_revisoes(doc, incluir_revisao=None) -> list:
    """Return a list of dicts describing every published version of *doc*.

    Each entry has: numero, data, descricao, item, elaborado_por.
    Used to build the revision-history table in PDFs and the preview page.

    If *incluir_revisao* is given (an in-progress RevisaoDocumento), it is
    appended at the end so the preview shows the current revision too.
    """
    _estados_publicados = [StatusDocumento.VIGENTE, StatusDocumento.OBSOLETO]

    revisoes_publicadas = (
        RevisaoDocumento.query
        .filter(
            RevisaoDocumento.documento_id == doc.id,
            RevisaoDocumento.status.in_(_estados_publicados),
        )
        .order_by(RevisaoDocumento.numero_revisao)
        .all()
    )

    rev_numbers = {r.numero_revisao for r in revisoes_publicadas}
    hist = []

    # Original version comes from the Documento itself (published via
    # publicar_vigente — the Rascunho→Vigente shortcut, no RevisaoDocumento row).
    # We detect this when rev 0 is absent from published revisions list,
    # OR when the document was created at rev 0 and published directly.
    # Always include the doc-level entry for completeness when rev 0 is missing.
    num_inicial = min(rev_numbers) - 1 if rev_numbers else doc.revisao_atual
    if num_inicial not in rev_numbers:
        hist.append({
            'numero': num_inicial,
            'data': doc.data_publicacao or doc.data_aprovacao,
            'descricao': doc.descricao_alteracao or 'Emiss\u00e3o inicial',
            'item': doc.item_alterado or 'N/A',
            'elaborado_por': (
                doc.elaborado_por.nome if doc.elaborado_por else '\u2014'
            ),
        })

    for rev in revisoes_publicadas:
        hist.append({
            'numero': rev.numero_revisao,
            'data': rev.data_publicacao or rev.data_aprovacao,
            'descricao': rev.descricao_alteracao or '\u2014',
            'item': rev.item_alterado or '\u2014',
            'elaborado_por': (
                rev.elaborado_por.nome if rev.elaborado_por else '\u2014'
            ),
        })

    # Append the in-progress revision when previewing, so the user sees
    # the current revision's data even before it is published.
    if incluir_revisao is not None:
        already = {h['numero'] for h in hist}
        if incluir_revisao.numero_revisao not in already:
            hist.append({
                'numero': incluir_revisao.numero_revisao,
                'data': (
                    incluir_revisao.data_aprovacao
                    or incluir_revisao.data_elaboracao
                    or incluir_revisao.data_revisao
                ),
                'descricao': incluir_revisao.descricao_alteracao or '\u2014',
                'item': incluir_revisao.item_alterado or '\u2014',
                'elaborado_por': (
                    incluir_revisao.elaborado_por.nome
                    if incluir_revisao.elaborado_por else '\u2014'
                ),
                'em_andamento': True,
            })

    return hist


# ── Online Editor ──────────────────────────────────────────────────────────────

@documentos.route('/<int:id>/editor', methods=['GET', 'POST'])
@login_required
def editor_documento(id):
    """Online editor page for a Rascunho document."""
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status != StatusDocumento.RASCUNHO:
        flash('O editor online só está disponível para documentos em Rascunho.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    if not (current_user.pode_editar_documentos() or current_user.pode_abrir_revisao()):
        abort(403)

    form = EditorConteudoForm()

    if form.validate_on_submit():
        doc.content_html = form.content_html.data
        doc.content_mode = 'online_editor'
        if form.descricao_alteracao.data:
            doc.descricao_alteracao = form.descricao_alteracao.data.strip()
        if form.item_alterado.data:
            doc.item_alterado = form.item_alterado.data.strip()
        doc.atualizado_em = agora_brasilia()
        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.CONTEUDO_EDITADO_ONLINE,
            f'Conteúdo editado online por {current_user.nome}.',
        )
        db.session.commit()
        flash('Conteúdo salvo com sucesso!', 'success')
        if request.form.get('_next') == 'preview':
            return redirect(url_for('documentos.preview_documento', id=id))
        return redirect(url_for('documentos.editor_documento', id=id))
    elif request.method == 'POST':
        erros = '; '.join(e for errs in form.errors.values() for e in errs)
        flash(f'Erro ao salvar: {erros}', 'danger')

    if request.method == 'GET' and doc.content_html:
        form.content_html.data = doc.content_html
        form.descricao_alteracao.data = doc.descricao_alteracao or ''
        form.item_alterado.data = doc.item_alterado or ''

    return render_template(
        'documentos/editor.html',
        doc=doc,
        form=form,
        action_url=url_for('documentos.editor_documento', id=id),
        preview_url=url_for('documentos.preview_documento', id=id),
        back_url=url_for('documentos.detalhe', id=id),
        titulo_editor='Editar Conteúdo — Rascunho',
    )


@documentos.route('/<int:id>/revisoes/<int:rev_id>/editor', methods=['GET', 'POST'])
@login_required
def editor_revisao(id, rev_id):
    """CKEditor page for an active revision."""
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(id=rev_id, documento_id=id).first_or_404()

    _estados_editaveis = [StatusDocumento.EM_REVISAO, StatusDocumento.AGUARDANDO_APROVACAO]
    if revisao.status not in _estados_editaveis:
        flash('O editor online não está disponível para revisões neste estado.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    if not (current_user.pode_editar_documentos() or current_user.pode_abrir_revisao()):
        abort(403)

    form = EditorConteudoForm()

    if form.validate_on_submit():
        revisao.content_html = form.content_html.data
        revisao.content_mode = 'online_editor'
        if form.descricao_alteracao.data:
            revisao.descricao_alteracao = form.descricao_alteracao.data.strip()
        if form.item_alterado.data:
            revisao.item_alterado = form.item_alterado.data.strip()
        revisao.status = StatusDocumento.AGUARDANDO_APROVACAO
        doc.status = StatusDocumento.AGUARDANDO_APROVACAO
        doc.atualizado_em = agora_brasilia()
        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.CONTEUDO_EDITADO_ONLINE,
            f'Conteúdo da revisão Rev{revisao.numero_revisao:02d} salvo por {current_user.nome}. '
            f'Aguardando aprovação.',
        )
        db.session.commit()
        flash('Conteúdo salvo. Revisão encaminhada para aprovação.', 'success')
        if request.form.get('_next') == 'preview':
            return redirect(url_for('documentos.preview_revisao', id=id, rev_id=rev_id))
        return redirect(url_for('documentos.editor_revisao', id=id, rev_id=rev_id))
    elif request.method == 'POST':
        erros = '; '.join(e for errs in form.errors.values() for e in errs)
        flash(f'Erro ao salvar: {erros}', 'danger')

    if request.method == 'GET' and revisao.content_html:
        form.content_html.data = revisao.content_html
        form.descricao_alteracao.data = revisao.descricao_alteracao or ''
        form.item_alterado.data = revisao.item_alterado or ''

    return render_template(
        'documentos/editor.html',
        doc=doc,
        revisao=revisao,
        form=form,
        action_url=url_for('documentos.editor_revisao', id=id, rev_id=rev_id),
        preview_url=url_for('documentos.preview_revisao', id=id, rev_id=rev_id),
        back_url=url_for('documentos.detalhe', id=id),
        titulo_editor=f'Editar Conteúdo — Rev{revisao.numero_revisao:02d}',
    )


@documentos.route('/<int:id>/preview-online', methods=['GET'])
@login_required
def preview_documento(id):
    """Preview online content of a Rascunho document."""
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if not doc.content_html:
        flash('Não há conteúdo online para visualizar.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    publicar_form = PublicarVigenteForm()
    aprovadores = (
        Usuario.query
        .filter(Usuario.ativo == True,
                Usuario.perfil.in_([Perfil.APROVADOR, Perfil.ADMINISTRADOR]))
        .order_by(Usuario.nome).all()
    )
    publicar_form.aprovado_por_id.choices = [(u.id, u.nome) for u in aprovadores]
    if doc.aprovado_por_id:
        publicar_form.aprovado_por_id.data = doc.aprovado_por_id

    pode_publicar = (
        (current_user.pode_abrir_revisao() or current_user.pode_aprovar())
        and doc.status in [StatusDocumento.RASCUNHO, StatusDocumento.APROVADO]
        and not RevisaoDocumento.query.filter(
            RevisaoDocumento.documento_id == id,
            RevisaoDocumento.status.notin_([
                StatusDocumento.VIGENTE, StatusDocumento.OBSOLETO, StatusDocumento.CANCELADO
            ])
        ).first()
    )

    return render_template(
        'documentos/preview_online.html',
        doc=doc,
        revisao=None,
        titulo=doc.titulo,
        codigo=doc.codigo,
        revisao_num=doc.revisao_atual,
        status=doc.status,
        content_html=doc.content_html,
        historico_revisoes=_build_historico_revisoes(doc),
        back_url=url_for('documentos.detalhe', id=id),
        publicar_form=publicar_form,
        aprovar_form=None,
        reprovar_form=None,
        enviar_aprovacao_form=None,
        pode_publicar=pode_publicar,
        pode_aprovar_doc=current_user.pode_aprovar(),
        pode_editar=current_user.pode_editar_documentos(),
        tem_aprovadores=len(aprovadores) > 0,
        revisao_ativa=None,
    )


@documentos.route('/<int:id>/revisoes/<int:rev_id>/preview-online', methods=['GET'])
@login_required
def preview_revisao(id, rev_id):
    """Preview online content of an active revision."""
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(id=rev_id, documento_id=id).first_or_404()

    if not revisao.content_html:
        flash('Não há conteúdo online para visualizar nesta revisão.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    todos_usuarios = (
        Usuario.query.filter(Usuario.ativo == True).order_by(Usuario.nome).all()
    )
    aprovadores = [
        u for u in todos_usuarios
        if u.perfil in [Perfil.APROVADOR, Perfil.ADMINISTRADOR]
    ]

    aprovar_form = AprovarRevisaoForm()
    aprovar_form.elaborado_por_id.choices = [(u.id, u.nome) for u in todos_usuarios]
    aprovar_form.revisado_por_id.choices = [(u.id, u.nome) for u in todos_usuarios]
    aprovar_form.aprovado_por_id.choices = [(u.id, u.nome) for u in aprovadores]
    if revisao.elaborado_por_id:
        aprovar_form.elaborado_por_id.data = revisao.elaborado_por_id
    if revisao.revisado_por_id:
        aprovar_form.revisado_por_id.data = revisao.revisado_por_id
    if revisao.aprovado_por_id:
        aprovar_form.aprovado_por_id.data = revisao.aprovado_por_id

    reprovar_form = ReprovarRevisaoForm()

    publicar_revisao_form = PublicarRevisaoForm()

    return render_template(
        'documentos/preview_online.html',
        doc=doc,
        revisao=revisao,
        titulo=doc.titulo,
        codigo=doc.codigo,
        revisao_num=revisao.numero_revisao,
        status=revisao.status,
        content_html=revisao.content_html,
        historico_revisoes=_build_historico_revisoes(doc, incluir_revisao=revisao),
        back_url=url_for('documentos.detalhe', id=id),
        publicar_form=None,
        publicar_revisao_form=publicar_revisao_form,
        aprovar_form=aprovar_form,
        reprovar_form=reprovar_form,
        enviar_aprovacao_form=None,
        pode_publicar=False,
        pode_aprovar_doc=current_user.pode_aprovar(),
        pode_editar=current_user.pode_editar_documentos(),
        tem_aprovadores=len(aprovadores) > 0,
        revisao_ativa=revisao,
    )


# ── Documentos Externos ────────────────────────────────────────────────────────

@documentos.route('/<int:id>/tornar-obsoleto', methods=['POST'])
@login_required
def tornar_obsoleto(id):
    """Mark a Vigente document as Obsoleto (retire without a new revision)."""
    if not (current_user.pode_abrir_revisao() or current_user.pode_aprovar()):
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status != StatusDocumento.VIGENTE:
        flash('Apenas documentos Vigentes podem ser tornados obsoletos.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    # Ensure no active revision is in progress
    revisao_ativa = (
        RevisaoDocumento.query
        .filter(
            RevisaoDocumento.documento_id == id,
            RevisaoDocumento.status.notin_([
                StatusDocumento.VIGENTE, StatusDocumento.OBSOLETO,
                StatusDocumento.CANCELADO,
            ]),
        )
        .first()
    )
    if revisao_ativa:
        flash('Não é possível tornar obsoleto: existe uma revisão em andamento.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    motivo = request.form.get('motivo', '').strip()
    if not motivo:
        flash('Informe o motivo para tornar o documento obsoleto.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    agora = agora_brasilia()
    vigentes_dir = current_app.config['VIGENTES_PDF_DIR']
    obsoletos_dir = current_app.config['OBSOLETOS_DIR']

    # Move PDF to obsoletos/
    if doc.caminho_pdf_vigente:
        pdf_path = os.path.join(vigentes_dir, doc.caminho_pdf_vigente)
        if arquivo_existe(pdf_path):
            nome_obs = doc.nome_arquivo_obsoleto(doc.revisao_atual)
            mover_arquivo(pdf_path, os.path.join(obsoletos_dir, nome_obs))

    doc.status = StatusDocumento.OBSOLETO
    doc.atualizado_em = agora

    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.PUBLICADO_VIGENTE,
        f'Documento tornado obsoleto por {current_user.nome}. Motivo: {motivo}',
    )
    db.session.commit()

    flash(f'Documento {doc.codigo} marcado como Obsoleto.', 'success')
    return redirect(url_for('documentos.detalhe', id=id))


@documentos.route('/externos', methods=['GET', 'POST'])
@login_required
def documentos_externos():
    """Single-page list + upload for external documents."""
    form = DocumentoExternoForm()
    exibir_obsoletos = request.args.get('obs', '0') == '1'
    q_f = request.args.get('q', '').strip()
    orgao_f = request.args.get('orgao', '').strip()

    if form.validate_on_submit():
        if not current_user.pode_editar_documentos():
            abort(403)

        # ── Save uploaded file if provided ─────────────────────────────────
        arquivo_nome = None
        if form.arquivo.data and form.arquivo.data.filename:
            f = form.arquivo.data
            original = secure_filename(f.filename)
            ext = os.path.splitext(original)[1]
            prefixo = re.sub(r'[^\w]', '_', (form.codigo.data or form.titulo.data)[:30])
            arquivo_nome = f"{prefixo}_{agora_brasilia().strftime('%Y%m%d_%H%M%S')}{ext}"
            ext_dir = current_app.config['EXTERNOS_DIR']
            os.makedirs(ext_dir, exist_ok=True)
            f.save(os.path.join(ext_dir, arquivo_nome))

        # ── Auto-obsolete previous vigente docs with same código or título ─
        codigo_novo = (form.codigo.data or '').strip()
        titulo_novo = form.titulo.data.strip()

        anteriores = DocumentoExterno.query.filter_by(status='Vigente')
        if codigo_novo:
            anteriores = anteriores.filter(
                or_(
                    DocumentoExterno.codigo == codigo_novo,
                    DocumentoExterno.titulo == titulo_novo,
                )
            )
        else:
            anteriores = anteriores.filter(DocumentoExterno.titulo == titulo_novo)

        for prev in anteriores.all():
            prev.status = 'Obsoleto'

        novo = DocumentoExterno(
            codigo=codigo_novo or None,
            titulo=titulo_novo,
            orgao_emissor=(form.orgao_emissor.data or '').strip() or None,
            revisao=(form.revisao.data or '').strip() or None,
            arquivo_pdf=arquivo_nome,
            distribuicao_tecnica=bool(form.distribuicao_tecnica.data),
            distribuicao_administrativa=bool(form.distribuicao_administrativa.data),
            observacao=(form.observacao.data or '').strip() or None,
            status='Vigente',
            enviado_por_id=current_user.id,
            data_envio=agora_brasilia(),
        )
        db.session.add(novo)
        db.session.commit()
        flash('Documento externo registrado com sucesso!', 'success')
        return redirect(url_for('documentos.documentos_externos'))

    query = DocumentoExterno.query
    if not exibir_obsoletos:
        query = query.filter_by(status='Vigente')
    if q_f:
        query = query.filter(
            or_(
                DocumentoExterno.codigo.ilike(f'%{q_f}%'),
                DocumentoExterno.titulo.ilike(f'%{q_f}%'),
            )
        )
    if orgao_f:
        query = query.filter(DocumentoExterno.orgao_emissor.ilike(f'%{orgao_f}%'))
    docs_externos = query.order_by(
        DocumentoExterno.orgao_emissor, DocumentoExterno.codigo
    ).all()

    return render_template(
        'documentos/documentos_externos.html',
        title='Documentos Externos',
        form=form,
        docs_externos=docs_externos,
        exibir_obsoletos=exibir_obsoletos,
        q_f=q_f,
        orgao_f=orgao_f,
        pode_editar=current_user.pode_editar_documentos(),
    )


@documentos.route('/externos/download/<int:id>')
@login_required
def download_externo(id):
    """Serve an uploaded external document file."""
    doc = DocumentoExterno.query.get_or_404(id)
    if not doc.arquivo_pdf:
        abort(404)
    ext_dir = current_app.config['EXTERNOS_DIR']
    caminho = os.path.join(ext_dir, doc.arquivo_pdf)
    if not os.path.isfile(caminho):
        abort(404)
    return send_file(caminho, as_attachment=False, download_name=doc.arquivo_pdf)


@documentos.route('/externos/editar/<int:id>', methods=['POST'])
@login_required
def editar_externo(id):
    """Inline edit of an external document's metadata / file replacement."""
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = DocumentoExterno.query.get_or_404(id)

    # Read fields directly from request.form — inline raw-HTML form
    doc.codigo = (request.form.get('codigo', '') or '').strip() or None
    titulo = (request.form.get('titulo', '') or '').strip()
    if not titulo:
        flash('O título não pode estar em branco.', 'danger')
        return redirect(url_for('documentos.documentos_externos'))
    doc.titulo = titulo
    doc.orgao_emissor = (request.form.get('orgao_emissor', '') or '').strip() or None
    doc.revisao = (request.form.get('revisao', '') or '').strip() or None
    doc.distribuicao_tecnica = bool(request.form.get('distribuicao_tecnica'))
    doc.distribuicao_administrativa = bool(request.form.get('distribuicao_administrativa'))
    doc.observacao = (request.form.get('observacao', '') or '').strip() or None

    # Optional file replacement
    arq = request.files.get('arquivo')
    if arq and arq.filename:
        original = secure_filename(arq.filename)
        ext = os.path.splitext(original)[1].lower()
        if ext not in {'.pdf', '.docx', '.doc', '.xlsx', '.xls'}:
            flash('Formato de arquivo não permitido.', 'danger')
            return redirect(url_for('documentos.documentos_externos'))
        prefixo = re.sub(r'[^\w]', '_', (doc.codigo or doc.titulo)[:30])
        arquivo_nome = f"{prefixo}_{agora_brasilia().strftime('%Y%m%d_%H%M%S')}{ext}"
        ext_dir = current_app.config['EXTERNOS_DIR']
        os.makedirs(ext_dir, exist_ok=True)
        arq.save(os.path.join(ext_dir, arquivo_nome))
        doc.arquivo_pdf = arquivo_nome

    db.session.commit()
    flash('Documento externo atualizado!', 'success')
    return redirect(url_for('documentos.documentos_externos'))


@documentos.route('/externos/visualizar/<int:id>')
@login_required
def visualizar_externo(id):
    """Show an inline preview of an uploaded external document."""
    doc = DocumentoExterno.query.get_or_404(id)

    ext_suportada = False
    tipo_arquivo = None
    arquivo_url = None

    if doc.arquivo_pdf:
        ext = os.path.splitext(doc.arquivo_pdf)[1].lower()
        ext_dir = current_app.config['EXTERNOS_DIR']
        existe = os.path.isfile(os.path.join(ext_dir, doc.arquivo_pdf))
        if existe:
            arquivo_url = url_for('documentos.download_externo', id=doc.id)
            if ext == '.pdf':
                tipo_arquivo = 'pdf'
                ext_suportada = True
            elif ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
                tipo_arquivo = 'imagem'
                ext_suportada = True
            else:
                tipo_arquivo = 'outro'

    return render_template(
        'documentos/visualizar_externo.html',
        title='Visualizar Documento Externo',
        doc=doc,
        tipo_arquivo=tipo_arquivo,
        ext_suportada=ext_suportada,
        arquivo_url=arquivo_url,
    )


# ── Editor image upload / serve ────────────────────────────────────────────────

_ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


@documentos.route('/editor/upload-imagem', methods=['POST'])
@login_required
def editor_upload_imagem():
    """Receive an image upload from TinyMCE and return {"location": url}."""
    if not current_user.pode_editar_documentos():
        return jsonify({'error': 'Você não tem permissão para executar esta ação.'}), 403

    arquivo = request.files.get('file')
    if not arquivo or not arquivo.filename:
        return jsonify({'error': 'Nenhum arquivo enviado.'}), 400

    ext = os.path.splitext(secure_filename(arquivo.filename))[1].lstrip('.').lower()
    if ext not in _ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({'error': 'Formato de imagem não permitido. Use PNG, JPG, JPEG, GIF ou WEBP.'}), 415

    imagens_dir = current_app.config['EDITOR_IMAGENS_DIR']
    os.makedirs(imagens_dir, exist_ok=True)

    nome_unico = f"{uuid.uuid4().hex}.{ext}"
    destino = os.path.join(imagens_dir, nome_unico)
    try:
        arquivo.save(destino)
    except Exception:
        current_app.logger.exception('Erro ao salvar imagem do editor')
        return jsonify({'error': 'Erro ao enviar imagem.'}), 500

    location = url_for('documentos.editor_serve_imagem', filename=nome_unico, _external=False)
    return jsonify({'location': location}), 200


@documentos.route('/editor/imagem/<filename>')
@login_required
def editor_serve_imagem(filename):
    """Serve an image that was uploaded via the online editor."""
    # Prevent path traversal: basename only
    safe = os.path.basename(secure_filename(filename))
    if not safe or safe != filename:
        abort(404)

    imagens_dir = current_app.config['EDITOR_IMAGENS_DIR']
    caminho = os.path.join(imagens_dir, safe)
    if not os.path.isfile(caminho):
        abort(404)

    return send_file(caminho)

