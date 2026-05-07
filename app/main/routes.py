from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.main import main
from app.models import (
    Documento,
    DocumentoExterno,
    HistoricoEvento,
    Usuario,
    Perfil,
)
from app.models.documento import StatusDocumento
from app.extensions import db


@main.route('/')
@main.route('/dashboard')
@login_required
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
    )


@main.route('/em-desenvolvimento')
@login_required
def em_desenvolvimento():
    return render_template('main/em_desenvolvimento.html', title='Em desenvolvimento')


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

        u = Usuario(nome=nome, email=email, perfil=perfil, ativo=ativo)
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

        u.nome = nome
        u.email = email
        u.perfil = perfil
        u.ativo = ativo
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
