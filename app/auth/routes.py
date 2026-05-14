from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.auth import auth
from app.auth.forms import LoginForm
from app.models import Usuario
from app.models.usuario import Perfil


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.perfil == Perfil.AUDITOR_EXTERNO:
            return redirect(url_for('documentos.lista_mestra'))
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(
            email=form.email.data.strip().lower()
        ).first()

        if usuario and usuario.ativo and usuario.check_senha(form.senha.data):
            login_user(usuario, remember=form.lembrar.data)

            # Prevent open redirect: only allow relative URLs
            next_page = request.args.get('next')
            if next_page and (
                not next_page.startswith('/')
                or next_page.startswith('//')
            ):
                next_page = None

            flash(f'Bem-vindo(a), {usuario.nome}!', 'success')
            # Redirect auditors to their allowed landing page
            if usuario.perfil == Perfil.AUDITOR_EXTERNO:
                return redirect(url_for('documentos.lista_mestra'))
            return redirect(next_page or url_for('main.dashboard'))

        elif usuario and not usuario.ativo:
            flash('Sua conta está inativa. Contate o administrador.', 'danger')
        else:
            flash('E-mail ou senha inválidos.', 'danger')

    return render_template('auth/login.html', form=form, title='Login')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sessão encerrada com sucesso.', 'info')
    return redirect(url_for('auth.login'))
