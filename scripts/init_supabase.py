# scripts/init_supabase.py
from pathlib import Path
import json
from math import ceil

import psycopg2

from db.database import (
    init_db,
    DB_USER,
    DB_PASS,
    DB_HOST,
    DB_PORT,
    DB_NAME,
)


BATCH_SIZE = 1000  # quantidade de itens por lote


def main():
    print(">> Criando tabelas no Supabase...")
    init_db()

    # Caminho do items.json (mesmo lugar do projeto)
    items_path = Path(__file__).resolve().parent.parent / "items.json"

    print(f">> Carregando itens de {items_path} ...")
    with open(items_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # data: { "6608": "Mana Coagulada", ... }
    rows = []
    for k, v in data.items():
        try:
            item_id = int(k)
        except ValueError:
            continue
        rows.append((item_id, v))

    total = len(rows)
    print(f">> Total de itens a inserir: {total}")

    if total == 0:
        print("Nada para inserir. Encerrando.")
        return

    # Conexão única com o Postgres do Supabase
    conn = psycopg2.connect(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
    )
    cur = conn.cursor()

    sql = """
        INSERT INTO items (id, name)
        VALUES (%s, %s)
        ON CONFLICT (id) DO NOTHING;
    """

    n_batches = ceil(total / BATCH_SIZE)
    print(f">> Enviando em {n_batches} lote(s) de até {BATCH_SIZE} itens...")

    for i in range(n_batches):
        start = i * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch = rows[start:end]

        print(f"   - Lote {i+1}/{n_batches} [{start}:{end}] ...", end="", flush=True)
        cur.executemany(sql, batch)
        conn.commit()
        print(" ok")

    cur.close()
    conn.close()

    print("✅ Tabelas criadas e itens carregados com sucesso (batch por lotes)!")


if __name__ == "__main__":
    main()
