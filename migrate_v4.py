"""
Migration v4 – add correction columns for admin "small fix" feature.

  documentos:
    - correcao_pendente        BOOLEAN  DEFAULT 0   (flag: correction in progress)
    - correcao_content_html    TEXT                  (draft online-editor content)
    - correcao_metadados_json  TEXT                  (draft metadata changes as JSON)

Run once:
    .\venv\Scripts\python migrate_v4.py
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'sgq_cascavel.db')


def add_column_if_missing(cur, table: str, column: str, col_def: str) -> None:
    cur.execute(f"PRAGMA table_info({table})")
    existing = [row[1] for row in cur.fetchall()]
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        print(f"  + {table}.{column}  ({col_def})")
    else:
        print(f"  ~ {table}.{column} already exists — skip")


def main() -> None:
    print(f"Database: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("ERROR: database file not found.")
        raise SystemExit(1)

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    print("\nMigrating 'documentos' table…")
    add_column_if_missing(cur, 'documentos', 'correcao_pendente', 'BOOLEAN NOT NULL DEFAULT 0')
    add_column_if_missing(cur, 'documentos', 'correcao_content_html', 'TEXT')
    add_column_if_missing(cur, 'documentos', 'correcao_metadados_json', 'TEXT')

    con.commit()
    con.close()
    print("\nMigration v4 complete.")


if __name__ == '__main__':
    main()
