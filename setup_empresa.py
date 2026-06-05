"""
setup_empresa.py – Script de configuração inicial do SistemaSGQ para nova empresa.

Execute este script APÓS clonar o projeto para uma nova empresa.
Ele irá:
  1. Configurar o nome da empresa (substitui "CSV Cascavel" nos templates)
  2. Configurar os usuários iniciais
  3. Copiar o logo da empresa
  4. Inicializar o banco de dados

Uso:
    python setup_empresa.py

Requisitos:
    - Python 3.8+
    - Dependências instaladas (pip install -r requirements.txt)
    - Arquivo .env configurado (copie .env.example para .env)
"""

import os
import sys
import shutil
import re
from pathlib import Path

# ── Cores para o terminal (Windows) ──────────────────────────────────────────
def _enable_windows_colors():
    """Habilita cores ANSI no Windows."""
    if sys.platform == 'win32':
        os.system('')  # Habilita ANSI no Windows 10+

_enable_windows_colors()

class Cores:
    VERDE = '\033[92m'
    AMARELO = '\033[93m'
    AZUL = '\033[94m'
    VERMELHO = '\033[91m'
    CIANO = '\033[96m'
    NEGRITO = '\033[1m'
    RESET = '\033[0m'

def cor(texto, c):
    return f"{c}{texto}{Cores.RESET}"

def titulo(texto):
    largura = 60
    print()
    print(cor('═' * largura, Cores.CIANO))
    print(cor(f'  {texto}', Cores.NEGRITO + Cores.CIANO))
    print(cor('═' * largura, Cores.CIANO))
    print()

def sucesso(texto):
    print(f"  {cor('[OK]', Cores.VERDE)} {texto}")

def aviso(texto):
    print(f"  {cor('[!]', Cores.AMARELO)} {texto}")

def erro(texto):
    print(f"  {cor('[ERRO]', Cores.VERMELHO)} {texto}")

def info(texto):
    print(f"  {cor('[i]', Cores.AZUL)} {texto}")


# ── Caminhos do projeto ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
TEMPLATES_DIR = BASE_DIR / 'app' / 'templates'
STATIC_DIR = BASE_DIR / 'app' / 'static'
LOGO_DESTINO = STATIC_DIR / 'images' / 'logo.png'
STORAGE_DIR = BASE_DIR / 'storage'
INSTANCE_DIR = BASE_DIR / 'instance'

# Nome antigo que será substituído
NOME_ANTIGO = 'CSV Cascavel'
DOMINIO_ANTIGO = 'csvcascavel.com.br'

# Perfis disponíveis (espelha app/models/usuario.py)
PERFIS = [
    'Administrador',
    'Responsável da Qualidade',
    'Responsável Técnico',
    'Aprovador',
    'Colaborador Consulta',
    'Auditor Externo / Técnico',
]


# ── Passo 1: Configurar nome da empresa ──────────────────────────────────────
def configurar_empresa():
    titulo('PASSO 1 – Nome da Empresa')

    print(f"  O nome atual do sistema é: {cor(NOME_ANTIGO, Cores.AMARELO)}")
    print(f"  Ele será substituído em todos os templates e telas do sistema.")
    print()

    nome_empresa = ''
    while not nome_empresa.strip():
        nome_empresa = input(f"  {cor('Nome da empresa:', Cores.NEGRITO)} ").strip()
        if not nome_empresa:
            erro("O nome não pode ser vazio.")

    print()
    sucesso(f"Nome da empresa definido: {cor(nome_empresa, Cores.VERDE)}")
    return nome_empresa


# ── Passo 2: Configurar domínio de e-mail ────────────────────────────────────
def configurar_dominio():
    titulo('PASSO 2 – Domínio de E-mail')

    print(f"  O domínio atual dos e-mails é: {cor(DOMINIO_ANTIGO, Cores.AMARELO)}")
    print(f"  Exemplo: admin@{DOMINIO_ANTIGO}")
    print()

    dominio = ''
    while not dominio.strip():
        dominio = input(f"  {cor('Domínio de e-mail (ex: empresa.com.br):', Cores.NEGRITO)} ").strip().lower()
        if not dominio:
            erro("O domínio não pode ser vazio.")
        elif '.' not in dominio:
            erro("Domínio inválido. Use o formato: empresa.com.br")
            dominio = ''

    print()
    sucesso(f"Domínio definido: {cor(dominio, Cores.VERDE)}")
    return dominio


