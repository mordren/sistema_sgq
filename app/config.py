import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-fallback-key-change-before-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 52428800))  # 50 MB

    # ── Storage paths ──────────────────────────────────────────────────────────
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    STORAGE_DIR = os.path.join(BASE_DIR, 'storage')

    VIGENTES_PDF_DIR = os.path.join(STORAGE_DIR, 'documentos', 'vigentes_pdf')
    EDITAVEIS_DOCX_DIR = os.path.join(STORAGE_DIR, 'documentos', 'editaveis_docx')
    EM_REVISAO_DIR = os.path.join(STORAGE_DIR, 'documentos', 'em_revisao')
    OBSOLETOS_DIR = os.path.join(STORAGE_DIR, 'documentos', 'obsoletos')
    EXTERNOS_DIR = os.path.join(STORAGE_DIR, 'documentos', 'externos')
    EXPORTACOES_DIR = os.path.join(STORAGE_DIR, 'exportacoes')
    BACKUPS_DIR = os.path.join(STORAGE_DIR, 'backups')

    # ── Allowed upload extensions ──────────────────────────────────────────────
    ALLOWED_DOCX_EXTENSIONS = {'docx'}
    ALLOWED_PDF_EXTENSIONS = {'pdf'}
    ALLOWED_DOCUMENT_EXTENSIONS = {'docx', 'pdf'}


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'sqlite:///sgq_cascavel.db'
    )
    # More verbose SQL logging for development
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

    # Enforce HTTPS cookies in production
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
