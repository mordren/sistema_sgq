from datetime import datetime

from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.atividades import atividades
from app.extensions import db
from app.models.consulta_remota import ConsultaRemota
from app.utils.datetime_utils import agora_brasilia
from app.utils.decorators import bloquear_auditor

_MESES = [
    (1, 'JAN'), (2, 'FEV'), (3, 'MAR'), (4, 'ABR'),
    (5, 'MAI'), (6, 'JUN'), (7, 'JUL'), (8, 'AGO'),
    (9, 'SET'), (10, 'OUT'), (11, 'NOV'), (12, 'DEZ'),
]

_FONTES = [
    {
        'nome': 'INMETRO – Legislação',
        'url': (
            'http://www.inmetro.gov.br/legislacao/resultado_pesquisa.asp'
            '?num_ato=N%FAmero&ano_assinatura=Ano&palavra_chave=Palavra-Chave'
            '&imageField.x=41&imageField.y=6&nom_classe=&seq_classe=&sig_classe='
        ),
        'icon': 'bi-journal-text',
        'cor': 'primary',
    },
    {
        'nome': 'SENATRAN – Resoluções CONTRAN',
        'url': (
            'https://www.gov.br/transportes/pt-br/assuntos/transito/'
            'conteudo-Senatran/resolucoes-contran'
        ),
        'icon': 'bi-card-list',
        'cor': 'success',
    },
    {
        'nome': 'SENATRAN – Portarias SENATRAN',
        'url': (
            'https://www.gov.br/transportes/pt-br/assuntos/transito/'
            'conteudo-Senatran/portarias-senatran'
        ),
        'icon': 'bi-file-earmark-ruled',
        'cor': 'info',
    },
    {
        'nome': 'INMETRO – Organismos Acreditados / OIA',
        'url': (
            'http://www.inmetro.gov.br/credenciamento/organismos/'
            'doc_organismos.asp?tOrganismo=OIA'
        ),
        'icon': 'bi-patch-check',
        'cor': 'warning',
    },
]


def _tabela_ano(ano: int) -> dict:
    """Return {(mes, quinzena): ConsultaRemota|None} for all 24 slots of the year."""
    registros = ConsultaRemota.query.filter_by(ano=ano).all()
    mapa = {(r.mes, r.quinzena): r for r in registros}
    return mapa


@atividades.route('/consultas-remotas', methods=['GET', 'POST'])
@login_required
@bloquear_auditor
def consultas_remotas():
    ano_atual = agora_brasilia().year
    try:
        ano = int(request.args.get('ano', ano_atual))
    except ValueError:
        ano = ano_atual

    pode_editar = current_user.pode_editar_documentos()

    if request.method == 'POST':
        if not pode_editar:
            abort(403)

        marcados = request.form.getlist('quinzena')  # e.g. ['1-1', '1-2', '3-1']
        agora = agora_brasilia()
        salvos = 0

        for item in marcados:
            try:
                mes_str, qz_str = item.split('-')
                mes = int(mes_str)
                quinzena = int(qz_str)
            except (ValueError, AttributeError):
                continue
            if mes not in range(1, 13) or quinzena not in (1, 2):
                continue

            registro = ConsultaRemota.query.filter_by(
                ano=ano, mes=mes, quinzena=quinzena
            ).first()

            if registro is None:
                registro = ConsultaRemota(
                    ano=ano, mes=mes, quinzena=quinzena,
                    verificado=True,
                    verificado_em=agora,
                    verificado_por_id=current_user.id,
                )
                db.session.add(registro)
            else:
                registro.verificado = True
                registro.verificado_em = agora
                registro.verificado_por_id = current_user.id
                registro.atualizado_em = agora
            salvos += 1

        db.session.commit()
        flash('Consultas remotas salvas com sucesso.', 'success')
        return redirect(url_for('atividades.consultas_remotas', ano=ano))

    mapa = _tabela_ano(ano)
    anos_disponiveis = _anos_disponiveis()

    return render_template(
        'atividades/consultas_remotas.html',
        title='Consultas Remotas',
        meses=_MESES,
        fontes=_FONTES,
        mapa=mapa,
        ano=ano,
        ano_atual=ano_atual,
        anos_disponiveis=anos_disponiveis,
        pode_editar=pode_editar,
    )