# ── Passo 3: Configurar usuários ─────────────────────────────────────────────
def configurar_usuarios(dominio):
    titulo('PASSO 3 – Usuários Iniciais')

    print(f"  Configure os usuários que serão criados no sistema.")
    print(f"  O domínio de e-mail será: {cor('@' + dominio, Cores.AZUL)}")
    print()
    print(f"  Perfis disponíveis:")
    for i, perfil in enumerate(PERFIS, 1):
        print(f"    {cor(str(i), Cores.CIANO)}. {perfil}")
    print()

    usuarios = []
    contador = 1

    while True:
        print(f"  ── Usuário {contador} ──")

        # Nome
        nome = ''
        while not nome.strip():
            nome = input(f"    {cor('Nome completo:', Cores.NEGRITO)} ").strip()
            if not nome:
                erro("O nome não pode ser vazio.")

        # E-mail
        email = ''
        while not email.strip():
            email_input = input(f"    {cor('E-mail (sem @domínio):', Cores.NEGRITO)} ").strip().lower()
            if not email_input:
                erro("O e-mail não pode ser vazio.")
                continue
            if '@' in email_input:
                email = email_input
            else:
                email = f"{email_input}@{dominio}"
            # Validação simples
            if '@' not in email or '.' not in email.split('@')[1]:
                erro(f"E-mail inválido: {email}")
                email = ''

        # Perfil
        print(f"    Perfis:")
        for i, perfil in enumerate(PERFIS, 1):
            print(f"      {cor(str(i), Cores.CIANO)}. {perfil}")

        perfil_idx = 0
        while perfil_idx < 1 or perfil_idx > len(PERFIS):
            try:
                perfil_input = input(f"    {cor('Perfil (número):', Cores.NEGRITO)} ").strip()
                perfil_idx = int(perfil_input)
                if perfil_idx < 1 or perfil_idx > len(PERFIS):
                    erro(f"Escolha um número entre 1 e {len(PERFIS)}.")
            except ValueError:
                erro("Digite um número válido.")

        perfil = PERFIS[perfil_idx - 1]

        # Senha
        senha = ''
        while not senha:
            senha = input(f"    {cor('Senha inicial:', Cores.NEGRITO)} ").strip()
            if not senha:
                erro("A senha não pode ser vazia.")
            elif len(senha) < 6:
                erro("A senha deve ter pelo menos 6 caracteres.")
                senha = ''

        usuarios.append({
            'nome': nome,
            'email': email,
            'senha': senha,
            'perfil': perfil,
        })

        sucesso(f"Usuário adicionado: {nome} ({email}) – {perfil}")
        print()

        # Perguntar se quer adicionar mais
        mais = input(f"  {cor('Adicionar outro usuário? (s/n):', Cores.NEGRITO)} ").strip().lower()
        if mais not in ('s', 'sim', 'y', 'yes'):
            break

        contador += 1
        print()

    print()
    sucesso(f"Total de usuários configurados: {cor(str(len(usuarios)), Cores.VERDE)}")
    return usuarios


# ── Passo 4: Configurar logo ─────────────────────────────────────────────────
def configurar_logo():
    titulo('PASSO 4 – Logo da Empresa')

    print(f"  O logo será exibido nos documentos e na interface do sistema.")
    print(f"  Formato recomendado: PNG com transparência")
    print(f"  Tamanho recomendado: 200 x 60 px (ou proporção similar)")
    print(f"  Destino: {cor(str(LOGO_DESTINO), Cores.AZUL)}")
    print()

    while True:
        caminho = input(f"  {cor('Caminho do arquivo de logo (ou Enter para pular):', Cores.NEGRITO)} ").strip()

        if not caminho:
            aviso("Logo não configurado. O sistema exibirá o nome da empresa no lugar.")
            return None

        caminho = caminho.strip('"').strip("'")
        caminho_path = Path(caminho)

        if not caminho_path.is_absolute():
            caminho_path = Path.cwd() / caminho_path

        if not caminho_path.exists():
            erro(f"Arquivo não encontrado: {caminho_path}")
            continue

        if not caminho_path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'):
            erro("Formato não suportado. Use PNG, JPG, GIF, WebP ou SVG.")
            continue

        sucesso(f"Logo encontrado: {caminho_path}")
        return caminho_path


