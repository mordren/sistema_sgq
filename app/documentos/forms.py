from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, SelectField, BooleanField, TextAreaField,
    IntegerField, SubmitField,
)
from wtforms.validators import DataRequired, Length, Optional, NumberRange

from app.models.documento import TipoDocumento


class NovoDocumentoForm(FlaskForm):
    codigo = StringField(
        'Código',
        validators=[
            DataRequired(message='Informe o código.'),
            Length(max=50, message='Máximo 50 caracteres.'),
        ],
    )
    titulo = StringField(
        'Título',
        validators=[
            DataRequired(message='Informe o título.'),
            Length(max=200, message='Máximo 200 caracteres.'),
        ],
    )
    tipo_documento = SelectField(
        'Tipo de documento',
        choices=[],
        validators=[DataRequired(message='Selecione o tipo.')],
    )
    revisao_inicial = IntegerField(
        'Revisão inicial',
        default=0,
        validators=[NumberRange(min=0, max=99, message='Revisão entre 0 e 99.')],
    )

    # ── Responsible users ──────────────────────────────────────────────────────
    elaborado_por_id = SelectField(
        'Elaborado por', coerce=int, choices=[], validators=[Optional()]
    )
    revisado_por_id = SelectField(
        'Revisado por', coerce=int, choices=[], validators=[Optional()]
    )
    aprovado_por_id = SelectField(
        'Aprovado por', coerce=int, choices=[], validators=[Optional()]
    )

    # ── Metadata ───────────────────────────────────────────────────────────────
    requisito_relacionado = StringField(
        'Requisito relacionado',
        validators=[Optional(), Length(max=200)],
    )
    distribuicao_tecnica = BooleanField('Distribuição técnica')
    distribuicao_administrativa = BooleanField('Distribuição administrativa')
    requer_treinamento = BooleanField('Requer treinamento')
    observacao = TextAreaField('Observação', validators=[Optional()])

    # ── File uploads (optional at creation) ───────────────────────────────────
    arquivo_docx = FileField(
        'Arquivo DOCX editável',
        validators=[
            Optional(),
            FileAllowed(['docx'], 'Apenas arquivos .docx são permitidos.'),
        ],
    )
    arquivo_pdf = FileField(
        'PDF vigente (importação)',
        validators=[
            Optional(),
            FileAllowed(['pdf'], 'Apenas arquivos .pdf são permitidos.'),
        ],
    )

    submit = SubmitField('Cadastrar documento')


class EditarDocumentoForm(FlaskForm):
    titulo = StringField(
        'Título',
        validators=[
            DataRequired(message='Informe o título.'),
            Length(max=200, message='Máximo 200 caracteres.'),
        ],
    )
    tipo_documento = SelectField(
        'Tipo de documento', choices=[], validators=[DataRequired()]
    )
    elaborado_por_id = SelectField(
        'Elaborado por', coerce=int, choices=[], validators=[Optional()]
    )
    revisado_por_id = SelectField(
        'Revisado por', coerce=int, choices=[], validators=[Optional()]
    )
    aprovado_por_id = SelectField(
        'Aprovado por', coerce=int, choices=[], validators=[Optional()]
    )
    requisito_relacionado = StringField(
        'Requisito relacionado', validators=[Optional(), Length(max=200)]
    )
    distribuicao_tecnica = BooleanField('Distribuição técnica')
    distribuicao_administrativa = BooleanField('Distribuição administrativa')
    requer_treinamento = BooleanField('Requer treinamento')
    observacao = TextAreaField('Observação', validators=[Optional()])

    submit = SubmitField('Salvar alterações')


class UploadDocxForm(FlaskForm):
    arquivo_docx = FileField(
        'Arquivo DOCX',
        validators=[
            DataRequired(message='Selecione um arquivo .docx.'),
            FileAllowed(['docx'], 'Apenas arquivos .docx são permitidos.'),
        ],
    )
    submit = SubmitField('Enviar DOCX')


class UploadPdfForm(FlaskForm):
    arquivo_pdf = FileField(
        'Arquivo PDF',
        validators=[
            DataRequired(message='Selecione um arquivo .pdf.'),
            FileAllowed(['pdf'], 'Apenas arquivos .pdf são permitidos.'),
        ],
    )
    submit = SubmitField('Enviar PDF')


class PublicarVigenteForm(FlaskForm):
    motivo = TextAreaField(
        'Motivo / Descrição da publicação',
        validators=[
            DataRequired(message='Informe o motivo da publicação.'),
            Length(max=1000),
        ],
    )
    aprovado_por_id = SelectField(
        'Aprovado por',
        coerce=int,
        choices=[],
        validators=[DataRequired(message='Selecione o aprovador.')],
    )
    submit = SubmitField('Publicar como Vigente')


