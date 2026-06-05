from flask import Blueprint

atividades = Blueprint('atividades', __name__)

from app.atividades import routes  # noqa: F401, E402
