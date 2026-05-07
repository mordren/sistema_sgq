"""
HTML → PDF generation for online-editor documents.

Uses xhtml2pdf (pisa), which wraps ReportLab and handles basic HTML/CSS.
Called during publication of documents created via the online editor.
"""
from __future__ import annotations

import base64
import io
import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)

# ── Logo helper ────────────────────────────────────────────────────────────────

_IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'images')


def _logo_html() -> str:
    """Return an <img> tag with base64-encoded logo, or org name as text."""
    logo_path = os.path.normpath(os.path.join(_IMAGES_DIR, 'logo.png'))
    if os.path.exists(logo_path):
        try:
            with open(logo_path, 'rb') as fh:
                b64 = base64.b64encode(fh.read()).decode('ascii')
            return (
                f'<img src="data:image/png;base64,{b64}" '
                f'style="max-width:100%;max-height:55px;object-fit:contain;" />'
            )
        except Exception:
            pass
    return 'CSV Cascavel'


# ── Revision-history helper ────────────────────────────────────────────────────

def _historico_html(historico_revisoes: list) -> str:
    """Render the revision-history table rows as an HTML string."""
    if not historico_revisoes:
        return ''

    rows = []
    for entry in historico_revisoes:
        num = entry.get('numero', '')
        data = entry.get('data')
        if isinstance(data, datetime):
            data_str = data.strftime('%d/%m/%Y')
        elif data:
            data_str = str(data)
        else:
            data_str = '—'
        descricao = entry.get('descricao', '—') or '—'
        item = entry.get('item', '—') or '—'
        autor = entry.get('elaborado_por', '—') or '—'
        rows.append(
            f'<tr>'
            f'<td style="text-align:center">Rev{int(num):02d}</td>'
            f'<td style="text-align:center">{data_str}</td>'
            f'<td>{descricao}</td>'
            f'<td style="text-align:center">{item}</td>'
            f'<td style="text-align:center">{autor}</td>'
            f'</tr>'
        )
    return '\n'.join(rows)

