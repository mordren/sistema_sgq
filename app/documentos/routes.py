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
from sqlalchemy import or_, text, case

from app.documentos import documentos
from werkzeug.utils import secure_filename

from app.documentos.forms import (
    NovoDocumentoForm, EditarDocumentoForm,
    PublicarVigenteForm,
    AbrirRevisaoForm, EnviarAprovacaoForm,
    AprovarRevisaoForm, ReprovarRevisaoForm, PublicarRevisaoForm,
    EditorConteudoForm, ListaMestraConfigForm,
    DocumentoExternoForm, UploadPdfForm,
)
from app.documentos.exportar import (
    gerar_excel_lista_mestra, gerar_pdf_lista_mestra, gerar_csv_lista_mestra,
)
from app.extensions import db
from app.models import Documento, Usuario, HistoricoEvento, RevisaoDocumento, MatrizCorrelacao, Alerta
from app.models.documento_externo import DocumentoExterno
from app.models.lista_mestra_config import ListaMestraConfig
from app.models.documento import TipoDocumento, StatusDocumento
from app.models.historico import AcaoEvento
from app.models.usuario import Perfil
from app.utils.decorators import bloquear_auditor
from app.utils.file_utils import (
    salvar_upload, caminho_seguro, arquivo_existe,
    nome_pdf_vigente, nome_docx_editavel,
    caminho_vigente_pdf, caminho_editavel_docx,
    caminho_em_revisao, caminho_obsoleto, mover_arquivo, copiar_arquivo,
    extensao_permitida, ALLOWED_PDF,
)
from app.utils.datetime_utils import agora_brasilia
from app.utils.historico import registrar_evento


# ── Helpers ────────────────────────────────────────────────────────────────────

def _natural_sort_key(value: str | None):
    """Key for natural (human-friendly) sorting of strings with numbers.

    Splits on digit boundaries so that 'Portaria 23/1994' < 'Portaria 058/2017'
    instead of lexicographic ordering where '23' > '1097'.
    """
    if not value:
        return ('',)
    parts = re.split(r'(\d+)', value)
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts)


def _ordenar_docs_externos(docs: list) -> list:
    """Sort external documents naturally: orgao_emissor first, then codigo."""
    docs.sort(key=lambda d: (
        (d.orgao_emissor or '').lower(),
        _natural_sort_key(d.codigo),
    ))
    return docs


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


# ── Upload em Lote – helpers ───────────────────────────────────────────────────

# Aceita ambos os formatos:
#   FOR ADM 47 rev. 00 Titulo.pdf  (espaço + rev. + número)
#   FOR ADM 47_Rev00_Titulo.pdf    (underscore + Rev + número)
_RE_NOME_PDF_LOTE = re.compile(r'^(.+?)(?:\s+|_+)rev\.?\s*(\d+)', re.IGNORECASE)


def _parsear_codigo_do_nome(filename: str):
    """Extract (codigo, revisao) from a PDF filename.

    Supported formats:
      FOR ADM 47 rev. 00 Titulo.pdf
      FOR ADM 47_Rev00_Titulo.pdf

    Returns (codigo_str, revisao_int) or (None, None) if no match.
    """
    nome = os.path.splitext(filename)[0]
    m = _RE_NOME_PDF_LOTE.match(nome)
    if not m:
        return None, None
    codigo_raw = m.group(1).strip().strip('_')
    try:
        revisao = int(m.group(2))
    except ValueError:
        revisao = 0
    return codigo_raw, revisao


def _buscar_doc_lote(codigo_raw: str):
    """Find an active document by code, trying multiple normalizations.

    Handles mismatches between filename separators and DB codes, e.g.:
      filename: 'FOR ADM 04'  →  DB code: 'FOR-ADM-04'
      filename: 'FOR ADM 04'  →  DB code: 'FOR ADM 04'
      filename: 'FOR_ADM_04'  →  DB code: 'FOR ADM 04'
    """
    # Build a list of candidate codes to try (deduplicated, preserving order)
    seen = set()
    candidates = []
    for variant in [
        codigo_raw,                              # as-is
        codigo_raw.replace('_', ' '),            # underscores → spaces
        codigo_raw.replace(' ', '-'),            # spaces → hyphens
        codigo_raw.replace('_', '-'),            # underscores → hyphens
        re.sub(r'[\s_-]+', ' ', codigo_raw),     # any separator → single space
        re.sub(r'[\s_-]+', '-', codigo_raw),     # any separator → hyphen
    ]:
        key = variant.upper()
        if key not in seen:
            seen.add(key)
            candidates.append(variant)

    for candidate in candidates:
        doc = Documento.query.filter(
            db.func.upper(Documento.codigo) == candidate.upper(),
            Documento.ativo == True,
        ).first()
        if doc:
            return doc
    return None


def _processar_pdf_lote(arquivo) -> dict:
    """Save a PDF and publish the matching document as Vigente.

    Returns a result dict with keys: arquivo, status, codigo, titulo, mensagem.
    """
    filename = arquivo.filename or ''

    if not extensao_permitida(filename, ALLOWED_PDF):
        return {'arquivo': filename, 'status': 'erro',
                'mensagem': 'Apenas arquivos PDF são permitidos.'}

    codigo_raw, _revisao = _parsear_codigo_do_nome(filename)
    if not codigo_raw:
        return {
            'arquivo': filename, 'status': 'erro',
            'mensagem': (
                'Não foi possível identificar o código no nome do arquivo. '
                'Use o formato: CODIGO_RevXX_Titulo.pdf'
            ),
        }

    doc = _buscar_doc_lote(codigo_raw)
    if doc is None:
        return {
            'arquivo': filename, 'status': 'nao_encontrado', 'codigo': codigo_raw,
            'mensagem': f'Documento com código "{codigo_raw}" não encontrado no sistema.',
        }

    if doc.status != StatusDocumento.RASCUNHO:
        return {
            'arquivo': filename, 'status': 'ignorado', 'codigo': doc.codigo,
            'titulo': doc.titulo,
            'mensagem': (
                f'Status atual: {doc.status}. '
                'Somente documentos em Rascunho são aceitos.'
            ),
        }

    nome_arquivo = nome_pdf_vigente(doc.codigo, doc.revisao_atual, doc.titulo)
    em_revisao_dir = current_app.config['EM_REVISAO_DIR']

    try:
        salvar_upload(arquivo, em_revisao_dir, nome_arquivo)
    except Exception:
        current_app.logger.exception('Erro ao salvar PDF lote doc %s', doc.id)
        return {'arquivo': filename, 'status': 'erro',
                'mensagem': 'Erro ao salvar o arquivo no servidor.'}

    agora = agora_brasilia()
    doc.aprovado_por_id = current_user.id
    doc.data_aprovacao = agora
    doc.data_publicacao = agora
    doc.status = StatusDocumento.VIGENTE
    doc.content_mode = 'uploaded_file'
    doc.content_html = None
    doc.atualizado_em = agora

    src = caminho_em_revisao(nome_arquivo)
    dst = caminho_vigente_pdf(nome_arquivo)
    if arquivo_existe(src):
        mover_arquivo(src, dst)
    doc.caminho_pdf_vigente = nome_arquivo

    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.PUBLICADO_VIGENTE,
        f'Upload em lote por {current_user.nome}.',
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Erro ao commitar lote doc %s', doc.id)
        return {'arquivo': filename, 'status': 'erro',
                'mensagem': 'Erro ao salvar no banco de dados.'}

    return {
        'arquivo': filename, 'status': 'sucesso',
        'codigo': doc.codigo, 'titulo': doc.titulo,
        'mensagem': f'Documento {doc.codigo} publicado como Vigente.',
        'doc_id': doc.id,
    }


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
@bloquear_auditor
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
        query.order_by(*_order_by_tipo_codigo())
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