# ── Passo 5: Resumo e confirmação ────────────────────────────────────────────
def confirmar_configuracao(nome_empresa, dominio, usuarios, logo_path):
    titulo('RESUMO DA CONFIGURAÇÃO')

    print(f"  {cor('Empresa:', Cores.NEGRITO)} {nome_empresa}")
    print(f"  {cor('Domínio:', Cores.NEGRITO)} {dominio}")
    print(f"  {cor('Logo:', Cores.NEGRITO)} {logo_path if logo_path else '(não configurado)'}")
    print()
    print(f"  {cor('Usuários a serem criados:', Cores.NEGRITO)}")
    for u in usuarios:
        print(f"    • {u['nome']} ({u['email']}) – {u['perfil']}")
    print()
    print(f"  {cor('Substituições que serão feitas:', Cores.NEGRITO)}")
    print(f"    • \"{NOME_ANTIGO}\" → \"{nome_empresa}\" (em todos os templates)")
    print(f"    • \"{DOMINIO_ANTIGO}\" → \"{dominio}\" (nos templates)")
    print(f"    • Logo copiado para {LOGO_DESTINO}")
    print(f"    • Banco de dados inicializado com {len(usuarios)} usuário(s)")
    print()

    confirmar = input(f"  {cor('Confirmar e executar? (s/n):', Cores.NEGRITO)} ").strip().lower()
    return confirmar in ('s', 'sim', 'y', 'yes')


# ── Execução: Substituir nome da empresa nos templates ───────────────────────
def substituir_nome_empresa(nome_empresa, dominio):
    titulo('Substituindo nome da empresa nos templates...')

    arquivos_modificados = []
    total_substituicoes = 0

    # Percorrer todos os arquivos HTML nos templates
    for arquivo_html in TEMPLATES_DIR.rglob('*.html'):
        conteudo_original = arquivo_html.read_text(encoding='utf-8')
        conteudo_novo = conteudo_original

        # Substituir nome da empresa
        if NOME_ANTIGO in conteudo_novo:
            conteudo_novo = conteudo_novo.replace(NOME_ANTIGO, nome_empresa)

        # Substituir domínio de e-mail
        if DOMINIO_ANTIGO in conteudo_novo:
            conteudo_novo = conteudo_novo.replace(DOMINIO_ANTIGO, dominio)

        if conteudo_novo != conteudo_original:
            arquivo_html.write_text(conteudo_novo, encoding='utf-8')
            # Contar substituições
            subs_nome = conteudo_original.count(NOME_ANTIGO)
            subs_dom = conteudo_original.count(DOMINIO_ANTIGO)
            total = subs_nome + subs_dom
            total_substituicoes += total
            arquivos_modificados.append((arquivo_html, subs_nome, subs_dom))
            sucesso(f"{arquivo_html.relative_to(BASE_DIR)} ({total} substituições)")

    # Também substituir no LEIA-ME.txt do logo
    leia_me = STATIC_DIR / 'images' / 'LEIA-ME.txt'
    if leia_me.exists():
        conteudo = leia_me.read_text(encoding='utf-8')
        if NOME_ANTIGO in conteudo:
            conteudo = conteudo.replace(NOME_ANTIGO, nome_empresa)
            leia_me.write_text(conteudo, encoding='utf-8')
            sucesso(f"{leia_me.relative_to(BASE_DIR)} (atualizado)")

    print()
    sucesso(f"Total: {len(arquivos_modificados)} arquivo(s) modificado(s), {total_substituicoes} substituição(ões)")
    return arquivos_modificados


# ── Execução: Copiar logo ────────────────────────────────────────────────────
def copiar_logo(logo_path):
    titulo('Copiando logo da empresa...')

    if logo_path is None:
        aviso("Nenhum logo configurado. Pulando.")
        return False

    try:
        # Garantir que o diretório existe
        LOGO_DESTINO.parent.mkdir(parents=True, exist_ok=True)

        # Copiar o arquivo
        shutil.copy2(str(logo_path), str(LOGO_DESTINO))
        sucesso(f"Logo copiado para: {LOGO_DESTINO}")
        return True
    except Exception as e:
        erro(f"Falha ao copiar logo: {e}")
        return False


