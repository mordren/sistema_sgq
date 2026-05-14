"""
Custom access-control decorators.

Usage:
    @perfil_requerido(Perfil.ADMINISTRADOR, Perfil.RESPONSAVEL_QUALIDADE)
    def minha_view():
        ...
"""

from functools import wraps
from flask import abort
from flask_login import current_user


def perfil_requerido(*perfis):
    """Restrict a view to users whose perfil is in *perfis*."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                return redirect(url_for('auth.login'))
            if current_user.perfil not in perfis:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_ou_qualidade(f):
    """Shortcut: allow only Administrador or Responsável da Qualidade."""
    from app.models.usuario import Perfil
    return perfil_requerido(Perfil.ADMINISTRADOR, Perfil.RESPONSAVEL_QUALIDADE)(f)


def pode_aprovar(f):
    """Shortcut: allow only Aprovador or Administrador."""
    from app.models.usuario import Perfil
    return perfil_requerido(Perfil.APROVADOR, Perfil.ADMINISTRADOR)(f)


def somente_admin(f):
    """Shortcut: allow only Administrador."""
    from app.models.usuario import Perfil
    return perfil_requerido(Perfil.ADMINISTRADOR)(f)


def bloquear_auditor(f):
    """Block Auditor Externo / Técnico from accessing a view (returns 403)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            from flask import redirect, url_for
            return redirect(url_for('auth.login'))
        from app.models.usuario import Perfil
        if current_user.perfil == Perfil.AUDITOR_EXTERNO:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