# ── Cadastro Rápido de Documentos ──────────────────────────────────────────────

@documentos.route('/cadastro-rapido', methods=['GET', 'POST'])
@login_required
@bloquear_auditor
def cadastro_rapido():
    """Express bulk registration of existing documents directly to VIGENTE status."""
    if not current_user.pode_editar_documentos():
        abort(403)

    if request.method == 'POST':
        dados = request.get_json(silent=True) or []
        criados = 0
        duplicados = []
        erros = []

        for item in dados:
            codigo = (item.get('codigo') or '').strip().upper()
            titulo = (item.get('titulo') or '').strip()
            tipo = (item.get('tipo') or '').strip()
            try:
                revisao = int(item.get('revisao') or 0)
            except (ValueError, TypeError):
                revisao = 0

            if not codigo or not titulo or not tipo:
                continue

            if Documento.query.filter_by(codigo=codigo).first():
                duplicados.append(codigo)
                continue

            try:
                _revisor = Usuario.revisor_padrao_ativo()
                doc = Documento(
                    codigo=codigo,
                    titulo=titulo,
                    tipo_documento=tipo,
                    revisao_atual=revisao,
                    status=StatusDocumento.RASCUNHO,
                    elaborado_por_id=current_user.id,
                    revisado_por_id=_revisor.id if _revisor else None,
                    ativo=True,
                )
                db.session.add(doc)
                db.session.flush()
                registrar_evento(
                    doc.id, current_user.id,
                    AcaoEvento.DOCUMENTO_CADASTRADO,
                    f'Cadastro rápido (rascunho) por {current_user.nome}.',
                )
                criados += 1
            except Exception as exc:
                db.session.rollback()
                erros.append(f'{codigo}: {str(exc)}')

        if criados:
            db.session.commit()

        return jsonify({'criados': criados, 'duplicados': duplicados, 'erros': erros})

    tipos = [(t, TipoDocumento.LABELS.get(t, t)) for t in TipoDocumento.TODOS]
    return render_template(
        'documentos/cadastro_rapido.html',
        title='Cadastro Rápido',
        tipos=tipos,
    )


# ── Upload em Lote ─────────────────────────────────────────────────────────────

@documentos.route('/upload-lote', methods=['GET', 'POST'])
@login_required
@bloquear_auditor
def upload_lote():
    """Bulk PDF upload: identify documents by filename, publish each as Vigente.

    POST expects multipart field 'arquivos' (multiple PDFs).
    Returns JSON with per-file results so the page can display live feedback.
    """
    if not current_user.pode_editar_documentos():
        abort(403)

    if request.method == 'POST':
        arquivos = request.files.getlist('arquivos')
        if not arquivos or all(not a.filename for a in arquivos):
            return jsonify({'erro': 'Nenhum arquivo recebido.'}), 400

        resultados = []
        for arquivo in arquivos:
            if not arquivo.filename:
                continue
            resultado = _processar_pdf_lote(arquivo)
            resultados.append(resultado)

        return jsonify({'resultados': resultados})

    return render_template(
        'documentos/upload_lote.html',
        title='Upload em Lote',
    )


# ── Importar Matriz de Correlação ──────────────────────────────────────────────

# ── Ordenação por tipo (ordem canônica do SGQ) ────────────────────────────────
_ORDEM_TIPO = [TipoDocumento.MQ, TipoDocumento.PA, TipoDocumento.PT,
               TipoDocumento.IT, TipoDocumento.FOR_ADM, TipoDocumento.FOR_TEC]


def _order_by_tipo_codigo():
    """Return SQLAlchemy order clauses: tipo (canonical order) then codigo."""
    tipo_case = case(
        {t: i for i, t in enumerate(_ORDEM_TIPO)},
        value=Documento.tipo_documento,
        else_=len(_ORDEM_TIPO),
    )
    return tipo_case, Documento.codigo


# Regex que reconhece códigos de documento como FOR ADM 01, FOR-ADM-01, PA-01, PA 01, etc.
_RE_CODIGO_DOC = re.compile(
    r'\b(?:FOR[-\s]+(?:ADM|TEC)|PA|PT|IT|MQ)[-\s]*\d+\b',
    re.IGNORECASE,
)


def _split_codigos(texto: str) -> list:
    """Split text into individual document codes.

    Handles: comma/semicolon/newline separators AND space-separated codes
    within a single cell (e.g. 'FOR ADM 05 FOR ADM 44 FOR ADM 47').
    """
    if not texto:
        return []
    # First check if the text contains multiple recognizable codes
    encontrados = _RE_CODIGO_DOC.findall(texto)
    if len(encontrados) > 1:
        # Multiple codes packed in one string — use regex matches directly
        return [c.strip() for c in encontrados if c.strip()]
    # Fall back to standard separator split
    return [p.strip() for p in re.split(r'[,\n;/]+', texto) if p.strip()]


