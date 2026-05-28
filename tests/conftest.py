"""Pytest fixtures for SGQ tests."""
import io
import pytest
from app import create_app
from app.extensions import db as _db
from app.models.documento import Documento, TipoDocumento, StatusDocumento
from app.models.revisao import RevisaoDocumento
from app.models.usuario import Usuario, Perfil


@pytest.fixture(scope='session')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture()
def db(app):
    with app.app_context():
        yield _db
        _db.session.rollback()


@pytest.fixture()
def client(app):
    return app.test_client()


def _create_usuario(db, nome='Teste', perfil=Perfil.RESPONSAVEL_QUALIDADE):
    u = Usuario(
        nome=nome,
        email=f'{nome.lower().replace(" ","_")}@test.com',
        perfil=perfil,
        ativo=True,
    )
    u.set_senha('senha123')
    db.session.add(u)
    db.session.flush()
    return u


def _create_doc_pa(db, usuario_id, status=StatusDocumento.RASCUNHO):
    doc = Documento(
        codigo='PA-001',
        titulo='Procedimento Teste',
        tipo_documento=TipoDocumento.PA,
        status=status,
        revisao_atual=0,
        elaborado_por_id=usuario_id,
        ativo=True,
    )
    db.session.add(doc)
    db.session.flush()
    return doc


@pytest.fixture()
def usuario(db):
    with db.session.begin_nested():
        u = _create_usuario(db)
    return u


@pytest.fixture()
def doc_pa_rascunho(db, usuario):
    with db.session.begin_nested():
        doc = _create_doc_pa(db, usuario.id, StatusDocumento.RASCUNHO)
    return doc


@pytest.fixture()
def doc_pa_vigente(db, usuario):
    with db.session.begin_nested():
        doc = _create_doc_pa(db, usuario.id, StatusDocumento.VIGENTE)
        doc.content_mode = 'uploaded_file'
        doc.caminho_pdf_vigente = 'PA-001_Rev00_Procedimento_Teste.pdf'
        doc.revisao_atual = 0
    return doc
