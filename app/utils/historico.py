"""
Helper to stage a HistoricoEvento for the current db.session.
Call db.session.commit() after all changes in the same transaction.
"""

from app.extensions import db
from app.models.historico import HistoricoEvento


def registrar_evento(
    documento_id: int,
    usuario_id: int,
    acao: str,
    descricao: str | None = None,
) -> None:
    """Stage a HistoricoEvento. Must call db.session.commit() afterwards."""
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