def _parsear_tabela_matriz(tabela: str) -> list:
    """Parse a tab-separated table paste into a list of row dicts."""
    SKIP_VALS = {'não aplicável', 'nao aplicavel', 'n/a', '-', '—', '–', '', 'não  aplicável'}
    HEADER_STARTERS = {'norma', 'iso', 'nit diois', 'requisito', 'procedimento',
                       'formulário', 'formulario', 'mq'}

    linhas = []
    for linha_raw in tabela.splitlines():
        linha_raw = linha_raw.strip()
        if not linha_raw:
            continue
        cols = [c.strip().replace('\xa0', ' ') for c in linha_raw.split('\t')]
        if len(cols) < 4:
            continue

        primeiro = cols[0].lower().strip().replace('\xa0', ' ')
        if any(primeiro.startswith(h) for h in HEADER_STARTERS):
            continue

        def norm(v):
            cleaned = v.strip().replace('\xa0', ' ')
            return '' if cleaned.lower() in SKIP_VALS else cleaned

        norma    = norm(cols[0]) if len(cols) > 0 else ''
        nit019   = norm(cols[1]) if len(cols) > 1 else ''
        nit008   = norm(cols[2]) if len(cols) > 2 else ''
        mq_val   = norm(cols[3]) if len(cols) > 3 else ''
        descricao = cols[4].strip() if len(cols) > 4 else ''
        procs    = norm(cols[5]) if len(cols) > 5 else ''
        # Collect formulário from col[6] plus any extra columns (col[7]+)
        form_parts = []
        for i in range(6, len(cols)):
            v = norm(cols[i])
            if v:
                form_parts.append(v)
        form_col = ' '.join(form_parts)

        if not any([norma, nit019, nit008, mq_val]):
            continue

        linhas.append({
            'norma_17020': norma,
            'nit_diois_019': nit019,
            'nit_diois_008': nit008,
            'mq': mq_val,
            'descricao': descricao,
            'procedimentos': procs,
            'formulario': form_col,
        })
    return linhas


def _criar_mc_direto(linha: dict, formularios: list) -> None:
    """Insert a MatrizCorrelacao row directly (no associated document)."""
    mc = MatrizCorrelacao(
        norma_17020=linha['norma_17020'] or None,
        nit_diois_019=linha['nit_diois_019'] or None,
        nit_diois_008=linha['nit_diois_008'] or None,
        mq=linha['mq'] or None,
        requisito=linha['mq'] or linha['norma_17020'] or '—',
        descricao_requisito=linha['descricao'] or None,
        formularios=', '.join(formularios) if formularios else None,
    )
    db.session.add(mc)


def _importar_linhas_matriz(linhas: list) -> dict:
    """
    For each parsed row:
    - procedimentos has a valid doc code → update that doc's matriz_correlacao_json
    - otherwise → insert a MatrizCorrelacao entry directly
    Returns stats dict.
    """
    doc_cache: dict = {}       # UPPER_CODE → Documento or None
    doc_rows: dict  = {}       # doc.id → {'doc': Documento, 'rows': list}
    nao_encontrados: list = []
    diretos = 0

    for linha in linhas:
        formularios = _split_codigos(linha['formulario'])
        proc_codes  = _split_codigos(linha['procedimentos'])

        row_data = {
            'norma_17020': linha['norma_17020'],
            'nit_diois_019': linha['nit_diois_019'],
            'nit_diois_008': linha['nit_diois_008'],
            'mq': linha['mq'],
            'requisito': linha['mq'] or linha['norma_17020'] or '',
            'formularios': formularios,
        }

        if proc_codes:
            for code in proc_codes:
                code_up = code.upper()
                if code_up not in doc_cache:
                    doc_cache[code_up] = Documento.query.filter(
                        db.func.upper(Documento.codigo) == code_up,
                        Documento.ativo == True,
                    ).first()

                doc = doc_cache[code_up]
                if doc:
                    if doc.id not in doc_rows:
                        existing = []
                        if doc.matriz_correlacao_json:
                            try:
                                existing = json.loads(doc.matriz_correlacao_json)
                            except Exception:
                                existing = []
                        doc_rows[doc.id] = {'doc': doc, 'rows': list(existing)}
                    doc_rows[doc.id]['rows'].append(row_data)
                else:
                    if code_up not in nao_encontrados:
                        nao_encontrados.append(code_up)
                    _criar_mc_direto(linha, formularios)
                    diretos += 1
        else:
            _criar_mc_direto(linha, formularios)
            diretos += 1

    atualizados = 0
    for info in doc_rows.values():
        doc = info['doc']
        doc.matriz_correlacao_json = json.dumps(info['rows'], ensure_ascii=False)
        doc.requisito_relacionado = _resumo_requisitos_matriz(doc.matriz_correlacao_json)
        doc.atualizado_em = agora_brasilia()
        atualizados += 1

    db.session.commit()
    return {
        'atualizados': atualizados,
        'diretos': diretos,
        'nao_encontrados': nao_encontrados,
    }


@documentos.route('/importar-matriz', methods=['GET', 'POST'])
@login_required
@bloquear_auditor
def importar_matriz():
    """Paste a tab-separated matrix table and import it into the correlation matrix."""
    if not current_user.pode_editar_documentos():
        abort(403)

    _ensure_documento_matriz_schema()
    _ensure_matriz_correlacao_schema()

    tabela = ''
    linhas_parsed = []
    preview = False

    if request.method == 'POST':
        tabela = request.form.get('tabela', '')
        acao = request.form.get('acao', 'preview')
        linhas_parsed = _parsear_tabela_matriz(tabela)

        if acao == 'importar' and linhas_parsed:
            resultado = _importar_linhas_matriz(linhas_parsed)
            registrar_evento(
                usuario_id=current_user.id,
                acao=AcaoEvento.MATRIZ_ATUALIZADA,
                descricao=f'{resultado["atualizados"]} doc(s) atualizado(s), '
                          f'{resultado["diretos"]} linha(s) direta(s)',
            )
            flash(
                f'Importação concluída: {resultado["atualizados"]} documento(s) atualizado(s), '
                f'{resultado["diretos"]} linha(s) sem procedimento registrada(s) diretamente.',
                'success',
            )
            if resultado['nao_encontrados']:
                flash(
                    'Procedimentos não encontrados no banco (registrados como entradas avulsas): '
                    + ', '.join(resultado['nao_encontrados']),
                    'warning',
                )
            return redirect(url_for('documentos.importar_matriz'))
        else:
            preview = True

    return render_template(
        'documentos/importar_matriz.html',
        title='Importar Matriz de Correlação',
        tabela=tabela,
        linhas=linhas_parsed,
        preview=preview,
    )


# ── Lista Mestra ───────────────────────────────────────────────────────────────

