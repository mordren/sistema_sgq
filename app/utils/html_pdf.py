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
    margin: 14mm 15mm 20mm 15mm;
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
    <td><span class="meta-label">Revis\u00e3o:</span> Rev{revisao_display}</td>
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

    # Prepare safe display values for header (fallbacks per rules)
    rev_val = metadata.get('revisao')
    if rev_val is None:
        revisao_display = 'S/R'
    else:
        try:
            revisao_display = f'{int(rev_val):02d}'
        except Exception:
            revisao_display = str(rev_val)

    codigo_display = metadata.get('codigo') or 'S/C'
    titulo_display = metadata.get('titulo') or 'Sem título'

    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)

    # Inline editor-uploaded images as base64 into content_html BEFORE
    # inserting into the template, so xhtml2pdf can render them without HTTP.
    try:
        from flask import current_app as _app
        _imagens_dir = _app.config.get('EDITOR_IMAGENS_DIR', '')
    except Exception:
        _imagens_dir = ''

    _content_for_pdf = (
        _inline_editor_images(content_html, _imagens_dir)
        if _imagens_dir and content_html
        else (content_html or '')
    )

    pdf_html = _HTML_TEMPLATE.format(
        logo_html=_logo_html(),
        titulo=titulo_display,
        codigo=codigo_display,
        revisao_display=revisao_display,
        data_aprovacao=data_apr_str,
        status=metadata.get('status', ''),
        elaborado_por=metadata.get('elaborado_por', '—'),
        revisado_por=metadata.get('revisado_por', '—'),
        aprovado_por=metadata.get('aprovado_por', '—'),
        historico_section=historico_section,
        content_html=_content_for_pdf,
    )

    try:
        with open(caminho_saida, 'wb') as f:
            result = pisa.CreatePDF(
                src=io.StringIO(pdf_html),
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


def _inline_editor_images(html: str, imagens_dir: str) -> str:
    """Return *html* with every editor-image <img src> replaced by a base64 data URI.

    Uses Python's html.parser so it handles any quote style, extra attributes,
    and URL format (relative /documentos/editor/imagem/ or absolute http://...).
    Works on the raw content_html fragment before it is inserted into the PDF template.
    """
    from html.parser import HTMLParser
    import mimetypes

    _IMAGE_ROUTE_PARTS = ('editor', 'imagem')

    def _filename_from_editor_url(url: str) -> str | None:
        """Extract the stored editor image filename from absolute or relative URLs."""
        from urllib.parse import unquote, urlparse

        parsed = urlparse(url)
        path = unquote(parsed.path or url)
        normalized = path.replace('\\', '/')
        parts = [part for part in normalized.split('/') if part and part != '.']

        for idx in range(len(parts) - 2, -1, -1):
            if tuple(part.lower() for part in parts[idx:idx + 2]) == _IMAGE_ROUTE_PARTS:
                return os.path.basename(parts[idx + 2]) if idx + 2 < len(parts) else None

        return None

    def _to_data_uri(url: str):
        """Convert an editor image URL to a base64 data URI, or return None."""
        filename = _filename_from_editor_url(url)
        if not filename:
            return None
        filepath = os.path.join(imagens_dir, filename)
        if not os.path.isfile(filepath):
            log.warning('Editor image not found for PDF: %s', filepath)
            return None
        try:
            mime, _ = mimetypes.guess_type(filepath)
            mime = mime or 'image/png'
            with open(filepath, 'rb') as fh:
                b64 = base64.b64encode(fh.read()).decode('ascii')
            log.debug('Inlined editor image %s for PDF', filename)
            return f'data:{mime};base64,{b64}'
        except Exception:
            log.exception('Failed to read editor image %s', filepath)
            return None

    class _ImgInliner(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.out = []

        def handle_starttag(self, tag, attrs):
            if tag.lower() == 'img':
                new_attrs = []
                for name, value in attrs:
                    if name.lower() == 'src' and value:
                        data_uri = _to_data_uri(value)
                        if data_uri:
                            value = data_uri
                    new_attrs.append((name, value))
                attrs = new_attrs
            parts = [tag]
            for name, value in attrs:
                if value is None:
                    parts.append(name)
                else:
                    parts.append(f'{name}="{value}"')
            self.out.append('<' + ' '.join(parts) + '>')

        def handle_endtag(self, tag):
            self.out.append(f'</{tag}>')

        def handle_startendtag(self, tag, attrs):
            # Self-closing tags like <img .../>
            self.handle_starttag(tag, attrs)
            # Remove the > added by handle_starttag and close properly
            if self.out and self.out[-1].endswith('>'):
                self.out[-1] = self.out[-1][:-1] + ' />'

        def handle_data(self, data):
            self.out.append(data)

        def handle_entityref(self, name):
            self.out.append(f'&{name};')

        def handle_charref(self, name):
            self.out.append(f'&#{name};')

        def handle_comment(self, data):
            self.out.append(f'<!--{data}-->')

    parser = _ImgInliner()
    parser.feed(html)
    return ''.join(parser.out)


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



def _safe_meta_for_header(metadata: dict) -> dict:
    """Return safe header metadata with fallbacks per project rules."""
    codigo = metadata.get('codigo') or 'S/C'
    titulo = metadata.get('titulo') or 'Sem título'
    revisao = metadata.get('revisao')
    if revisao is None:
        revisao_display = 'S/R'
    else:
        try:
            revisao_display = f'{int(revisao):02d}'
        except Exception:
            revisao_display = str(revisao)
    return {'codigo': codigo, 'titulo': titulo, 'revisao': revisao_display}


def NumberedCanvasFactory(metadata: dict):
    """Return a ReportLab Canvas class that draws a running header with page X/Y.

    Use as: doc.build(elements, canvasmaker=NumberedCanvasFactory(meta))
    """
    try:
        from reportlab.pdfgen.canvas import Canvas
    except Exception:
        return None

    safe = _safe_meta_for_header(metadata or {})

    class NumberedCanvas(Canvas):
      def __init__(self, *args, **kwargs):
        Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

      def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        Canvas.showPage(self)

      def save(self):
        # Add page count to each saved page and write them out
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
          self.__dict__.update(state)
          self._draw_header(num_pages)
          Canvas.showPage(self)
        Canvas.save(self)

      def _draw_header(self, total_pages: int) -> None:
        self.saveState()
        try:
          codigo = safe.get('codigo', 'S/C')
          titulo = safe.get('titulo', 'Sem título')
          revisao = safe.get('revisao', 'S/R')
          cur = getattr(self, '_pageNumber', 1)
          text = f"{codigo} - {titulo} - Rev{revisao} - Pg. {cur}/{total_pages}"
          # small font, centered near top (leave some margin)
          width, height = self._pagesize
          self.setFont('Helvetica', 8)
          y = height - (12 * mm_to_pt_factor())  # approx 12 mm from top
          self.drawCentredString(width / 2.0, y, text)
        finally:
          self.restoreState()

    return NumberedCanvas


def mm_to_pt_factor():
    # 1 mm = 2.8346456693 points
    return 2.8346456693


def _format_signature_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    if hasattr(value, 'strftime'):
        try:
            return value.strftime('%d/%m/%Y')
        except Exception:
            pass
    return str(value) if value else 'S/D'


def _signature_text(metadata: dict) -> str:
    signed_at = (
        metadata.get('data_assinatura')
        or metadata.get('data_aprovacao')
        or metadata.get('data_publicacao')
    )
    user = (
        metadata.get('usuario_assinatura')
        or metadata.get('aprovado_por')
        or metadata.get('revisado_por')
        or metadata.get('elaborado_por')
        or 'Usuário não identificado'
    )
    return (
        'O documento foi assinado digitalmente através do login no sistema SGQ '
        f'no dia {_format_signature_date(signed_at)} pelo {user}.'
    )


def _fit_text_to_width(text: str, max_width: float, font: str, size: int) -> str:
    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except Exception:
        return text

    if stringWidth(text, font, size) <= max_width:
        return text

    clipped = text
    while len(clipped) > 4 and stringWidth(clipped + '...', font, size) > max_width:
        clipped = clipped[:-1]
    return clipped + '...'


def _wrap_text_to_width(text: str, max_width: float, font: str, size: int) -> list[str]:
    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth
    except Exception:
        return [text]

    lines = []
    current = ''
    for word in text.split():
        candidate = f'{current} {word}'.strip()
        if current and stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:2] or ['']


def _draw_pdf_marks(canvas_obj, width: float, height: float, metadata: dict, page_no: int, total_pages: int) -> None:
    safe = _safe_meta_for_header(metadata or {})
    header = (
        f"{safe.get('codigo', 'S/C')} - {safe.get('titulo', 'Sem título')} - "
        f"Rev{safe.get('revisao', 'S/R')} - Pg. {page_no}/{total_pages}"
    )

    canvas_obj.saveState()
    try:
        margin_x = 15 * mm_to_pt_factor()

        canvas_obj.setFont('Helvetica', 8)
        header = _fit_text_to_width(
            header,
            width - (2 * margin_x),
            'Helvetica',
            8,
        )
        canvas_obj.drawCentredString(width / 2.0, height - (8 * mm_to_pt_factor()), header)
        canvas_obj.line(
            margin_x,
            height - (10 * mm_to_pt_factor()),
            width - margin_x,
            height - (10 * mm_to_pt_factor()),
        )

        canvas_obj.setFont('Helvetica', 7)
        footer_lines = _wrap_text_to_width(
            _signature_text(metadata or {}),
            width - (2 * margin_x),
            'Helvetica',
            7,
        )
        canvas_obj.line(margin_x, 13 * mm_to_pt_factor(), width - margin_x, 13 * mm_to_pt_factor())
        first_y = 9 * mm_to_pt_factor()
        for idx, line in enumerate(footer_lines):
            canvas_obj.drawCentredString(width / 2.0, first_y - (idx * 8), line)
    finally:
        canvas_obj.restoreState()


def _overlay_header_footer_to_buffer(source_pdf_path: str, metadata: dict):
    if not os.path.exists(source_pdf_path):
        return None

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
        reader = PdfReader(source_pdf_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)

        for pageno, page in enumerate(reader.pages, start=1):
            try:
                media = page.mediabox
                width = float(media.width)
                height = float(media.height)
            except Exception:
                from reportlab.lib.pagesizes import A4
                width, height = A4

            packet = io.BytesIO()
            c = rl_canvas.Canvas(packet, pagesize=(width, height))
            _draw_pdf_marks(c, width, height, metadata or {}, pageno, total_pages)
            c.save()
            packet.seek(0)

            overlay_reader = PdfReader(packet)
            overlay_page = overlay_reader.pages[0]
            try:
                page.merge_page(overlay_page)
            except Exception:
                try:
                    page.mergePage(overlay_page)
                except Exception:
                    pass

            writer.add_page(page)

        out_buf = io.BytesIO()
        writer.write(out_buf)
        out_buf.seek(0)
        return out_buf
    except Exception:
        log.exception('Failed to overlay PDF header/footer')
        return None


def _overlay_header_footer_on_file(source_pdf_path: str, metadata: dict) -> bool:
    buf = _overlay_header_footer_to_buffer(source_pdf_path, metadata)
    if not buf:
        return False

    tmp_path = source_pdf_path + '.marked.pdf'
    try:
        with open(tmp_path, 'wb') as fh:
            fh.write(buf.getvalue())
        os.replace(tmp_path, source_pdf_path)
        return True
    except Exception:
        log.exception('Failed to write PDF header/footer overlay')
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return False


def overlay_header_on_pdf(source_pdf_path: str, metadata: dict):
    """Return a BytesIO with the PDF header and signature footer overlaid.

    Attempts to use `pypdf` / `PyPDF2` if available. If not available and the document
    has HTML content metadata, callers should attempt to regenerate the PDF via
    `gerar_pdf_de_html` as a fallback (handled by callers).
    Returns BytesIO on success, or None if overlaying isn't possible.
    """
    return _overlay_header_footer_to_buffer(source_pdf_path, metadata)

    try:
        reader = PdfReader(source_pdf_path)
        writer = PdfWriter()

        # For each page, create a small one-page PDF with the header drawn and merge
        for pageno, page in enumerate(reader.pages, start=1):
            # Determine page size
            try:
                media = page.mediabox
                width = float(media.width)
                height = float(media.height)
            except Exception:
                # Default to A4 portrait points
                from reportlab.lib.pagesizes import A4
                width, height = A4

            # Create overlay PDF in memory with same page size
            packet = io.BytesIO()
            try:
                from reportlab.pdfgen import canvas as rl_canvas
            except Exception:
                return None

            c = rl_canvas.Canvas(packet, pagesize=(width, height))
            safe = _safe_meta_for_header(metadata or {})
            codigo = safe.get('codigo', 'S/C')
            titulo = safe.get('titulo', 'Sem título')
            revisao = safe.get('revisao', 'S/R')
            text = f"{codigo} - {titulo} - Rev{revisao} - Pg. {pageno}/{len(reader.pages)}"
            c.setFont('Helvetica', 8)
            # draw near top
            y = height - (12 * mm_to_pt_factor())
            c.drawCentredString(width / 2.0, y, text)
            c.save()

            packet.seek(0)

            # Read overlay and merge
            overlay_reader = PdfReader(packet)
            overlay_page = overlay_reader.pages[0]

            try:
                # pypdf provides merge_page, older PyPDF2 uses mergePage
                page.merge_page(overlay_page)
            except Exception:
                try:
                    page.mergePage(overlay_page)
                except Exception:
                    # If merging failed, skip overlay for this page
                    pass

            writer.add_page(page)

        out_buf = io.BytesIO()
        writer.write(out_buf)
        out_buf.seek(0)
        return out_buf
    except Exception:
        return None