def _anos_disponiveis() -> list:
    """Years with existing records plus current and next year."""
    from sqlalchemy import distinct
    anos_db = [
        r[0] for r in db.session.query(distinct(ConsultaRemota.ano)).all()
    ]
    ano_atual = agora_brasilia().year
    todos = sorted(set(anos_db) | {ano_atual - 1, ano_atual, ano_atual + 1})
    return todos


# ── Controle de Versão de Software ────────────────────────────────────────────

@atividades.route('/controle-versao-software', methods=['GET', 'POST'])
@login_required
@bloquear_auditor
def controle_versao_software():
    from app.models.controle_versao_software import ControleVersaoSoftware

    pode_editar = current_user.pode_editar_documentos()

    if request.method == 'POST':
        if not pode_editar:
            abort(403)

        equipamento = (request.form.get('equipamento', '') or '').strip()
        software = (request.form.get('software', '') or '').strip()
        versao = (request.form.get('versao', '') or '').strip()

        if not equipamento:
            flash('O campo Equipamento é obrigatório.', 'danger')
            return redirect(url_for('atividades.controle_versao_software'))
        if not software:
            flash('O campo Software é obrigatório.', 'danger')
            return redirect(url_for('atividades.controle_versao_software'))
        if not versao:
            flash('O campo Versão é obrigatório.', 'danger')
            return redirect(url_for('atividades.controle_versao_software'))

        registro = ControleVersaoSoftware(
            equipamento=equipamento,
            software=software,
            versao=versao,
        )
        db.session.add(registro)
        db.session.commit()
        flash('Registro adicionado com sucesso!', 'success')
        return redirect(url_for('atividades.controle_versao_software'))

    registros = (
        ControleVersaoSoftware.query
        .order_by(
            ControleVersaoSoftware.equipamento,
            ControleVersaoSoftware.software,
        )
        .all()
    )

    return render_template(
        'atividades/controle_versao_software.html',
        title='Controle de Versão de Software',
        registros=registros,
        pode_editar=pode_editar,
    )


@atividades.route('/controle-versao-software/editar/<int:id>', methods=['POST'])
@login_required
@bloquear_auditor
def editar_versao_software(id):
    from app.models.controle_versao_software import ControleVersaoSoftware

    if not current_user.pode_editar_documentos():
        abort(403)

    registro = ControleVersaoSoftware.query.get_or_404(id)

    equipamento = (request.form.get('equipamento', '') or '').strip()
    software = (request.form.get('software', '') or '').strip()
    versao = (request.form.get('versao', '') or '').strip()

    if not equipamento:
        flash('O campo Equipamento é obrigatório.', 'danger')
        return redirect(url_for('atividades.controle_versao_software'))
    if not software:
        flash('O campo Software é obrigatório.', 'danger')
        return redirect(url_for('atividades.controle_versao_software'))
    if not versao:
        flash('O campo Versão é obrigatório.', 'danger')
        return redirect(url_for('atividades.controle_versao_software'))

    registro.equipamento = equipamento
    registro.software = software
    registro.versao = versao
    db.session.commit()
    flash('Registro atualizado com sucesso!', 'success')
    return redirect(url_for('atividades.controle_versao_software'))


@atividades.route('/controle-versao-software/excluir/<int:id>', methods=['POST'])
@login_required
@bloquear_auditor
def excluir_versao_software(id):
    from app.models.controle_versao_software import ControleVersaoSoftware

    if current_user.perfil != 'Administrador':
        abort(403)

    registro = ControleVersaoSoftware.query.get_or_404(id)
    nome = f'{registro.equipamento} – {registro.software}'
    db.session.delete(registro)
    db.session.commit()
    flash(f'Registro "{nome}" excluído permanentemente.', 'success')
    return redirect(url_for('atividades.controle_versao_software'))