@documentos.route('/lista-mestra', methods=['GET'])
@login_required
def lista_mestra():
    # Show all documents that are Vigente (or Em revisão keeping old PDF valid)
    # regardless of whether their PDF is stored or generated on-demand (online editor).
    _excluidos = [
        StatusDocumento.RASCUNHO,
        StatusDocumento.OBSOLETO,
        StatusDocumento.CANCELADO,
    ]
    from sqlalchemy import or_
    query = (
        Documento.query
        .filter(
            Documento.ativo == True,
            Documento.status.notin_(_excluidos),
            or_(
                Documento.caminho_pdf_vigente.isnot(None),
                Documento.content_html.isnot(None),
            ),
        )
    )

    # ── Filtro por busca textual ──
    q = (request.args.get('q', '') or '').strip()
    if q:
        query = query.filter(
            or_(
                Documento.codigo.ilike(f'%{q}%'),
                Documento.titulo.ilike(f'%{q}%'),
            )
        )

    docs = query.order_by(*_order_by_tipo_codigo()).all()
    cfg = ListaMestraConfig.get()
    pode_configurar = current_user.pode_aprovar() or current_user.perfil == Perfil.ADMINISTRADOR
    docs_externos = (
        DocumentoExterno.query
        .filter_by(status='Vigente')
        .all()
    )
    _ordenar_docs_externos(docs_externos)

    from app.models.consulta_remota import ConsultaRemota
    from app.models.controle_versao_software import ControleVersaoSoftware
    ano_lm = agora_brasilia().year
    consultas = ConsultaRemota.query.filter_by(ano=ano_lm).all()
    consultas_mapa = {(c.mes, c.quinzena): c for c in consultas}

    versao_software = (
        ControleVersaoSoftware.query
        .order_by(
            ControleVersaoSoftware.equipamento,
            ControleVersaoSoftware.software,
        )
        .all()
    )

    _MESES_LM = [
        (1,'JAN'),(2,'FEV'),(3,'MAR'),(4,'ABR'),
        (5,'MAI'),(6,'JUN'),(7,'JUL'),(8,'AGO'),
        (9,'SET'),(10,'OUT'),(11,'NOV'),(12,'DEZ'),
    ]

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
        consultas_mapa=consultas_mapa,
        consultas_meses=_MESES_LM,
        consultas_ano=ano_lm,
        versao_software=versao_software,
        q_f=q,
    )


@documentos.route('/lista-mestra/exportar/<formato>', methods=['GET'])
@login_required
def exportar_lista_mestra(formato):
    if not current_user.pode_exportar():
        abort(403)

    docs = (
        Documento.query
        .filter_by(status=StatusDocumento.VIGENTE, ativo=True)
        .order_by(*_order_by_tipo_codigo())
        .all()
    )
    docs_externos_exp = (
        DocumentoExterno.query
        .filter_by(status='Vigente')
        .order_by(DocumentoExterno.orgao_emissor, DocumentoExterno.codigo)
        .all()
    )

    from app.models.consulta_remota import ConsultaRemota
    from app.models.controle_versao_software import ControleVersaoSoftware
    consultas_exp = ConsultaRemota.query.filter_by(ano=agora_brasilia().year).all()
    versao_sw_exp = (
        ControleVersaoSoftware.query
        .order_by(
            ControleVersaoSoftware.equipamento,
            ControleVersaoSoftware.software,
        )
        .all()
    )

    stamp = agora_brasilia().strftime('%Y%m%d_%H%M')
    fmt = formato.lower()
    cfg = ListaMestraConfig.get()

    if fmt == 'excel':
        output = gerar_excel_lista_mestra(docs, externos=docs_externos_exp, consultas=consultas_exp, versao_sw=versao_sw_exp)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'lista_mestra_{stamp}.xlsx',
        )
    elif fmt == 'pdf':
        output = gerar_pdf_lista_mestra(docs, cfg=cfg, externos=docs_externos_exp, consultas=consultas_exp, versao_sw=versao_sw_exp)
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'lista_mestra_{stamp}.pdf',
        )
    elif fmt == 'csv':
        csv_str = gerar_csv_lista_mestra(docs, externos=docs_externos_exp, consultas=consultas_exp, versao_sw=versao_sw_exp)
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
        cfg.data_aprovacao = form.data_aprovacao.data or agora_brasilia()
        cfg.atualizado_em = agora_brasilia()
        db.session.commit()
        flash('Configuração da Lista Mestra salva com sucesso!', 'success')
        return redirect(url_for('documentos.lista_mestra'))

    if request.method == 'GET':
        form.elaborado_por_id.data = cfg.elaborado_por_id or 0
        form.revisado_por_id.data = cfg.revisado_por_id or 0
        form.aprovado_por_id.data = cfg.aprovado_por_id or 0
        if cfg.data_aprovacao:
            form.data_aprovacao.data = cfg.data_aprovacao.date()

    return render_template(
        'documentos/configurar_lista_mestra.html',
        title='Configurar Lista Mestra',
        form=form,
        cfg=cfg,
    )


# ── New document ───────────────────────────────────────────────────────────────

