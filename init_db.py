"""
init_db.py – Database initialisation script for SGQ CSV Cascavel.

Run once to create all tables and seed the default users:

    python init_db.py

Default credentials (CHANGE IMMEDIATELY after first login):
    admin@csvcascavel.com.br     /  Admin@SGQ2024
    qualidade@csvcascavel.com.br /  Qualidade@SGQ2024
    aprovador@csvcascavel.com.br /  Aprovador@SGQ2024
"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db
from app.models import Usuario
from app.models.usuario import Perfil


def init_database() -> None:
    app = create_app(os.environ.get('FLASK_ENV', 'development'))

    with app.app_context():
        # Create all tables
        db.create_all()
        print("[OK] Tabelas criadas (ou já existentes).")

        # Add new columns to existing tables when needed
        _migrate_documentos_externos()

        _seed_usuarios()

        db.session.commit()
        print("[OK] Banco de dados inicializado com sucesso.")


def _migrate_documentos_externos() -> None:
    """Add new columns to documentos_externos if they don't already exist (SQLite-safe)."""
    new_cols = [
        ('distribuicao_tecnica',    'BOOLEAN NOT NULL DEFAULT 0'),
        ('distribuicao_administrativa', 'BOOLEAN NOT NULL DEFAULT 0'),
        ('enviado_por_id',          'INTEGER'),
        ('data_envio',              'DATETIME'),
    ]
    engine = db.engine
    with engine.connect() as conn:
        # Get existing columns
        existing = {
            row[1]
            for row in conn.execute(
                db.text("PRAGMA table_info(documentos_externos)")
            )
        }
        for col_name, col_def in new_cols:
            if col_name not in existing:
                try:
                    conn.execute(
                        db.text(
                            f'ALTER TABLE documentos_externos ADD COLUMN {col_name} {col_def}'
                        )
                    )
                    print(f'  [ADD]  documentos_externos.{col_name}')
                except Exception as exc:
                    print(f'  [SKIP] documentos_externos.{col_name}: {exc}')
            else:
                print(f'  [OK]   documentos_externos.{col_name} já existe')


def _seed_usuarios() -> None:
    usuarios_iniciais = [
        {
            'nome': 'Administrador',
            'email': 'admin@csvcascavel.com.br',
            'senha': 'Admin@SGQ2024',
            'perfil': Perfil.ADMINISTRADOR,
        },
        {
            'nome': 'Responsável da Qualidade',
            'email': 'qualidade@csvcascavel.com.br',
            'senha': 'Qualidade@SGQ2024',
            'perfil': Perfil.RESPONSAVEL_QUALIDADE,
        },
        {
            'nome': 'Aprovador Padrão',
            'email': 'aprovador@csvcascavel.com.br',
            'senha': 'Aprovador@SGQ2024',
            'perfil': Perfil.APROVADOR,
        },
    ]

    for dados in usuarios_iniciais:
        existente = Usuario.query.filter_by(email=dados['email']).first()
        if existente:
            print(f"  [SKIP] Usuário já existe: {dados['email']}")
            continue

        usuario = Usuario(
            nome=dados['nome'],
            email=dados['email'],
            perfil=dados['perfil'],
            ativo=True,
        )
        usuario.set_senha(dados['senha'])
        db.session.add(usuario)
        print(f"  [ADD]  {dados['perfil']:40s} → {dados['email']}")

    print()
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  IMPORTANTE: Altere as senhas padrão após o primeiro acesso │")
    print("  └─────────────────────────────────────────────────────────────┘")
    print()
    print("  admin@csvcascavel.com.br      / Admin@SGQ2024")
    print("  qualidade@csvcascavel.com.br  / Qualidade@SGQ2024")
    print("  aprovador@csvcascavel.com.br  / Aprovador@SGQ2024")


if __name__ == '__main__':
    init_database()
