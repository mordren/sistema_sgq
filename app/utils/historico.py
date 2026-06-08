"""
Helper to stage a HistoricoEvento for the current db.session.
Call db.session.commit() after all changes in the same transaction.
"""

from app.extensions import db
from app.models.historico import HistoricoEvento


def registrar_evento(
    documento_id: int | None = None,
    usuario_id: int | None = None,
    acao: str = '',
    descricao: str | None = None,
) -> None:
    """Stage a HistoricoEvento. Must call db.session.commit() afterwards.

    documento_id can be None for events not tied to a specific document
    (e.g. external documents, software version control, PDF exports).
    """
    try:
        from flask import request
        ip = request.environ.get('REMOTE_ADDR', 'unknown')
    except RuntimeError:
        ip = 'sistema'

    evento = HistoricoEvento(
        documento_id=documento_id,
        usuario_id=usuario_id,
        acao=acao,
        descricao=descricao,
        ip_usuario=ip,
    )
    db.session.add(evento)
