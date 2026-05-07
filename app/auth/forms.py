from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    email = StringField(
        'E-mail',
        validators=[
            DataRequired(message='Informe o e-mail.'),
            Email(message='Informe um e-mail válido.'),
        ],
    )
    senha = PasswordField(
        'Senha',
        validators=[
            DataRequired(message='Informe a senha.'),
            Length(min=6, message='A senha deve ter pelo menos 6 caracteres.'),
        ],
    )
    lembrar = BooleanField('Lembrar de mim')
    submit = SubmitField('Entrar')