# ── Official PDF print template ────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<style>
  @page {{
    size: A4;
    margin: 2cm 2cm 2.5cm 2cm;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: Arial, Helvetica, sans-serif;
    font-size: 10pt;
    color: #000;
    line-height: 1.4;
  }}
  /* \u2500\u2500 Document header \u2500\u2500 */
  .doc-header {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12px;
  }}
  .doc-header td {{
    border: 1px solid #000;
    padding: 5px 8px;
    vertical-align: middle;
  }}
  .org-name {{
    font-size: 11pt;
    font-weight: bold;
    text-align: center;
    width: 28%;
  }}
  .doc-title-cell {{
    font-size: 13pt;
    font-weight: bold;
    text-align: center;
    width: 72%;
  }}
  .meta-label {{ font-weight: bold; }}
  /* \u2500\u2500 Signatories \u2500\u2500 */
  .signatories {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 10px;
  }}
  .signatories td {{
    border: 1px solid #000;
    padding: 5px 8px;
    width: 33.33%;
    font-size: 9pt;
  }}
  /* \u2500\u2500 Revision history \u2500\u2500 */
  .rev-history {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 16px;
    font-size: 8.5pt;
  }}
  .rev-history th {{
    background-color: #d0d0d0;
    border: 1px solid #000;
    padding: 3px 5px;
    font-weight: bold;
    text-align: center;
  }}
  .rev-history td {{
    border: 1px solid #000;
    padding: 3px 5px;
    vertical-align: top;
  }}
  .rev-section-title {{
    font-weight: bold;
    font-size: 9pt;
    margin: 8px 0 3px 0;
  }}
  /* \u2500\u2500 Content \u2500\u2500 */
  .content {{ margin-top: 8px; }}
  .content h1 {{ font-size: 12pt; font-weight: bold; margin: 14px 0 6px; }}
  .content h2 {{ font-size: 11pt; font-weight: bold; margin: 12px 0 5px; }}
  .content h3 {{ font-size: 10pt; font-weight: bold; margin: 10px 0 4px; }}
  .content p  {{ margin: 6px 0; }}
  .content ul, .content ol {{ margin: 6px 0 6px 20px; padding: 0; }}
  .content li {{ margin: 3px 0; }}
  .content table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
    margin: 8px 0;
    font-size: 9pt;
    word-wrap: break-word;
  }}
  .content table td,
  .content table th {{
    border: 1px solid #888;
    padding: 4px 6px;
    vertical-align: top;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }}
  .content table th {{ background-color: #e8e8e8; font-weight: bold; text-align: left; }}
  .content strong {{ font-weight: bold; }}
  .content em     {{ font-style: italic; }}
  .content u      {{ text-decoration: underline; }}
  a {{ color: #000; text-decoration: underline; }}
</style>
</head>
<body>

<!-- \u2500\u2500 Header table \u2500\u2500 -->
<table class="doc-header">
  <tr>
    <td class="org-name" rowspan="3">{logo_html}</td>
    <td class="doc-title-cell" colspan="2">{titulo}</td>
  </tr>
  <tr>
    <td><span class="meta-label">C\u00f3digo:</span> {codigo}</td>
    <td><span class="meta-label">Revis\u00e3o:</span> Rev{revisao:02d}</td>
  </tr>
  <tr>
    <td><span class="meta-label">Data de Aprova\u00e7\u00e3o:</span> {data_aprovacao}</td>
    <td><span class="meta-label">Status:</span> {status}</td>
  </tr>
</table>

<!-- \u2500\u2500 Signatories \u2500\u2500 -->
<table class="signatories">
  <tr>
    <td><span class="meta-label">Elaborado por:</span><br/>{elaborado_por}</td>
    <td><span class="meta-label">Revisado por:</span><br/>{revisado_por}</td>
    <td><span class="meta-label">Aprovado por:</span><br/>{aprovado_por}</td>
  </tr>
</table>

<!-- \u2500\u2500 Revision history \u2500\u2500 -->
{historico_section}

<!-- \u2500\u2500 Procedure content \u2500\u2500 -->
<div class="content">
{content_html}
</div>

</body>
</html>
"""


def _nome_usuario(usuario_obj) -> str:
    if usuario_obj is None:
        return '\u2014'
    return str(usuario_obj.nome)


def gerar_pdf_de_html(
    content_html: str,
    metadata: dict,
    caminho_saida: str,
) -> bool:
    """
    Generate a PDF from HTML content using the official print template.

    Parameters
    ----------
    content_html : str
        The procedure body (HTML from CKEditor).
    metadata : dict with keys:
        titulo, codigo, revisao (int), status,
        data_aprovacao (datetime|None),
        elaborado_por (str), revisado_por (str), aprovado_por (str)
    caminho_saida : str
        Full filesystem path to write the output PDF.

    Returns
    -------
    bool — True on success, False on failure.
    """
    try:
        from xhtml2pdf import pisa  # lazy import — optional dependency
    except ImportError:
        log.error('xhtml2pdf não está instalado. Execute: pip install xhtml2pdf')
        return False

    data_apr = metadata.get('data_aprovacao')
    if isinstance(data_apr, datetime):
        data_apr_str = data_apr.strftime('%d/%m/%Y')
    elif data_apr:
        data_apr_str = str(data_apr)
    else:
        data_apr_str = '\u2014'

    # Build revision history section
    hist_rows = _historico_html(metadata.get('historico_revisoes') or [])
    if hist_rows:
        historico_section = (
            '<p class="rev-section-title">Hist\u00f3rico de Revis\u00f5es</p>'
            '<table class="rev-history">'
            '<tr>'
            '<th style="width:8%">Rev</th>'
            '<th style="width:12%">Data</th>'
            '<th style="width:42%">Descri\u00e7\u00e3o das Altera\u00e7\u00f5es</th>'
            '<th style="width:18%">Item(s) Alterado(s)</th>'
            '<th style="width:20%">Elaborado por</th>'
            '</tr>'
            + hist_rows
            + '</table>'
        )
    else:
        historico_section = ''

    full_html = _HTML_TEMPLATE.format(
        logo_html=_logo_html(),
        titulo=metadata.get('titulo', ''),
        codigo=metadata.get('codigo', ''),
        revisao=int(metadata.get('revisao', 0)),
        data_aprovacao=data_apr_str,
        status=metadata.get('status', ''),
        elaborado_por=metadata.get('elaborado_por', '\u2014'),
        revisado_por=metadata.get('revisado_por', '\u2014'),
        aprovado_por=metadata.get('aprovado_por', '\u2014'),
        historico_section=historico_section,
        content_html=content_html or '',
    )

    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)

    try:
        with open(caminho_saida, 'wb') as f:
            result = pisa.CreatePDF(
                src=io.StringIO(full_html),
                dest=f,
                encoding='utf-8',
            )
        if result.err:
            log.error('xhtml2pdf reported errors: %s', result.err)
            return False
        return True
    except Exception as exc:
        log.exception('PDF generation failed: %s', exc)
        return False


def metadata_from_documento(doc) -> dict:
    """Build a metadata dict from a Documento ORM object."""
    return {
        'titulo': doc.titulo,
        'codigo': doc.codigo,
        'revisao': doc.revisao_atual,
        'status': doc.status,
        'data_aprovacao': doc.data_aprovacao,
        'elaborado_por': _nome_usuario(getattr(doc, 'elaborado_por', None)),
        'revisado_por': _nome_usuario(getattr(doc, 'revisado_por', None)),
        'aprovado_por': _nome_usuario(getattr(doc, 'aprovado_por', None)),
    }


def metadata_from_revisao(doc, revisao) -> dict:
    """Build a metadata dict from a RevisaoDocumento + parent Documento."""
    return {
        'titulo': doc.titulo,
        'codigo': doc.codigo,
        'revisao': revisao.numero_revisao,
        'status': revisao.status,
        'data_aprovacao': revisao.data_aprovacao,
        'elaborado_por': _nome_usuario(getattr(revisao, 'elaborado_por', None)),
        'revisado_por': _nome_usuario(getattr(revisao, 'revisado_por', None)),
        'aprovado_por': _nome_usuario(getattr(revisao, 'aprovado_por', None)),
    }
