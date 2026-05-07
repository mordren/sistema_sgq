import os
from flask import Flask, render_template
from app.extensions import db, login_manager, csrf, migrate
from app.config import config


def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ── Initialise extensions ──────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    # ── Login manager settings ─────────────────────────────────────────────────
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'

    # ── Ensure storage directories exist ──────────────────────────────────────
    _create_storage_dirs(app)

    # ── Register blueprints ────────────────────────────────────────────────────
    from app.auth import auth as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.main import main as main_bp
    app.register_blueprint(main_bp)

    from app.documentos import documentos as documentos_bp
    app.register_blueprint(documentos_bp, url_prefix='/documentos')

    # ── Register error handlers ────────────────────────────────────────────────
    _register_error_handlers(app)

    # ── Import models so SQLAlchemy registers them ─────────────────────────────
    with app.app_context():
        from app import models  # noqa: F401
        _migrate_lightweight_schema()

    return app


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_storage_dirs(app: Flask) -> None:
    dirs = [
        app.config['VIGENTES_PDF_DIR'],
        app.config['EDITAVEIS_DOCX_DIR'],
        app.config['EM_REVISAO_DIR'],
        app.config['OBSOLETOS_DIR'],
        app.config['EXTERNOS_DIR'],
        os.path.join(app.config['EXPORTACOES_DIR'], 'lista_mestra'),
        os.path.join(app.config['EXPORTACOES_DIR'], 'matriz_correlacao'),
        os.path.join(app.config['EXPORTACOES_DIR'], 'relatorios'),
        app.config['BACKUPS_DIR'],
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def _migrate_lightweight_schema() -> None:
    """SQLite-safe additions used by newer screens before Flask-Migrate runs."""
    try:
        rows = db.session.execute(db.text('PRAGMA table_info(documentos)')).fetchall()
        existing = {row[1] for row in rows}
        if 'matriz_correlacao_json' not in existing:
            db.session.execute(
                db.text('ALTER TABLE documentos ADD COLUMN matriz_correlacao_json TEXT')
            )
            db.session.commit()
    except Exception:
        db.session.rollback()


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return render_template('errors/500.html'), 500
