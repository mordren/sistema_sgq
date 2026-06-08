from flask import (
    render_template, redirect, url_for, flash, request, abort, session,
    send_file, current_app,
)
from flask_login import login_required, current_user
import os
import threading
import zipfile

from app.main import main
from app.models import (
    Documento,
    DocumentoExterno,
    HistoricoEvento,
    Usuario,
    Perfil,
    Alerta,
)
from app.models.documento import StatusDocumento
from app.models.exportacao_lote import ExportacaoLote
from app.extensions import db
from app.utils.decorators import bloquear_auditor
from app.utils.datetime_utils import agora_brasilia
from app.utils.historico import registrar_evento


@main.route('/')
@main.route('/dashboard')
@login_required
@bloquear_auditor
def dashboard():
    # ── Counters ───────────────────────────────────────────────────────────────
    total_vigentes = Documento.query.filter_by(
        status=StatusDocumento.VIGENTE, ativo=True
    ).count()

    total_em_revisao = Documento.query.filter_by(
        status=StatusDocumento.EM_REVISAO, ativo=True
    ).count()

    total_aguardando_aprovacao = Documento.query.filter(
        Documento.status.in_([
            StatusDocumento.AGUARDANDO_APROVACAO,
            StatusDocumento.APROVADO,
        ]),
        Documento.ativo == True,
    ).count()

    total_obsoletos = Documento.query.filter_by(
        status=StatusDocumento.OBSOLETO, ativo=True
    ).count()

    total_em_elaboracao = Documento.query.filter_by(
        status=StatusDocumento.RASCUNHO, ativo=True
    ).count()

    total_requer_treinamento = Documento.query.filter_by(
        status=StatusDocumento.VIGENTE,
        requer_treinamento=True,
        ativo=True,
    ).count()

    total_externos_aplicaveis = DocumentoExterno.query.filter_by(
        aplicavel=True
    ).count()

    # ── Recent activity (last 10 events) ──────────────────────────────────────
    eventos_recentes = (
        HistoricoEvento.query
        .order_by(HistoricoEvento.data_evento.desc())
        .limit(10)
        .all()
    )

    # ── Pending items ──────────────────────────────────────────────────────────
    pendentes = []

    docs_vigentes_sem_pdf = Documento.query.filter(
        Documento.status == StatusDocumento.VIGENTE,
        Documento.caminho_pdf_vigente.is_(None),
        Documento.content_html.is_(None),  # online-editor docs generate PDF on-the-fly
        Documento.ativo == True,
    ).count()
    if docs_vigentes_sem_pdf:
        pendentes.append({
            'tipo': 'warning',
            'icone': 'file-earmark-x',
            'mensagem': (
                f'{docs_vigentes_sem_pdf} documento(s) vigente(s) '
                'sem PDF cadastrado'
            ),
        })

    docs_sem_aprovador = Documento.query.filter(
        Documento.status == StatusDocumento.VIGENTE,
        Documento.aprovado_por_id.is_(None),
        Documento.ativo == True,
    ).count()
    if docs_sem_aprovador:
        pendentes.append({
            'tipo': 'warning',
            'icone': 'person-x',
            'mensagem': (
                f'{docs_sem_aprovador} documento(s) vigente(s) '
                'sem aprovador definido'
            ),
        })

    docs_aguardando = Documento.query.filter(
        Documento.status.in_([
            StatusDocumento.AGUARDANDO_REVISAO,
            StatusDocumento.AGUARDANDO_APROVACAO,
        ]),
        Documento.ativo == True,
    ).count()
    if docs_aguardando:
        pendentes.append({
            'tipo': 'info',
            'icone': 'hourglass-split',
            'mensagem': (
                f'{docs_aguardando} documento(s) aguardando revisão/aprovação'
            ),
        })

    # ── Documents recently updated ─────────────────────────────────────────────
    documentos_recentes = (
        Documento.query
        .filter_by(ativo=True)
        .order_by(Documento.atualizado_em.desc())
        .limit(8)
        .all()
    )

    # ── Alertas ativos (não descartados) ─────────────────────────────────────
    alertas_ativos = Alerta.alertas_ativos()

    return render_template(
        'main/dashboard.html',
        title='Dashboard',
        total_vigentes=total_vigentes,
        total_em_elaboracao=total_em_elaboracao,
        total_em_revisao=total_em_revisao,
        total_aguardando_aprovacao=total_aguardando_aprovacao,
        total_obsoletos=total_obsoletos,
        total_requer_treinamento=total_requer_treinamento,
        total_externos_aplicaveis=total_externos_aplicaveis,
        eventos_recentes=eventos_recentes,
        documentos_recentes=documentos_recentes,
        pendentes=pendentes,
        alertas_ativos=alertas_ativos,
    )


