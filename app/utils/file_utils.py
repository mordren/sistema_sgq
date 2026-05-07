"""
File system utilities for SGQ document storage.

Naming convention:
  Current PDF  : CODIGO_RevXX_TITULO.pdf
  Editable DOCX: CODIGO_RevXX_TITULO.docx
  Obsolete PDF : CODIGO_RevXX_TITULO_OBSOLETO.pdf
"""

import os
import re
import shutil
from pathlib import Path
from flask import current_app


# ── Allowed extensions ─────────────────────────────────────────────────────────

ALLOWED_DOCX = {'docx'}
ALLOWED_PDF = {'pdf'}
ALLOWED_UPLOAD = {'docx', 'pdf'}


def extensao_permitida(filename: str, allowed: set) -> bool:
    """Return True if *filename* has an allowed extension."""
    ext = Path(filename).suffix.lstrip('.').lower()
    return ext in allowed


def extensao_segura(filename: str) -> str:
    """Return the lowercase extension without the dot."""
    return Path(filename).suffix.lstrip('.').lower()


# ── File naming ────────────────────────────────────────────────────────────────

def _sanitizar_titulo(titulo: str, max_len: int = 50) -> str:
    """Convert a document title to a filesystem-safe segment."""
    safe = re.sub(r'[^\w\s-]', '', titulo)       # remove non-word chars
    safe = re.sub(r'[\s]+', '_', safe.strip())    # spaces → underscores
    return safe[:max_len]


def nome_pdf_vigente(codigo: str, revisao: int, titulo: str) -> str:
    return f"{codigo}_Rev{revisao:02d}_{_sanitizar_titulo(titulo)}.pdf"


def nome_docx_editavel(codigo: str, revisao: int, titulo: str) -> str:
    return f"{codigo}_Rev{revisao:02d}_{_sanitizar_titulo(titulo)}.docx"


def nome_pdf_obsoleto(codigo: str, revisao: int, titulo: str) -> str:
    return f"{codigo}_Rev{revisao:02d}_{_sanitizar_titulo(titulo)}_OBSOLETO.pdf"


# ── Path resolution ────────────────────────────────────────────────────────────

def caminho_vigente_pdf(nome_arquivo: str) -> str:
    return os.path.join(current_app.config['VIGENTES_PDF_DIR'], nome_arquivo)


def caminho_editavel_docx(nome_arquivo: str) -> str:
    return os.path.join(current_app.config['EDITAVEIS_DOCX_DIR'], nome_arquivo)


def caminho_em_revisao(nome_arquivo: str) -> str:
    return os.path.join(current_app.config['EM_REVISAO_DIR'], nome_arquivo)


def caminho_obsoleto(nome_arquivo: str) -> str:
    return os.path.join(current_app.config['OBSOLETOS_DIR'], nome_arquivo)


def caminho_externo(nome_arquivo: str) -> str:
    return os.path.join(current_app.config['EXTERNOS_DIR'], nome_arquivo)


# ── Path traversal prevention ──────────────────────────────────────────────────

def caminho_seguro(diretorio_base: str, nome_arquivo: str) -> str:
    """
    Build an absolute path and verify it stays inside *diretorio_base*.
    Raises ValueError if a path traversal attempt is detected.
    """
    base = os.path.realpath(diretorio_base)
    destino = os.path.realpath(os.path.join(base, os.path.basename(nome_arquivo)))
    if not destino.startswith(base + os.sep) and destino != base:
        raise ValueError(f"Path traversal attempt detected: {nome_arquivo}")
    return destino


# ── File operations ────────────────────────────────────────────────────────────

def salvar_upload(file_obj, diretorio: str, nome_arquivo: str) -> str:
    """
    Save a Werkzeug FileStorage object to *diretorio* as *nome_arquivo*.
    Returns the full destination path.
    """
    destino = caminho_seguro(diretorio, nome_arquivo)
    os.makedirs(diretorio, exist_ok=True)
    file_obj.save(destino)
    return destino


def mover_arquivo(origem: str, destino: str) -> None:
    """Move *origem* to *destino*, creating parent directories if needed."""
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.move(origem, destino)


def copiar_arquivo(origem: str, destino: str) -> None:
    """Copy *origem* to *destino*, creating parent directories if needed."""
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copy2(origem, destino)


def arquivo_existe(caminho: str) -> bool:
    return bool(caminho) and os.path.isfile(caminho)