# ── Execução: Inicializar banco de dados ─────────────────────────────────────
def inicializar_banco(usuarios_config):
    titulo('Inicializando banco de dados...')

    try:
        # Importar o Flask app e extensões
        from dotenv import load_dotenv
        load_dotenv()

        from app import create_app
        from app.extensions import db
        from app.models import Usuario
        from app.models.usuario import Perfil

        app = create_app(os.environ.get('FLASK_ENV', 'development'))

        with app.app_context():
            # Criar todas as tabelas
            db.create_all()
            sucesso("Tabelas criadas (ou já existentes).")

            # Migrations leves (mesma lógica do init_db.py)
            _migrate_documentos_externos(db)
            _migrate_usuarios(db)

            # Mapear perfis do input para as constantes do modelo
            perfil_map = {
                'Administrador': Perfil.ADMINISTRADOR,
                'Responsável da Qualidade': Perfil.RESPONSAVEL_QUALIDADE,
                'Responsável Técnico': Perfil.RESPONSAVEL_TECNICO,
                'Aprovador': Perfil.APROVADOR,
                'Colaborador Consulta': Perfil.COLABORADOR_CONSULTA,
                'Auditor Externo / Técnico': Perfil.AUDITOR_EXTERNO,
            }

            # Criar usuários
            for dados in usuarios_config:
                existente = Usuario.query.filter_by(email=dados['email']).first()
                if existente:
                    aviso(f"Usuário já existe: {dados['email']}")
                    continue

                perfil_const = perfil_map.get(dados['perfil'], Perfil.COLABORADOR_CONSULTA)

                usuario = Usuario(
                    nome=dados['nome'],
                    email=dados['email'],
                    perfil=perfil_const,
                    ativo=True,
                )
                usuario.set_senha(dados['senha'])
                db.session.add(usuario)
                sucesso(f"{dados['nome']} ({dados['email']}) – {dados['perfil']}")

            db.session.commit()
            print()
            sucesso("Banco de dados inicializado com sucesso!")

            # Exibir credenciais
            print()
            print(cor('  ┌─────────────────────────────────────────────────────────────┐', Cores.AMARELO))
            print(cor('  │  CREDENCIAIS DOS USUÁRIOS CRIADOS                          │', Cores.AMARELO))
            print(cor('  │  IMPORTANTE: Altere as senhas após o primeiro acesso!      │', Cores.AMARELO))
            print(cor('  └─────────────────────────────────────────────────────────────┘', Cores.AMARELO))
            print()
            for dados in usuarios_config:
                print(f"    {cor(dados['email'], Cores.CIANO):50s} / {dados['senha']}")
            print()

        return True

    except Exception as e:
        erro(f"Falha ao inicializar banco de dados: {e}")
        print()
        print(f"  Detalhes: {e}")
        print()
        print(f"  Certifique-se de que:")
        print(f"    1. As dependências estão instaladas: {cor('pip install -r requirements.txt', Cores.CIANO)}")
        print(f"    2. O arquivo .env existe (copie .env.example para .env)")
        print(f"    3. Não há outro processo usando o banco de dados")
        return False


def _migrate_documentos_externos(db):
    """Add new columns to documentos_externos if they don't already exist."""
    from sqlalchemy import text
    new_cols = [
        ('distribuicao_tecnica', 'BOOLEAN NOT NULL DEFAULT 0'),
        ('distribuicao_administrativa', 'BOOLEAN NOT NULL DEFAULT 0'),
        ('enviado_por_id', 'INTEGER'),
        ('data_envio', 'DATETIME'),
    ]
    engine = db.engine
    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(documentos_externos)"))
        }
        for col_name, col_def in new_cols:
            if col_name not in existing:
                try:
                    conn.execute(
                        text(f'ALTER TABLE documentos_externos ADD COLUMN {col_name} {col_def}')
                    )
                    conn.commit()
                    info(f"documentos_externos.{col_name} adicionada")
                except Exception:
                    pass