@main.route('/em-desenvolvimento')
@login_required
def em_desenvolvimento():
    return render_template('main/em_desenvolvimento.html', title='Em desenvolvimento')


@main.route('/limpar-pt-alerta', methods=['POST'])
@login_required
def limpar_pt_alerta():
    """Clear the PT alert modal flag from the session after user clicks OK."""
    session.pop('pt_alerta_modal', None)
    session.pop('pt_alerta_data', None)
    return '', 204


@main.route('/descartar-alerta/<int:alerta_id>', methods=['POST'])
@login_required
def descartar_alerta(alerta_id):
    """Dismiss a system alert (marks as discarded)."""
    alerta = Alerta.query.get_or_404(alerta_id)
    alerta.descartar(current_user.id)
    flash('Alerta descartado.', 'info')
    return redirect(url_for('main.dashboard'))


# ── User CRUD (admins only) ────────────────────────────────────────────────────

@main.route('/admin/usuarios')
@login_required
def usuarios():
    if not current_user.pode_gerenciar_usuarios():
        abort(403)
    todos = Usuario.query.order_by(Usuario.nome).all()
    return render_template('main/usuarios.html', title='Gerenciar Usuários', usuarios=todos)


@main.route('/admin/usuarios/novo', methods=['GET', 'POST'])
@login_required
def usuario_novo():
    if not current_user.pode_gerenciar_usuarios():
        abort(403)

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        perfil = request.form.get('perfil', '').strip()
        senha = request.form.get('senha', '')
        confirmar = request.form.get('confirmar_senha', '')
        ativo = bool(request.form.get('ativo'))
        revisor_padrao = bool(request.form.get('revisor_padrao'))

        erros = []
        if not nome:
            erros.append('Nome é obrigatório.')
        if not email:
            erros.append('E-mail é obrigatório.')
        if perfil not in Perfil.TODOS:
            erros.append('Perfil inválido.')
        if not senha:
            erros.append('Senha é obrigatória.')
        elif senha != confirmar:
            erros.append('As senhas não conferem.')
        elif len(senha) < 6:
            erros.append('A senha deve ter pelo menos 6 caracteres.')
        if not erros and Usuario.query.filter_by(email=email).first():
            erros.append('Já existe um usuário com este e-mail.')

        if erros:
            for e in erros:
                flash(e, 'danger')
            return render_template(
                'main/usuario_form.html',
                title='Novo Usuário',
                usuario=None,
                perfis=Perfil.TODOS,
                form_data=request.form,
            )

        # Enforce at most one default reviewer
        if revisor_padrao:
            Usuario.query.filter_by(revisor_padrao=True).update({'revisor_padrao': False})

        u = Usuario(nome=nome, email=email, perfil=perfil, ativo=ativo,
                    revisor_padrao=revisor_padrao)
        u.set_senha(senha)
        db.session.add(u)
        db.session.commit()
        flash('Usuário criado com sucesso!', 'success')
        return redirect(url_for('main.usuarios'))

    return render_template(
        'main/usuario_form.html',
        title='Novo Usuário',
        usuario=None,
        perfis=Perfil.TODOS,
        form_data={},
    )


