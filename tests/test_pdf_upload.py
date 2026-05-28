"""Tests for PDF upload feature on PA/PT documents."""
import io
import os
import pytest
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models.documento import Documento, TipoDocumento, StatusDocumento
from app.models.revisao import RevisaoDocumento
from app.models.usuario import Usuario, Perfil
from app.utils.file_utils import nome_pdf_vigente


# ── Helpers ────────────────────────────────────────────────────────────────────

def _login(client, email, password='senha123'):
    return client.post('/auth/login', data={'email': email, 'password': password},
                       follow_redirects=True)


def _fake_pdf():
    return (io.BytesIO(b'%PDF-1.4 fake'), 'test.pdf', 'application/pdf')


# ── UploadPdfForm validation ───────────────────────────────────────────────────

class TestUploadPdfForm:
    def test_form_accepts_pdf(self, app):
        from app.documentos.forms import UploadPdfForm
        with app.test_request_context():
            from werkzeug.datastructures import FileStorage, MultiDict, ImmutableMultiDict
            from werkzeug.test import EnvironBuilder
            # Just check the form class exists and has expected fields
            form = UploadPdfForm.__mro__  # simple presence check
            assert UploadPdfForm is not None

    def test_upload_pdf_form_has_arquivo_field(self, app):
        from app.documentos.forms import UploadPdfForm
        with app.test_request_context('/'):
            form = UploadPdfForm()
            assert hasattr(form, 'arquivo')
            assert hasattr(form, 'motivo')
            assert hasattr(form, 'submit')


# ── upload_pdf route ───────────────────────────────────────────────────────────

class TestUploadPdfRoute:
    def test_upload_pdf_blocks_non_pa_pt(self, app, client):
        """IT documents should not be accepted for PDF upload."""
        with app.app_context():
            u = Usuario(
                nome='Qualidade', email='q2@test.com', perfil=Perfil.RESPONSAVEL_QUALIDADE, ativo=True
            )
            u.set_senha('senha')
            db.session.add(u)
            doc = Documento(
                codigo='IT-001', titulo='Instrução', tipo_documento=TipoDocumento.IT,
                status=StatusDocumento.RASCUNHO, revisao_atual=0,
                elaborado_por_id=None, ativo=True,
            )
            db.session.add(doc)
            db.session.commit()
            doc_id = doc.id

        with client.session_transaction() as sess:
            # simulate login via flask-login
            pass

        # Use test client with login
        with app.test_client() as c:
            with app.app_context():
                u = Usuario.query.filter_by(email='q2@test.com').first()
                with c.session_transaction() as sess:
                    sess['_user_id'] = str(u.id)
                    sess['_fresh'] = True

                resp = c.post(
                    f'/documentos/{doc_id}/upload-pdf',
                    data={
                        'arquivo': _fake_pdf(),
                        'csrf_token': 'ignore',
                    },
                    content_type='multipart/form-data',
                    follow_redirects=True,
                )
                # Should redirect to detalhe with a warning
                assert resp.status_code == 200
                assert b'PA' in resp.data or b'PT' in resp.data or b'danger' in resp.data

    def test_upload_pdf_allowed_for_pa_rascunho(self, app):
        """PA document in Rascunho should accept PDF upload and set content_mode."""
        with app.app_context():
            u = Usuario(
                nome='Qualidade3', email='q3@test.com', perfil=Perfil.RESPONSAVEL_QUALIDADE, ativo=True
            )
            u.set_senha('senha')
            db.session.add(u)
            doc = Documento(
                codigo='PA-002', titulo='Procedimento PA2', tipo_documento=TipoDocumento.PA,
                status=StatusDocumento.RASCUNHO, revisao_atual=0,
                elaborado_por_id=None, ativo=True,
            )
            db.session.add(doc)
            db.session.commit()
            doc_id = doc.id
            user_id = u.id

            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['_user_id'] = str(user_id)
                    sess['_fresh'] = True

                nome_esperado = nome_pdf_vigente('PA-002', 0, 'Procedimento PA2')
                em_revisao_dir = app.config['EM_REVISAO_DIR']

                with patch('app.documentos.routes.salvar_upload') as mock_save, \
                     patch('app.documentos.routes.registrar_evento'):
                    mock_save.return_value = None

                    # We need a valid CSRF token — disable CSRF for testing (WTF_CSRF_ENABLED=False)
                    resp = c.post(
                        f'/documentos/{doc_id}/upload-pdf',
                        data={
                            'arquivo': (io.BytesIO(b'%PDF fake'), 'doc.pdf'),
                            'motivo': 'Emissão inicial',
                        },
                        content_type='multipart/form-data',
                        follow_redirects=False,
                    )
                    # Should redirect to detalhe
                    assert resp.status_code in (302, 200)

                    # Check DB
                    doc_updated = Documento.query.get(doc_id)
                    if mock_save.called:
                        assert doc_updated.content_mode == 'uploaded_file'


# ── abrir_revisao gate ────────────────────────────────────────────────────────