def _migrate_usuarios(db):
    """Add new columns to usuarios if they don't already exist."""
    from sqlalchemy import text
    new_cols = [
        ('revisor_padrao', 'BOOLEAN NOT NULL DEFAULT 0'),
    ]
    engine = db.engine
    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(usuarios)"))
        }
        for col_name, col_def in new_cols:
            if col_name not in existing:
                try:
                    conn.execute(
                        text(f'ALTER TABLE usuarios ADD COLUMN {col_name} {col_def}')
                    )
                    conn.commit()
                    info(f"usuarios.{col_name} adicionada")
                except Exception:
                    pass


# ── Menu principal ───────────────────────────────────────────────────────────
def main():
    print()
    print(cor('╔══════════════════════════════════════════════════════════════╗', Cores.CIANO))
    print(cor('║                                                              ║', Cores.CIANO))
    print(cor('║     CONFIGURAÇÃO INICIAL DO SISTEMASGQ                      ║', Cores.NEGRITO + Cores.CIANO))
    print(cor('║     Setup para nova empresa                                 ║', Cores.CIANO))
    print(cor('║                                                              ║', Cores.CIANO))
    print(cor('╚══════════════════════════════════════════════════════════════╝', Cores.CIANO))
    print()
    info("Este script irá configurar o sistema para uma nova empresa.")
    info("Os templates serão modificados com o nome da nova empresa.")
    info("O banco de dados será inicializado com os usuários configurados.")
    print()

    # Verificar pré-requisitos
    if not (BASE_DIR / 'requirements.txt').exists():
        erro("Arquivo requirements.txt não encontrado. Execute este script na raiz do projeto.")
        sys.exit(1)

    if not (BASE_DIR / '.env').exists() and not (BASE_DIR / '.env.example').exists():
        aviso("Arquivo .env não encontrado. Copie .env.example para .env antes de continuar.")

    input(f"  Pressione {cor('Enter', Cores.NEGRITO)} para continuar...")

    # Passo 1: Nome da empresa
    nome_empresa = configurar_empresa()

    # Passo 2: Domínio de e-mail
    dominio = configurar_dominio()

    # Passo 3: Usuários
    usuarios = configurar_usuarios(dominio)

    # Passo 4: Logo
    logo_path = configurar_logo()

    # Passo 5: Confirmação
    if not confirmar_configuracao(nome_empresa, dominio, usuarios, logo_path):
        aviso("Configuração cancelada pelo usuário.")
        sys.exit(0)

    # ── Executar configurações ───────────────────────────────────────────
    print()
    print(cor('╔══════════════════════════════════════════════════════════════╗', Cores.VERDE))
    print(cor('║  EXECUTANDO CONFIGURAÇÃO...                                 ║', Cores.NEGRITO + Cores.VERDE))
    print(cor('╚══════════════════════════════════════════════════════════════╝', Cores.VERDE))

    # 1. Substituir nome da empresa nos templates
    substituir_nome_empresa(nome_empresa, dominio)

    # 2. Copiar logo
    copiar_logo(logo_path)

    # 3. Inicializar banco de dados
    sucesso_db = inicializar_banco(usuarios)

    # ── Resultado final ──────────────────────────────────────────────────
    print()
    if sucesso_db:
        print(cor('╔══════════════════════════════════════════════════════════════╗', Cores.VERDE))
        print(cor('║  CONFIGURAÇÃO CONCLUÍDA COM SUCESSO!                        ║', Cores.NEGRITO + Cores.VERDE))
        print(cor('╚══════════════════════════════════════════════════════════════╝', Cores.VERDE))
        print()
        print(f"  Para iniciar o sistema, execute:")
        print(f"    {cor('python run.py', Cores.CIANO)}")
        print()
    else:
        print(cor('╔══════════════════════════════════════════════════════════════╗', Cores.AMARELO))
        print(cor('║  CONFIGURAÇÃO PARCIAL                                       ║', Cores.NEGRITO + Cores.AMARELO))
        print(cor('╚══════════════════════════════════════════════════════════════╝', Cores.AMARELO))
        print()
        print(f"  Os templates foram atualizados, mas o banco de dados não foi inicializado.")
        print(f"  Verifique os erros acima e tente novamente.")
        print(f"  Você também pode inicializar o banco manualmente com:")
        print(f"    {cor('python init_db.py', Cores.CIANO)}")
        print()


if __name__ == '__main__':
    main()