class AbrirRevisaoForm(FlaskForm):
    motivo = TextAreaField(
        'Motivo da revisão',
        validators=[
            DataRequired(message='Informe o motivo da revisão.'),
            Length(max=500),
        ],
    )
    submit = SubmitField('Abrir Revisão')


class EnviarAprovacaoForm(FlaskForm):
    """Move revisão diretamente para Aguardando aprovação."""
    submit = SubmitField('Enviar para Aprovação')


class AprovarRevisaoForm(FlaskForm):
    elaborado_por_id = SelectField(
        'Elaborado por',
        coerce=int,
        choices=[],
        validators=[DataRequired(message='Selecione quem elaborou.')],
    )
    revisado_por_id = SelectField(
        'Revisado por',
        coerce=int,
        choices=[],
        validators=[DataRequired(message='Selecione quem revisou.')],
    )
    aprovado_por_id = SelectField(
        'Aprovado por',
        coerce=int,
        choices=[],
        validators=[DataRequired(message='Selecione o aprovador.')],
    )
    submit = SubmitField('Aprovar Revisão')


class ReprovarRevisaoForm(FlaskForm):
    motivo = TextAreaField(
        'Motivo da reprovação',
        validators=[
            DataRequired(message='Informe o motivo da reprovação.'),
            Length(max=500),
        ],
    )
    submit = SubmitField('Reprovar')


class PublicarRevisaoForm(FlaskForm):
    """Publish a fully-approved revision as the new Vigente document."""
    motivo = TextAreaField(
        'Descrição das alterações',
        validators=[
            DataRequired(message='Descreva as alterações desta revisão.'),
            Length(max=1000),
        ],
    )
    gerar_pdf = BooleanField('Gerar PDF automaticamente (requer LibreOffice)', default=True)
    submit = SubmitField('Publicar Revisão')


class EditorConteudoForm(FlaskForm):
    """Online rich-text editor form."""
    content_html = TextAreaField(
        'Conteúdo',
        validators=[DataRequired(message='O conteúdo não pode estar vazio.')],
    )
    descricao_alteracao = TextAreaField(
        'Descrição da Modificação',
        validators=[Optional(), Length(max=500)],
        description='Ex: Emissão inicial do procedimento.',
    )
    item_alterado = StringField(
        'Item(s) Alterado(s)',
        validators=[Optional(), Length(max=200)],
        description='Ex: 3.2, 4.1 — ou "N/A" para emissão inicial.',
    )
    submit = SubmitField('Salvar Conteúdo')


class ListaMestraConfigForm(FlaskForm):
    """Form for setting the Lista Mestra document header metadata."""
    titulo = StringField(
        'Título',
        validators=[DataRequired(message='Informe o título.'), Length(max=200)],
        default='Lista Mestra de Documentos',
    )
    codigo = StringField(
        'Código do documento',
        validators=[DataRequired(message='Informe o código.'), Length(max=50)],
        default='LM-01',
    )
    revisao_num = IntegerField(
        'Número da revisão',
        default=0,
        validators=[NumberRange(min=0, max=99, message='Revisão entre 0 e 99.')],
    )
    elaborado_por_id = SelectField(
        'Elaborado por', coerce=int, choices=[], validators=[Optional()]
    )
    revisado_por_id = SelectField(
        'Revisado por', coerce=int, choices=[], validators=[Optional()]
    )
    aprovado_por_id = SelectField(
        'Aprovado por', coerce=int, choices=[], validators=[Optional()]
    )
    submit = SubmitField('Salvar Configuração')


class DocumentoExternoForm(FlaskForm):
    """Form for registering or editing an external document."""

    codigo = StringField(
        'Identificação do Documento',
        validators=[Optional(), Length(max=50)],
        description='Ex: Portaria 149/2022, NBR 14040:2023',
    )
    titulo = StringField(
        'Título',
        validators=[DataRequired(message='Informe o título.'), Length(max=200)],
    )
    orgao_emissor = StringField(
        'Órgão Emissor / Categoria',
        validators=[Optional(), Length(max=100)],
        description='Ex: INMETRO, SENATRAN, ABNT',
    )
    revisao = StringField(
        'Revisão',
        validators=[Optional(), Length(max=20)],
        description='Ex: 2024, Rev01 — ou deixe em branco para N/A',
    )
    arquivo = FileField(
        'Arquivo',
        validators=[
            Optional(),
            FileAllowed(
                ['pdf', 'docx', 'doc', 'xlsx', 'xls'],
                'Apenas PDF, DOCX, DOC, XLSX ou XLS.',
            ),
        ],
    )
    distribuicao_tecnica = BooleanField('Distribuição na Área Técnica')
    distribuicao_administrativa = BooleanField('Distribuição na Área Administrativa')
    observacao = TextAreaField('Observação', validators=[Optional()])
    submit = SubmitField('Salvar')