@documentos.route('/novo', methods=['GET', 'POST'])
@login_required
@bloquear_auditor
def novo():
    if not current_user.pode_editar_documentos():
        abort(403)

    _ensure_documento_matriz_schema()
    form = NovoDocumentoForm()
    form.tipo_documento.choices = _choices_tipos()
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

        _revisor_padrao = Usuario.revisor_padrao_ativo()
        doc = Documento(
            codigo=codigo,
            titulo=form.titulo.data.strip(),
            tipo_documento=form.tipo_documento.data,
            revisao_atual=form.revisao_inicial.data,
            status=StatusDocumento.RASCUNHO,
            elaborado_por_id=current_user.id,  # Always the authenticated user
            revisado_por_id=_revisor_padrao.id if _revisor_padrao else None,
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
        db.session.flush()  # get doc.id for history registration

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
@bloquear_auditor
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
    publicar_form = PublicarVigenteForm()
    abrir_revisao_form = AbrirRevisaoForm()
    aprovar_form = AprovarRevisaoForm()
    reprovar_form = ReprovarRevisaoForm()
    publicar_revisao_form = PublicarRevisaoForm()
    upload_pdf_form = UploadPdfForm()

    # ── Permissions ────────────────────────────────────────────────────────────
    pode_editar = current_user.pode_editar_documentos()
    pode_editar_meta = current_user.pode_editar_metadados()
    pode_publicar = (
        current_user.pode_aprovar()
        and doc.status in [StatusDocumento.RASCUNHO, StatusDocumento.APROVADO]
        and revisao_ativa is None  # only for simple import path (Rascunho→Vigente)
    )
    pode_ver_docx = current_user.pode_editar_documentos()

    # Debug: log the publishability state to help diagnose client issues
    current_app.logger.debug(
        'detalhe page: pode_publicar=%s, caminho_pdf_vigente=%s, has_content_html=%s',
        pode_publicar, doc.caminho_pdf_vigente, bool(doc.content_html),
    )

    revisor_global = Usuario.revisor_padrao_ativo()

    return render_template(
        'documentos/detalhe.html',
        title=f'{doc.codigo} – {doc.titulo}',
        doc=doc,
        historico=historico,
        revisoes=revisoes,
        revisao_ativa=revisao_ativa,
        revisor_global=revisor_global,
        publicar_form=publicar_form,
        abrir_revisao_form=abrir_revisao_form,
        enviar_aprovacao_form=None,
        aprovar_form=aprovar_form,
        reprovar_form=reprovar_form,
        publicar_revisao_form=publicar_revisao_form,
        upload_pdf_form=upload_pdf_form,
        pode_editar=pode_editar,
        pode_editar_meta=pode_editar_meta,
        pode_publicar=pode_publicar,
        pode_ver_docx=pode_ver_docx,
        pode_abrir_revisao=current_user.pode_abrir_revisao(),
        pode_revisar=current_user.pode_revisar(),
        pode_aprovar_doc=current_user.pode_aprovar(),
        StatusDocumento=StatusDocumento,
        TipoDocumento=TipoDocumento,
    )


# ── Edit document metadata ─────────────────────────────────────────────────────

@documentos.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@bloquear_auditor
def editar(id):
    # Metadata-only edit (title + matrix) allowed for Admin/Qualidade on any status.
    # Full content/workflow edits still require pode_editar_documentos().
    pode_meta = current_user.pode_editar_metadados()
    pode_full = current_user.pode_editar_documentos()

    if not pode_meta and not pode_full:
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    # Metadata-only mode: document is VIGENTE (or not editable by full editors)
    metadata_only = doc.status == StatusDocumento.VIGENTE

    if metadata_only and not pode_meta:
        flash(
            'Para alterar um documento vigente, abra uma nova revisão primeiro.',
            'warning',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    _ensure_documento_matriz_schema()
    form = EditarDocumentoForm(obj=doc)
    form.tipo_documento.choices = _choices_tipos()
    formularios_choices = _formularios_choices()

    if form.validate_on_submit():
        matriz_json = _normalize_matriz_json(form.matriz_correlacao_json.data)
        doc.titulo = form.titulo.data.strip()
        doc.tipo_documento = form.tipo_documento.data
        # Do NOT change elaborado_por_id, revisado_por_id, aprovado_por_id — these are auto-managed
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

    # Pre-populate optional fields with stored values
    if request.method == 'GET':
        form.matriz_correlacao_json.data = doc.matriz_correlacao_json or ''

    return render_template(
        'documentos/editar.html',
        title=f'Editar – {doc.codigo}',
        form=form,
        doc=doc,
        formularios_choices=formularios_choices,
        metadata_only=metadata_only,
    )


# ── Excluir documento (admin apenas) ──────────────────────────────────────────

@documentos.route('/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_documento(id):
    """Permanentemente exclui um documento e todos os seus dados.

    Apenas Administradores podem executar esta ação.
    Remove: registros do BD, arquivos PDF/DOCX, histórico, distribuições.
    """
    if current_user.perfil != Perfil.ADMINISTRADOR:
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    codigo = doc.codigo
    titulo = doc.titulo

    # ── 1. Desassociar registros da Matriz de Correlação ─────────────────────
    MatrizCorrelacao.query.filter_by(documento_id=id).update(
        {'documento_id': None}
    )

    # ── 2. Remover arquivos físicos ──────────────────────────────────────────
    vigentes_dir = current_app.config['VIGENTES_PDF_DIR']
    em_revisao_dir = current_app.config['EM_REVISAO_DIR']
    obsoletos_dir = current_app.config['OBSOLETOS_DIR']
    editaveis_dir = current_app.config['EDITAVEIS_DOCX_DIR']

    arquivos_para_remover = []

    if doc.caminho_pdf_vigente:
        arquivos_para_remover.append(
            os.path.join(vigentes_dir, doc.caminho_pdf_vigente)
        )
    if doc.caminho_obsoleto:
        arquivos_para_remover.append(
            os.path.join(obsoletos_dir, doc.caminho_obsoleto)
        )
    if doc.caminho_docx_editavel:
        arquivos_para_remover.append(
            os.path.join(editaveis_dir, doc.caminho_docx_editavel)
        )

    # Remove PDFs de revisões em andamento
    for rev in doc.revisoes:
        if rev.arquivo_pdf:
            arquivos_para_remover.append(
                os.path.join(em_revisao_dir, rev.arquivo_pdf)
            )
        if rev.arquivo_docx:
            arquivos_para_remover.append(
                os.path.join(em_revisao_dir, rev.arquivo_docx)
            )

    for caminho in arquivos_para_remover:
        try:
            if os.path.isfile(caminho):
                os.remove(caminho)
        except Exception:
            current_app.logger.warning(
                'Não foi possível remover arquivo %s', caminho
            )

    # ── 3. Remover registros do banco de dados ───────────────────────────────
    # As relações com cascade='all, delete-orphan' cuidam de:
    #   revisoes, historico, distribuicoes
    db.session.delete(doc)
    db.session.commit()

    flash(
        f'Documento {codigo} – {titulo} foi excluído permanentemente.',
        'success',
    )
    return redirect(url_for('documentos.lista'))


# ── Upload DOCX ────────────────────────────────────────────────────────────────

@documentos.route('/<int:id>/upload-docx', methods=['POST'])
@login_required
def upload_docx(id):
    flash(
        'Envio de DOCX foi desativado para documentos SGQ. Use apenas o editor online.',
        'warning',
    )
    return redirect(url_for('documentos.detalhe', id=id))


# ── Upload PDF (Rascunho inicial — somente PA e PT) ───────────────────────────

@documentos.route('/<int:id>/upload-pdf', methods=['POST'])
@login_required
@bloquear_auditor
def upload_pdf(id):
    """Upload a PDF for a PA/PT document in Rascunho state.

    The file is stored in EM_REVISAO_DIR under the vigente naming convention.
    It only moves to VIGENTES_PDF_DIR when publicar_vigente is called by an approver.
    """
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    # Upload de PDF disponível para todos os tipos de documentos SGQ
    if doc.status != StatusDocumento.RASCUNHO:
        flash('Upload de PDF de rascunho está disponível apenas para documentos em Rascunho.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    form = UploadPdfForm()
    if not form.validate_on_submit():
        for _field, errs in form.errors.items():
            for e in errs:
                flash(e, 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    arquivo = form.arquivo.data

    # Defensive extension check (Flask-WTF FileAllowed already validates, but double-check)
    if not extensao_permitida(arquivo.filename, ALLOWED_PDF):
        flash('Apenas arquivos PDF são permitidos.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    # Deterministic staged filename in EM_REVISAO_DIR
    nome_arquivo = nome_pdf_vigente(doc.codigo, doc.revisao_atual, doc.titulo)
    em_revisao_dir = current_app.config['EM_REVISAO_DIR']

    try:
        salvar_upload(arquivo, em_revisao_dir, nome_arquivo)
    except Exception:
        current_app.logger.exception('Erro ao salvar PDF de rascunho para doc %s', id)
        flash('Erro ao salvar o arquivo. Tente novamente.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    doc.content_mode = 'uploaded_file'
    doc.content_html = None
    doc.atualizado_em = agora_brasilia()

    descricao = (form.motivo.data or '').strip()
    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.ARQUIVO_ENVIADO,
        f'PDF enviado para rascunho: {nome_arquivo}'
        + (f'. {descricao}' if descricao else ''),
    )
    db.session.commit()

    flash('PDF enviado com sucesso. Publique o documento para torná-lo Vigente.', 'success')
    return redirect(url_for('documentos.detalhe', id=id))


# ── Publicar como Vigente (Etapa 2 simplified import path) ────────────────────

@documentos.route('/<int:id>/publicar-vigente', methods=['POST'])
@login_required
def publicar_vigente(id):
    # Only approvers can publish
    if not current_user.pode_aprovar():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status not in [StatusDocumento.RASCUNHO, StatusDocumento.APROVADO]:
        flash(
            'Apenas documentos em Rascunho ou Aprovado podem ser publicados como Vigente.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    tem_conteudo = (
        (doc.content_mode == 'online_editor' and bool(doc.content_html)) or
        (doc.content_mode == 'uploaded_file')
    )
    if not tem_conteudo:
        flash(
            'É necessário criar conteúdo pelo editor online ou enviar um PDF antes de publicar como Vigente.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    form = PublicarVigenteForm()

    if form.validate_on_submit():
        agora = agora_brasilia()

        # Set approval fields FIRST so they are available for PDF metadata
        doc.aprovado_por_id = current_user.id
        doc.data_aprovacao = agora
        doc.data_publicacao = agora
        doc.status = StatusDocumento.VIGENTE
        doc.atualizado_em = agora

        # For online_editor: PDF is generated on-demand via the imprimir page.
        # For uploaded_file: move the staged PDF to the vigentes directory.
        if doc.content_mode == 'uploaded_file':
            # Move staged PDF from EM_REVISAO_DIR to VIGENTES_PDF_DIR
            nome_pdf_out = nome_pdf_vigente(doc.codigo, doc.revisao_atual, doc.titulo)
            src = caminho_em_revisao(nome_pdf_out)
            dst = caminho_vigente_pdf(nome_pdf_out)
            if arquivo_existe(src):
                mover_arquivo(src, dst)
                doc.caminho_pdf_vigente = nome_pdf_out
            elif arquivo_existe(dst):
                # Already in the right place (re-publish edge case)
                doc.caminho_pdf_vigente = nome_pdf_out
            else:
                flash('Arquivo PDF enviado não encontrado. Reenvie o PDF e tente novamente.', 'danger')
                return redirect(url_for('documentos.detalhe', id=id))

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

        # Se for PT, cria alerta no dashboard + flag para modal na tela
        if doc.codigo and doc.codigo.upper().startswith('PT'):
            _criar_alerta_pt(doc.codigo)

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

@documentos.route('/<int:id>/regenerar-pdf', methods=['POST'])
@login_required
def regenerar_pdf(id):
    """Re-gera o PDF vigente a partir do conteúdo online (editor). Útil quando o
    arquivo está corrompido, ausente ou precisa ser atualizado após correção de CSS."""
    if not current_user.pode_aprovar():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if doc.status != StatusDocumento.VIGENTE:
        flash('Só é possível regenerar o PDF de documentos Vigentes.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    if doc.content_mode != 'online_editor' or not doc.content_html:
        flash('Este documento não possui conteúdo no editor online para regenerar o PDF.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    from app.utils.html_pdf import gerar_pdf_de_html, metadata_from_documento
    meta = metadata_from_documento(doc)
    meta['status'] = StatusDocumento.VIGENTE
    meta['historico_revisoes'] = _build_historico_revisoes(doc)

    nome_pdf_out = nome_pdf_vigente(doc.codigo, doc.revisao_atual, doc.titulo)
    caminho_pdf_out = caminho_vigente_pdf(nome_pdf_out)

    ok = gerar_pdf_de_html(doc.content_html, meta, caminho_pdf_out)
    if ok:
        doc.caminho_pdf_vigente = nome_pdf_out
        doc.atualizado_em = agora_brasilia()
        registrar_evento(
            doc.id, current_user.id,
            AcaoEvento.PUBLICADO_VIGENTE,
            'PDF regenerado manualmente.',
        )
        db.session.commit()
        flash(f'PDF do {doc.codigo} regenerado com sucesso!', 'success')
    else:
        flash('Falha ao regenerar o PDF. Verifique o log do servidor.', 'danger')

    return redirect(url_for('documentos.detalhe', id=id))


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

    if not (doc.content_mode == 'online_editor' and doc.content_html) and \
            not (doc.content_mode == 'uploaded_file' and doc.caminho_pdf_vigente):
        flash(
            'Somente documentos com conteúdo (editor online ou PDF enviado) podem abrir revisão.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

    nova_revisao_num = doc.revisao_atual + 1

    revisao = RevisaoDocumento(
        documento_id=doc.id,
        numero_revisao=nova_revisao_num,
        status=StatusDocumento.EM_REVISAO,
        motivo_alteracao=form.motivo.data.strip(),
        elaborado_por_id=current_user.id,
        data_elaboracao=agora_brasilia(),
        arquivo_docx=None,
        content_html=doc.content_html if doc.content_mode == 'online_editor' else None,
        content_mode=doc.content_mode,
    )

    # Auto-assign default reviewer if one is configured
    revisor = Usuario.revisor_padrao_ativo()
    if revisor:
        revisao.revisado_por_id = revisor.id

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
    flash(
        'Envio de DOCX foi desativado para revisões SGQ. Use apenas o editor online.',
        'warning',
    )
    return redirect(url_for('documentos.detalhe', id=id))


# ── Upload PDF para revisão em andamento ──────────────────────────────────────

@documentos.route('/<int:id>/revisoes/<int:rev_id>/upload-pdf', methods=['POST'])
@login_required
@bloquear_auditor
def upload_pdf_revisao(id, rev_id):
    """Upload a PDF for a PA/PT revision in Em revisão state."""
    if not current_user.pode_editar_documentos():
        abort(403)

    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(
        id=rev_id, documento_id=id
    ).first_or_404()

    # Upload de PDF disponível para todos os tipos de documentos SGQ
    if revisao.status != StatusDocumento.EM_REVISAO:
        flash('Upload de PDF disponível apenas para revisões em andamento (Em revisão).', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    form = UploadPdfForm()
    if not form.validate_on_submit():
        for _field, errs in form.errors.items():
            for e in errs:
                flash(e, 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    arquivo = form.arquivo.data

    if not extensao_permitida(arquivo.filename, ALLOWED_PDF):
        flash('Apenas arquivos PDF são permitidos.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    # Revision-scoped filename in EM_REVISAO_DIR
    nome_arquivo = nome_pdf_vigente(doc.codigo, revisao.numero_revisao, doc.titulo)
    em_revisao_dir = current_app.config['EM_REVISAO_DIR']

    try:
        salvar_upload(arquivo, em_revisao_dir, nome_arquivo)
    except Exception:
        current_app.logger.exception('Erro ao salvar PDF de revisão para doc %s rev %s', id, rev_id)
        flash('Erro ao salvar o arquivo. Tente novamente.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    revisao.content_mode = 'uploaded_file'
    revisao.content_html = None
    revisao.arquivo_pdf = nome_arquivo
    doc.atualizado_em = agora_brasilia()

    descricao = (form.motivo.data or '').strip()
    registrar_evento(
        doc.id, current_user.id,
        AcaoEvento.ARQUIVO_ENVIADO,
        f'PDF enviado para revisão Rev{revisao.numero_revisao:02d}: {nome_arquivo}'
        + (f'. {descricao}' if descricao else ''),
    )
    db.session.commit()

    flash('PDF enviado com sucesso. Envie para aprovação quando estiver pronto.', 'success')
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

    tem_conteudo_revisao = (
        (revisao.content_mode == 'online_editor' and bool(revisao.content_html)) or
        (revisao.content_mode == 'uploaded_file' and bool(revisao.arquivo_pdf))
    )
    if not tem_conteudo_revisao:
        flash(
            'A revisão precisa ter conteúdo do editor online ou PDF enviado antes do envio para aprovação.',
            'danger',
        )
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

    if not form.validate_on_submit():
        flash('Erro ao aprovar revisão. Tente novamente.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

    agora = agora_brasilia()
    vigentes_dir = current_app.config['VIGENTES_PDF_DIR']
    obsoletos_dir = current_app.config['OBSOLETOS_DIR']

    # ── Set approval metadata ──────────────────────────────────────────────────
    # Approval is done by current_user; keep elaborado and revisado as-is
    revisao.aprovado_por_id = current_user.id
    revisao.data_revisao = agora
    revisao.data_aprovacao = agora

    # ── Generate / copy PDF ────────────────────────────────────────────────────
    pdf_gerado = False
    nome_pdf_novo = nome_pdf_vigente(doc.codigo, revisao.numero_revisao, doc.titulo)

    # For online_editor: no PDF stored — generated on-demand via imprimir page.
    if revisao.content_mode == 'online_editor' and revisao.content_html:
        pdf_gerado = False  # PDF will be printed from browser when needed
    elif revisao.content_mode == 'uploaded_file' and revisao.arquivo_pdf:
        src = caminho_em_revisao(revisao.arquivo_pdf)
        dst = os.path.join(vigentes_dir, nome_pdf_novo)
        if arquivo_existe(src):
            copiar_arquivo(src, dst)
            pdf_gerado = True
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.PDF_GERADO,
                f'PDF copiado do arquivo enviado: {nome_pdf_novo}',
            )
        else:
            flash('Arquivo PDF da revisão não encontrado. Reenvie o PDF e tente novamente.', 'danger')
            return redirect(url_for('documentos.detalhe', id=id))
    else:
        flash('Conteúdo ausente. Adicione conteúdo (editor online ou PDF) antes de aprovar.', 'danger')
        return redirect(url_for('documentos.detalhe', id=id))

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

    # ── Update Documento → Vigente ─────────────────────────────────────────────
    revisao_anterior_num = doc.revisao_atual
    doc.revisao_atual = revisao.numero_revisao
    doc.status = StatusDocumento.VIGENTE
    # Only store PDF path for uploaded files; online content uses the imprimir page.
    if pdf_gerado:
        doc.caminho_pdf_vigente = nome_pdf_novo
    elif revisao.content_mode == 'online_editor':
        doc.caminho_pdf_vigente = None
    # Auto-set approval user
    doc.aprovado_por_id = current_user.id
    # Keep elaborado and revisado from revision (or maintain as-is if not already set)
    if revisao.elaborado_por_id:
        doc.elaborado_por_id = revisao.elaborado_por_id
    if revisao.revisado_por_id:
        doc.revisado_por_id = revisao.revisado_por_id
    doc.data_aprovacao = agora
    doc.data_publicacao = agora
    doc.atualizado_em = agora
    if revisao.content_mode == 'online_editor':
        doc.content_html = revisao.content_html
        doc.content_mode = revisao.content_mode
    elif revisao.content_mode == 'uploaded_file':
        doc.content_html = None
        doc.content_mode = 'uploaded_file'

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
        f'Rev{revisao.numero_revisao:02d} aprovada e publicada por {current_user.nome}. '
        f'Elaborado: {revisao.elaborado_por.nome if revisao.elaborado_por else "-"}, '
        f'Revisado: {revisao.revisado_por.nome if revisao.revisado_por else "-"}.',
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

    # Se for PT, cria alerta no dashboard + flag para modal
    if doc.codigo and doc.codigo.upper().startswith('PT'):
        _criar_alerta_pt(doc.codigo)

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
    obsoletos_dir = current_app.config['OBSOLETOS_DIR']

    # ── 1. Generate PDF ────────────────────────────────────────────────────────
    pdf_gerado = False
    nome_pdf_novo = nome_pdf_vigente(doc.codigo, revisao.numero_revisao, doc.titulo)

    # For online_editor: no PDF stored — generated on-demand via imprimir page.
    if revisao.content_mode == 'online_editor' and revisao.content_html:
        pdf_gerado = False  # PDF will be printed from browser when needed
    elif revisao.content_mode == 'uploaded_file' and revisao.arquivo_pdf:
        src = caminho_em_revisao(revisao.arquivo_pdf)
        dst = os.path.join(vigentes_dir, nome_pdf_novo)
        if arquivo_existe(src):
            mover_arquivo(src, dst)
            pdf_gerado = True
            registrar_evento(
                doc.id, current_user.id,
                AcaoEvento.PDF_GERADO,
                f'PDF movido do arquivo enviado: {nome_pdf_novo}',
            )
        elif arquivo_existe(dst):
            # File already in destination (edge case — already approved)
            pdf_gerado = True
        else:
            flash('Arquivo PDF da revisão não encontrado. Reenvie o PDF e tente novamente.', 'danger')
            return redirect(url_for('documentos.detalhe', id=id))
    else:
        flash(
            'A revisão precisa ter conteúdo (editor online ou PDF enviado) para ser publicada.',
            'danger',
        )
        return redirect(url_for('documentos.detalhe', id=id))

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

    # ── 3. Update Documento ───────────────────────────────────────────────────
    revisao_anterior_num = doc.revisao_atual
    doc.revisao_atual = revisao.numero_revisao
    doc.status = StatusDocumento.VIGENTE
    # Only store PDF path for uploaded files; online content uses the imprimir page.
    if pdf_gerado:
        doc.caminho_pdf_vigente = nome_pdf_novo
    elif revisao.content_mode == 'online_editor':
        doc.caminho_pdf_vigente = None
    doc.elaborado_por_id = revisao.elaborado_por_id
    doc.revisado_por_id = revisao.revisado_por_id
    doc.aprovado_por_id = revisao.aprovado_por_id
    doc.data_aprovacao = revisao.data_aprovacao or agora
    doc.data_publicacao = agora
    doc.atualizado_em = agora
    # Carry content mode to document record
    if revisao.content_mode == 'online_editor':
        doc.content_html = revisao.content_html
        doc.content_mode = revisao.content_mode
    elif revisao.content_mode == 'uploaded_file':
        doc.content_html = None
        doc.content_mode = 'uploaded_file'

    # ── 4. Update revision ────────────────────────────────────────────────────
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

    # Se for PT, cria alerta no dashboard + flag para modal
    if doc.codigo and doc.codigo.upper().startswith('PT'):
        _criar_alerta_pt(doc.codigo)

    return redirect(url_for('documentos.detalhe', id=id))


# ── PT Alert helper ────────────────────────────────────────────────────────────

def _criar_alerta_pt(codigo: str):
    """Cria um alerta no dashboard + marca sessão para exibir modal na tela."""
    from flask import session
    from app.utils.datetime_utils import agora_brasilia

    data_str = agora_brasilia().strftime('%d/%m/%Y')
    mensagem = (
        f'⚠️ O procedimento técnico {codigo} foi alterado em {data_str}. '
        f'Necessário atualizar as revisões nas Ordens de Serviço.'
    )
    Alerta.criar(mensagem, tipo='warning', categoria='pt_alterado')
    # Flag para exibir modal com OK na próxima renderização
    session['pt_alerta_modal'] = codigo
    session['pt_alerta_data'] = data_str


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


@documentos.route('/<int:id>/imprimir', methods=['GET'])
@login_required
def imprimir_documento(id):
    """Standalone print page — opens imprimir.html for browser Print → Save as PDF."""
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    content = doc.content_html
    if not content:
        flash('Não há conteúdo online para imprimir.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    return render_template(
        'documentos/imprimir.html',
        doc=doc,
        revisao=None,
        titulo=doc.titulo,
        codigo=doc.codigo,
        revisao_num=doc.revisao_atual,
        status=doc.status,
        content_html=content,
        historico_revisoes=_build_historico_revisoes(doc),
        revisor_global=Usuario.revisor_padrao_ativo(),
    )


@documentos.route('/<int:id>/revisoes/<int:rev_id>/imprimir', methods=['GET'])
@login_required
def imprimir_revisao(id, rev_id):
    """Standalone print page for a revision."""
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(id=rev_id, documento_id=id).first_or_404()

    content = revisao.content_html or doc.content_html
    if not content:
        flash('Não há conteúdo online para imprimir.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    return render_template(
        'documentos/imprimir.html',
        doc=doc,
        revisao=revisao,
        titulo=doc.titulo,
        codigo=doc.codigo,
        revisao_num=revisao.numero_revisao,
        status=revisao.status,
        content_html=content,
        historico_revisoes=_build_historico_revisoes(doc, incluir_revisao=revisao),
        revisor_global=Usuario.revisor_padrao_ativo(),
    )


@documentos.route('/<int:id>/preview-online', methods=['GET'])
@login_required
@bloquear_auditor
def preview_documento(id):
    """Preview online content of a Rascunho document."""
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()

    if not doc.content_html:
        flash('Não há conteúdo online para visualizar.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    publicar_form = PublicarVigenteForm()

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
        tem_aprovadores=current_user.pode_aprovar(),
        revisao_ativa=None,
        revisor_global=Usuario.revisor_padrao_ativo(),
    )


@documentos.route('/<int:id>/revisoes/<int:rev_id>/preview-online', methods=['GET'])
@login_required
@bloquear_auditor
def preview_revisao(id, rev_id):
    """Preview online content of an active revision."""
    doc = Documento.query.filter_by(id=id, ativo=True).first_or_404()
    revisao = RevisaoDocumento.query.filter_by(id=rev_id, documento_id=id).first_or_404()

    if not revisao.content_html:
        flash('Não há conteúdo online para visualizar nesta revisão.', 'warning')
        return redirect(url_for('documentos.detalhe', id=id))

    aprovar_form = AprovarRevisaoForm()

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
        tem_aprovadores=current_user.pode_aprovar(),
        revisao_ativa=revisao,
        revisor_global=Usuario.revisor_padrao_ativo(),
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
        registrar_evento(
            usuario_id=current_user.id,
            acao=AcaoEvento.DOCUMENTO_EXTERNO_ADICIONADO,
            descricao=f'{codigo_novo or titulo_novo} — {form.orgao_emissor.data or "Sem órgão"}',
        )
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
    docs_externos = query.all()
    _ordenar_docs_externos(docs_externos)

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

    registrar_evento(
        usuario_id=current_user.id,
        acao=AcaoEvento.DOCUMENTO_EXTERNO_EDITADO,
        descricao=f'{doc.codigo or doc.titulo} — {doc.orgao_emissor or "Sem órgão"}',
    )
    db.session.commit()
    flash('Documento externo atualizado!', 'success')
    return redirect(url_for('documentos.documentos_externos'))


@documentos.route('/externos/excluir/<int:id>', methods=['POST'])
@login_required
def excluir_externo(id):
    """Exclui permanentemente um documento externo. Apenas Admin."""
    if current_user.perfil != Perfil.ADMINISTRADOR:
        abort(403)

    doc = DocumentoExterno.query.get_or_404(id)
    codigo_ou_titulo = doc.codigo or doc.titulo

    # Remove arquivo físico
    if doc.arquivo_pdf:
        ext_dir = current_app.config['EXTERNOS_DIR']
        caminho = os.path.join(ext_dir, doc.arquivo_pdf)
        try:
            if os.path.isfile(caminho):
                os.remove(caminho)
        except Exception:
            current_app.logger.warning(
                'Não foi possível remover arquivo %s', caminho
            )

    registrar_evento(
        usuario_id=current_user.id,
        acao=AcaoEvento.DOCUMENTO_EXTERNO_EXCLUIDO,
        descricao=f'{codigo_ou_titulo}',
    )
    db.session.delete(doc)
    db.session.commit()
    flash(
        f'Documento externo "{codigo_ou_titulo}" excluído permanentemente.',
        'success',
    )
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

