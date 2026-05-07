from flask import Blueprint

documentos = Blueprint('documentos', __name__)

from app.documentos import routes  # noqa: F401, E402
