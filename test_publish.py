from app import create_app
from app.extensions import db
from app.models import Documento, Usuario
from app.models.documento import StatusDocumento

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False

with app.app_context():
    # create a test document
    doc = Documento(
        codigo='TEST-PUB',
        titulo='Documento Teste Publicar',
        tipo_documento='PT',
        revisao_atual=0,
        status=StatusDocumento.RASCUNHO,
        content_html='<p>conteudo de teste</p>',
        content_mode='online_editor',
    )
    db.session.add(doc)
    db.session.commit()
    doc_id = doc.id
    print('Created doc id', doc_id)

    # find an approver (prefer Perfil.APROVADOR if available)
    approver = Usuario.query.filter_by(ativo=True).filter(Usuario.perfil=='Aprovador').first()
    if not approver:
        approver = Usuario.query.filter_by(ativo=True).first()
    print('Using approver', approver.id, approver.nome)

    # use test client to simulate logged-in approver
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(approver.id)
        sess['_fresh'] = True

    # POST publish
    resp = client.post(f'/documentos/{doc_id}/publicar-vigente', data={
        'motivo': 'Teste de publicacao via cliente de testes',
        'aprovado_por_id': approver.id,
    }, follow_redirects=True)
    print('POST status', resp.status_code)
    data = resp.get_data(as_text=True)
    if 'publicado como Vigente' in data or 'publicado com sucesso' in data.lower():
        print('Publish seems successful (flash present)')
    else:
        print('Publish flash not found; response snippet:')
        print(data[:1000])

    # reload doc
    d2 = Documento.query.get(doc_id)
    print('Doc status after POST:', d2.status, 'caminho_pdf_vigente:', d2.caminho_pdf_vigente)
