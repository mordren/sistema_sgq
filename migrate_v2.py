"""
Migration v2 — Add online editor fields to existing tables.

Run once:  python migrate_v2.py
Safe to re-run (skips columns that already exist).
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'sgq_cascavel.db')


def add_column(cursor, table, column, col_type):
    try:
        cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}')
        print(f'  + {table}.{column}  OK')
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e).lower():
            print(f'  - {table}.{column}  already exists, skipped')
        else:
            raise


def main():
    if not os.path.exists(DB_PATH):
        print(f'Database not found at: {DB_PATH}')
        print('Run init_db.py first.')
        return

    print(f'Migrating: {DB_PATH}')
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Documento
    add_column(cur, 'documentos', 'content_html', 'TEXT')
    add_column(cur, 'documentos', 'content_mode', 'VARCHAR(20)')

    # RevisaoDocumento
    add_column(cur, 'revisoes_documentos', 'content_html', 'TEXT')
    add_column(cur, 'revisoes_documentos', 'content_mode', 'VARCHAR(20)')

    conn.commit()
    conn.close()
    print('Migration complete.')


if __name__ == '__main__':
    main()