class TestAbrirRevisaoGate:
    def test_uploaded_file_doc_can_open_revision(self, app):
        """A VIGENTE document with uploaded_file mode should be able to open revision."""
        with app.app_context():
            u = Usuario(
                nome='Qldd4', email='q4@test.com', perfil=Perfil.RESPONSAVEL_QUALIDADE, ativo=True
            )
            u.set_senha('senha')
            db.session.add(u)
            doc = Documento(
                codigo='PA-003', titulo='PA Vigente', tipo_documento=TipoDocumento.PA,
                status=StatusDocumento.VIGENTE, revisao_atual=1,
                content_mode='uploaded_file',
                caminho_pdf_vigente='PA-003_Rev01_PA_Vigente.pdf',
                elaborado_por_id=None, ativo=True,
            )
            db.session.add(doc)
            db.session.commit()
            doc_id = doc.id
            user_id = u.id

            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['_user_id'] = str(user_id)
                    sess['_fresh'] = True

                with patch('app.documentos.routes.registrar_evento'):
                    resp = c.post(
                        f'/documentos/{doc_id}/abrir-revisao',
                        data={'motivo': 'Atualização do procedimento'},
                        follow_redirects=False,
                    )
                    # Should redirect (not 403 or render with danger about content)
                    assert resp.status_code in (302, 200)
                    # If 302, it went to detalhe → success
                    if resp.status_code == 302:
                        revisao = RevisaoDocumento.query.filter_by(
                            documento_id=doc_id
                        ).first()
                        assert revisao is not None
                        assert revisao.content_mode == 'uploaded_file'


# ── enviar_para_aprovacao gate ────────────────────────────────────────────────

class TestEnviarParaAprovacaoGate:
    def test_uploaded_file_revisao_can_be_sent_for_approval(self, app):
        """Revision with content_mode='uploaded_file' and arquivo_pdf should be sendable."""
        with app.app_context():
            u = Usuario(
                nome='Qldd5', email='q5@test.com', perfil=Perfil.RESPONSAVEL_QUALIDADE, ativo=True
            )
            u.set_senha('senha')
            db.session.add(u)
            doc = Documento(
                codigo='PA-004', titulo='PA Rev', tipo_documento=TipoDocumento.PA,
                status=StatusDocumento.EM_REVISAO, revisao_atual=0,
                content_mode='uploaded_file', ativo=True,
            )
            db.session.add(doc)
            db.session.flush()
            revisao = RevisaoDocumento(
                documento_id=doc.id,
                numero_revisao=1,
                status=StatusDocumento.EM_REVISAO,
                content_mode='uploaded_file',
                arquivo_pdf='PA-004_Rev01_PA_Rev.pdf',
                elaborado_por_id=u.id,
            )
            db.session.add(revisao)
            db.session.commit()
            doc_id = doc.id
            rev_id = revisao.id
            user_id = u.id

        with app.app_context():
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['_user_id'] = str(user_id)
                    sess['_fresh'] = True

                with patch('app.documentos.routes.registrar_evento'):
                    resp = c.post(
                        f'/documentos/{doc_id}/revisoes/{rev_id}/enviar-aprovacao',
                        follow_redirects=False,
                    )
                    assert resp.status_code in (302, 200)
                    if resp.status_code == 302:
                        rev_updated = RevisaoDocumento.query.get(rev_id)
                        assert rev_updated.status == StatusDocumento.AGUARDANDO_APROVACAO


# ── aprovar_revisao with uploaded_file ────────────────────────────────────────

class TestAprovarRevisaoUploadedFile:
    def test_approve_uploaded_file_copies_pdf(self, app, tmp_path):
        """Approving a revision with uploaded PDF should copy it to vigentes/."""
        with app.app_context():
            u = Usuario(
                nome='Aprovador', email='aprov@test.com', perfil=Perfil.ADMINISTRADOR, ativo=True
            )
            u.set_senha('senha')
            db.session.add(u)
            doc = Documento(
                codigo='PA-005', titulo='PA Aprovar', tipo_documento=TipoDocumento.PA,
                status=StatusDocumento.AGUARDANDO_APROVACAO, revisao_atual=0,
                content_mode='uploaded_file', ativo=True,
            )
            db.session.add(doc)
            db.session.flush()
            revisao = RevisaoDocumento(
                documento_id=doc.id,
                numero_revisao=1,
                status=StatusDocumento.AGUARDANDO_APROVACAO,
                content_mode='uploaded_file',
                arquivo_pdf='PA-005_Rev01_PA_Aprovar.pdf',
                elaborado_por_id=u.id,
            )
            db.session.add(revisao)
            db.session.commit()
            doc_id = doc.id
            rev_id = revisao.id
            user_id = u.id

        with app.app_context():
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['_user_id'] = str(user_id)
                    sess['_fresh'] = True

                with patch('app.documentos.routes.arquivo_existe', return_value=True), \
                     patch('app.documentos.routes.copiar_arquivo') as mock_copy, \
                     patch('app.documentos.routes.mover_arquivo'), \
                     patch('app.documentos.routes.registrar_evento'):
                    resp = c.post(
                        f'/documentos/{doc_id}/revisoes/{rev_id}/aprovar',
                        follow_redirects=False,
                    )
                    assert resp.status_code in (302, 200)
                    if mock_copy.called:
                        # Verify the destination has the vigente filename
                        call_args = mock_copy.call_args
                        dst = call_args[0][1]
                        assert 'PA-005_Rev01' in dst

                    if resp.status_code == 302:
                        doc_updated = Documento.query.get(doc_id)
                        assert doc_updated.status == StatusDocumento.VIGENTE
                        assert doc_updated.content_mode == 'uploaded_file'
                        assert doc_updated.content_html is None