@main.route('/admin/usuarios/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def usuario_editar(id):
    if not current_user.pode_gerenciar_usuarios():
        abort(403)

    u = Usuario.query.get_or_404(id)

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        perfil = request.form.get('perfil', '').strip()
        senha = request.form.get('senha', '')
        confirmar = request.form.get('confirmar_senha', '')
        ativo = bool(request.form.get('ativo'))
        revisor_padrao = bool(request.form.get('revisor_padrao'))

        erros = []
        if not nome:
            erros.append('Nome é obrigatório.')
        if not email:
            erros.append('E-mail é obrigatório.')
        if perfil not in Perfil.TODOS:
            erros.append('Perfil inválido.')
        if senha:
            if senha != confirmar:
                erros.append('As senhas não conferem.')
            elif len(senha) < 6:
                erros.append('A senha deve ter pelo menos 6 caracteres.')
        # Check duplicate email only if changed
        if email != u.email and not erros:
            if Usuario.query.filter_by(email=email).first():
                erros.append('Já existe um usuário com este e-mail.')

        if erros:
            for e in erros:
                flash(e, 'danger')
            return render_template(
                'main/usuario_form.html',
                title='Editar Usuário',
                usuario=u,
                perfis=Perfil.TODOS,
                form_data=request.form,
            )

        # Enforce at most one default reviewer
        if revisor_padrao and not u.revisor_padrao:
            Usuario.query.filter(Usuario.id != u.id, Usuario.revisor_padrao == True).update(
                {'revisor_padrao': False}
            )

        u.nome = nome
        u.email = email
        u.perfil = perfil
        u.ativo = ativo
        u.revisor_padrao = revisor_padrao
        if senha:
            u.set_senha(senha)
        db.session.commit()
        flash('Usuário atualizado!', 'success')
        return redirect(url_for('main.usuarios'))

    return render_template(
        'main/usuario_form.html',
        title='Editar Usuário',
        usuario=u,
        perfis=Perfil.TODOS,
        form_data={},
    )


@main.route('/admin/usuarios/<int:id>/toggle-ativo', methods=['POST'])
@login_required
def usuario_toggle_ativo(id):
    if not current_user.pode_gerenciar_usuarios():
        abort(403)

    u = Usuario.query.get_or_404(id)
    # Prevent admin from deactivating themselves
    if u.id == current_user.id:
        flash('Você não pode desativar sua própria conta.', 'warning')
        return redirect(url_for('main.usuarios'))

    u.ativo = not u.ativo
    db.session.commit()
    msg = 'Usuário ativado.' if u.ativo else 'Usuário desativado.'
    flash(msg, 'success')
    return redirect(url_for('main.usuarios'))


# ── Exportação em Lote de PDFs ────────────────────────────────────────────────

def _exportar_pdfs_background(app, export_id: int) -> None:
    """Background task: ZIP all vigente PDFs and update the export record."""

    def _run():
        with app.app_context():
            from app.extensions import db
            from app.models.exportacao_lote import ExportacaoLote
            from sqlalchemy import or_
            import tempfile

            export = db.session.get(ExportacaoLote, export_id)
            if not export:
                return

            try:
                vigentes_dir = app.config['VIGENTES_PDF_DIR']
                exportacoes_dir = app.config['EXPORTACOES_DIR']
                os.makedirs(exportacoes_dir, exist_ok=True)

                # Query ALL vigente documents: stored PDFs OR online-edited HTML
                docs = (
                    Documento.query
                    .filter(
                        Documento.ativo == True,
                        Documento.status == StatusDocumento.VIGENTE,
                        or_(
                            Documento.caminho_pdf_vigente.isnot(None),
                            Documento.content_html.isnot(None),
                        ),
                    )
                    .order_by(Documento.tipo_documento, Documento.codigo)
                    .all()
                )

                export.total_documentos = len(docs)

                stamp = agora_brasilia().strftime('%Y%m%d_%H%M%S')
                zip_filename = f'exportacao_sgq_{stamp}.zip'
                zip_path = os.path.join(exportacoes_dir, zip_filename)

                # Temp directory for generated PDFs from HTML
                tmpdir = tempfile.mkdtemp(prefix='sgq_export_')
                arquivos_temp = []

                def _add_com_doc(zf, doc, arcname):
                    """Add a document PDF to the ZIP with header/footer overlay."""
                    from app.utils.html_pdf import (
                        gerar_pdf_de_html, metadata_from_documento,
                        _overlay_header_footer_to_buffer,
                    )

                    meta = metadata_from_documento(doc)

                    # 1) Stored PDF — copy + overlay
                    if doc.caminho_pdf_vigente:
                        pdf_path = os.path.join(vigentes_dir, doc.caminho_pdf_vigente)
                        if os.path.isfile(pdf_path):
                            buf = _overlay_header_footer_to_buffer(pdf_path, meta)
                            if buf:
                                zf.writestr(arcname, buf.getvalue())
                            else:
                                # Fallback: use original without overlay
                                zf.write(pdf_path, arcname)
                            return True

                    # 2) Online-edited — generate PDF + overlay
                    if doc.content_html:
                        tmp_pdf = os.path.join(tmpdir, f'{doc.id}.pdf')
                        ok = gerar_pdf_de_html(doc.content_html, meta, tmp_pdf)
                        if ok and os.path.isfile(tmp_pdf):
                            # Apply overlay with headers/footers
                            buf = _overlay_header_footer_to_buffer(tmp_pdf, meta)
                            if buf:
                                zf.writestr(arcname, buf.getvalue())
                            else:
                                zf.write(tmp_pdf, arcname)
                            arquivos_temp.append(tmp_pdf)
                            return True

                    return False

                try:
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for doc in docs:
                            arcname = (
                                f'{doc.tipo_documento}/'
                                f'{doc.codigo}_Rev{doc.revisao_atual:02d}.pdf'
                            )
                            _add_com_doc(zf, doc, arcname)
                finally:
                    # Clean up temp files
                    for f in arquivos_temp:
                        try:
                            os.remove(f)
                        except Exception:
                            pass
                    try:
                        os.rmdir(tmpdir)
                    except Exception:
                        pass

                export.tamanho_bytes = os.path.getsize(zip_path)
                export.arquivo_zip = zip_filename
                export.status = 'concluido'
                export.concluido_em = agora_brasilia()
                registrar_evento(
                    usuario_id=export.criado_por_id,
                    acao='Exportação de PDFs em lote concluída',
                    descricao=f'{export.total_documentos} PDFs — {zip_filename}',
                )
                db.session.commit()

            except Exception as exc:
                export.status = 'falhou'
                export.erro = str(exc)[:500]
                export.concluido_em = agora_brasilia()
                registrar_evento(
                    usuario_id=export.criado_por_id,
                    acao='Exportação de PDFs em lote concluída',
                    descricao=f'Falhou: {str(exc)[:100]}',
                )
                db.session.commit()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


@main.route('/admin/exportar-pdfs')
@login_required
def exportar_pdfs():
    """Page to trigger and download bulk PDF exports."""
    if not current_user.pode_gerenciar_usuarios():
        abort(403)

    exportacoes = (
        ExportacaoLote.query
        .order_by(ExportacaoLote.criado_em.desc())
        .limit(50)
        .all()
    )

    return render_template(
        'main/exportar_pdfs.html',
        title='Exportar PDFs em Lote',
        exportacoes=exportacoes,
    )


@main.route('/admin/exportar-pdfs/iniciar', methods=['POST'])
@login_required
def iniciar_exportacao_pdfs():
    """Start a new background PDF export."""
    if not current_user.pode_gerenciar_usuarios():
        abort(403)

    export = ExportacaoLote(
        status='processando',
        criado_por_id=current_user.id,
    )
    db.session.add(export)
    registrar_evento(
        usuario_id=current_user.id,
        acao='Exportação de PDFs em lote iniciada',
        descricao='Gerando ZIP com todos os PDFs vigentes...',
    )
    db.session.commit()

    _exportar_pdfs_background(current_app._get_current_object(), export.id)

    flash('Exportação iniciada em segundo plano. Esta página será atualizada automaticamente quando terminar.', 'info')
    return redirect(url_for('main.exportar_pdfs'))


@main.route('/admin/exportar-pdfs/download/<int:id>')
@login_required
def download_exportacao_pdfs(id):
    """Download a completed ZIP export."""
    if not current_user.pode_gerenciar_usuarios():
        abort(403)

    export = ExportacaoLote.query.get_or_404(id)

    if export.status != 'concluido' or not export.arquivo_zip:
        flash('Exportação ainda não está pronta para download.', 'warning')
        return redirect(url_for('main.exportar_pdfs'))

    exportacoes_dir = current_app.config['EXPORTACOES_DIR']
    zip_path = os.path.join(exportacoes_dir, export.arquivo_zip)

    if not os.path.isfile(zip_path):
        flash('Arquivo não encontrado no servidor.', 'danger')
        return redirect(url_for('main.exportar_pdfs'))

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=export.arquivo_zip,
        mimetype='application/zip',
    )


@main.route('/admin/exportar-pdfs/cancelar/<int:id>', methods=['POST'])
@login_required
def cancelar_exportacao_pdfs(id):
    """Cancel a processing export job."""
    if not current_user.pode_gerenciar_usuarios():
        abort(403)

    export = ExportacaoLote.query.get_or_404(id)

    if export.status != 'processando':
        flash('Apenas exportações em processamento podem ser canceladas.', 'warning')
        return redirect(url_for('main.exportar_pdfs'))

    export.status = 'falhou'
    export.erro = 'Cancelado pelo usuário.'
    export.concluido_em = agora_brasilia()
    db.session.commit()
    flash('Exportação cancelada.', 'info')
    return redirect(url_for('main.exportar_pdfs'))
