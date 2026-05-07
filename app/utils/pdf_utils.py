"""
PDF generation utility using LibreOffice headless.

Usage:
    from app.utils.pdf_utils import converter_docx_para_pdf

    pdf_path = converter_docx_para_pdf(caminho_docx, pasta_saida)
    if pdf_path is None:
        # conversion failed – check logs
        ...
"""

import glob
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

# ── LibreOffice executable candidates ─────────────────────────────────────────

_CANDIDATOS_WINDOWS = [
    r'C:\Program Files\LibreOffice\program\soffice.exe',
    r'C:\Program Files (x86)\LibreOffice\program\soffice.exe',
    r'C:\Program Files\LibreOffice 7\program\soffice.exe',
    r'C:\Program Files\LibreOffice 24\program\soffice.exe',
    r'C:\Program Files\LibreOffice 25\program\soffice.exe',
]

_CANDIDATOS_UNIX = [
    '/usr/bin/libreoffice',
    '/usr/bin/soffice',
    '/usr/local/bin/libreoffice',
    '/usr/local/bin/soffice',
    '/opt/libreoffice/program/soffice',
]

_CANDIDATOS_GLOB = [
    '/opt/libreoffice*/program/soffice',
    r'C:\Program Files\LibreOffice*\program\soffice.exe',
]

_PATH_COMMANDS = ['libreoffice', 'soffice']


def _localizar_libreoffice() -> str | None:
    """Return the path to the LibreOffice soffice executable, or None."""
    # 1. Absolute paths
    for path in _CANDIDATOS_WINDOWS + _CANDIDATOS_UNIX:
        if os.path.isfile(path):
            return path
    # 2. Glob patterns
    for pattern in _CANDIDATOS_GLOB:
        matches = glob.glob(pattern)
        if matches:
            return sorted(matches)[-1]  # pick the latest version
    # 3. PATH
    for cmd in _PATH_COMMANDS:
        try:
            result = subprocess.run(
                [cmd, '--version'],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def converter_docx_para_pdf(caminho_docx: str, pasta_saida: str) -> str | None:
    """
    Convert *caminho_docx* to PDF and save in *pasta_saida*.

    Returns the full path to the generated PDF file, or None on failure.

    Requires LibreOffice to be installed on the server.
    Install: https://www.libreoffice.org/download/download-libreoffice/
    """
    if not os.path.isfile(caminho_docx):
        logger.error('DOCX not found for conversion: %s', caminho_docx)
        return None

    os.makedirs(pasta_saida, exist_ok=True)

    executavel = _localizar_libreoffice()
    if not executavel:
        logger.error(
            'LibreOffice not found. Install LibreOffice to enable PDF generation. '
            'Download: https://www.libreoffice.org/'
        )
        return None

    try:
        logger.info('Converting %s → PDF using %s', caminho_docx, executavel)
        result = subprocess.run(
            [
                executavel,
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', pasta_saida,
                caminho_docx,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error(
                'LibreOffice conversion failed (rc=%d): %s',
                result.returncode,
                result.stderr[:500],
            )
            return None

        # LibreOffice names the output <basename>.pdf
        nome_base = os.path.splitext(os.path.basename(caminho_docx))[0]
        pdf_path = os.path.join(pasta_saida, nome_base + '.pdf')

        if os.path.isfile(pdf_path):
            logger.info('PDF generated: %s', pdf_path)
            return pdf_path

        logger.error('PDF not found after conversion: %s', pdf_path)
        return None

    except subprocess.TimeoutExpired:
        logger.error('LibreOffice conversion timed out for %s', caminho_docx)
        return None
    except Exception as exc:
        logger.error('Unexpected error during PDF conversion: %s', exc)
        return None
