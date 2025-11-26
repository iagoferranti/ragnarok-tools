# db/database.py
import sqlite3
import json
from pathlib import Path

import pandas as pd

# Caminho do banco
DB_PATH = Path(__file__).resolve().parent.parent / "market.db"

# Caminho do items.json
ITEMS_JSON_PATH = Path(__file__).resolve().parent.parent / "items.json"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Reinicializa o banco:
    - DROP TABLE das tabelas principais
    - Recriação de schema
    - Carga dos itens a partir do items.json
    """
    conn = get_connection()
    cur = conn.cursor()

    # 1) Dropa as tabelas (limpa o conteúdo)
    cur.execute("DROP TABLE IF EXISTS prices;")
    cur.execute("DROP TABLE IF EXISTS items;")

    # 2) Cria tabela de itens
    cur.execute(
        """
        CREATE TABLE items (
            id   INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        """
    )

    # 3) Cria tabela de preços (histórico)
    #    Já no formato esperado pelo monitor.py: date + price_zeny
    cur.execute(
        """
        CREATE TABLE prices (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id    INTEGER NOT NULL,
            date       TEXT    NOT NULL,
            price_zeny REAL    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (item_id) REFERENCES items (id)
        );
        """
    )

    # 4) Carrega items.json
    with open(ITEMS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # data: { "6608": "Mana Coagulada", ... }
    items_to_insert = []
    for item_id_str, name in data.items():
        try:
            item_id = int(item_id_str)
        except ValueError:
            # Se tiver alguma chave estranha, ignora
            continue
        items_to_insert.append((item_id, name))

    cur.executemany(
        "INSERT INTO items (id, name) VALUES (?, ?);",
        items_to_insert,
    )

    conn.commit()
    conn.close()

    print(f"[init_db] Carregados {len(items_to_insert)} itens de items.json.")


def reset_db_file():
    """
    Apaga o arquivo market.db e recria tudo chamando init_db().
    Usa se quiser limpeza TOTAL do banco.
    """
    if DB_PATH.exists():
        DB_PATH.unlink()
        print("[reset_db_file] market.db removido.")
    init_db()


def get_items_df() -> pd.DataFrame:
    """
    Retorna um DataFrame com (id, name) dos itens,
    ordenado pelo nome para facilitar o dropdown.
    """
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT id, name FROM items ORDER BY name ASC;",
        conn,
    )
    conn.close()
    return df


def insert_price(item_id: int, date_str: str, price_zeny: float):
    """
    Insere um preço no histórico para o item.

    Parâmetros:
    - item_id: ID do item (int)
    - date_str: data em formato ISO (ex: '2025-11-25') -> vindo do date_input
    - price_zeny: preço em zeny (float ou int)
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO prices (item_id, date, price_zeny)
        VALUES (?, ?, ?);
        """,
        (item_id, date_str, float(price_zeny)),
    )
    conn.commit()
    conn.close()


# ---- FUNÇÕES DE LEITURA DE HISTÓRICO ----

def get_price_history_df(item_id: int) -> pd.DataFrame:
    """
    Retorna o histórico de preços para um item como DataFrame,
    com colunas: id, item_id, date, price_zeny, created_at.
    """
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT id, item_id, date, price_zeny, created_at
        FROM prices
        WHERE item_id = ?
        ORDER BY date ASC, created_at ASC;
        """,
        conn,
        params=(item_id,),
    )
    conn.close()
    return df


def get_price_history(item_id: int) -> pd.DataFrame:
    """
    Alias para manter compatibilidade com o app.py antigo.
    """
    return get_price_history_df(item_id)


def get_all_prices_df() -> pd.DataFrame:
    """
    Retorna todos os registros de preços, já com o nome do item,
    para alimentar o compute_summary.

    Colunas típicas:
    - item_id
    - item_name
    - date
    - price_zeny
    """
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT
            p.item_id,
            i.name AS item_name,
            p.date,
            p.price_zeny
        FROM prices p
        JOIN items i ON i.id = p.item_id;
        """,
        conn,
    )
    conn.close()
    return df
