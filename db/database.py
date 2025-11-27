# db/database.py
import pandas as pd
import psycopg2
import time
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
import streamlit as st

# ======================================================
#  Engine + credenciais (com cache)
# ======================================================

@st.cache_resource(show_spinner=False)
def get_db_config_and_engine():
    """
    Lê as credenciais do secrets e cria o engine SQLAlchemy
    apenas uma vez por sessão de app (evita recriar a cada rerun).
    """
    cfg = st.secrets["postgres"]

    db_url = URL.create(
        drivername="postgresql+psycopg2",
        username=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database"],
    )

    engine = create_engine(db_url, pool_pre_ping=True)
    return cfg, engine


cfg, engine = get_db_config_and_engine()

DB_USER = cfg["user"]
DB_PASS = cfg["password"]
DB_HOST = cfg["host"]
DB_PORT = cfg["port"]
DB_NAME = cfg["database"]


# ======================================================
#  Funções auxiliares
# ======================================================

def execute(query, params=None):
    """Executa INSERT/UPDATE/DELETE com psycopg2."""
    start = time.perf_counter()
    conn = psycopg2.connect(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
    )
    cur = conn.cursor()
    cur.execute(query, params or ())
    conn.commit()
    cur.close()
    conn.close()
    elapsed = time.perf_counter() - start
    print(f"[PERF][execute] {elapsed:.3f}s  -> {query.split()[0]} ...")



def query_df(sql, params=None) -> pd.DataFrame:
    """Executa SELECT e retorna DataFrame via SQLAlchemy."""
    start = time.perf_counter()
    df = pd.read_sql(sql, engine, params=params)
    elapsed = time.perf_counter() - start
    # Mostra só a primeira linha do SQL pra não poluir muito
    first_line = sql.strip().splitlines()[0]
    print(f"[PERF][query_df] {elapsed:.3f}s  -> {first_line[:80]}...")
    return df



# ======================================================
#  Inicialização do schema (somente manual)
# ======================================================

def init_db():
    """Cria tabelas no PostgreSQL (roda só via script/init_supabase.py)."""
    q_items = """
    CREATE TABLE IF NOT EXISTS items (
        id   INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    );
    """

    q_prices = """
    CREATE TABLE IF NOT EXISTS prices (
        id         SERIAL PRIMARY KEY,
        item_id    INTEGER NOT NULL REFERENCES items(id),
        date       DATE NOT NULL,
        price_zeny INTEGER NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """

    execute(q_items)
    execute(q_prices)


# ======================================================
#  CRUD COM CACHE NAS LEITURAS
# ======================================================

@st.cache_data(ttl=5, show_spinner=False)
def _get_items_df_cached() -> pd.DataFrame:
    return query_df("SELECT id, name FROM items ORDER BY name ASC;")


def get_items_df() -> pd.DataFrame:
    """
    Wrapper em cima do cache.
    Usamos .copy() pra não correr risco de alterar o dataframe cacheado.
    """
    return _get_items_df_cached().copy()


@st.cache_data(ttl=5, show_spinner=False)
def _get_price_history_df_cached(item_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT *
        FROM prices
        WHERE item_id = %s
        ORDER BY date ASC, created_at ASC;
        """,
        (item_id,),
    )


def get_price_history_df(item_id: int) -> pd.DataFrame:
    return _get_price_history_df_cached(item_id).copy()


@st.cache_data(ttl=5, show_spinner=False)
def _get_all_prices_df_cached() -> pd.DataFrame:
    return query_df(
        """
        SELECT 
            p.item_id,
            i.name AS item_name,
            p.date,
            p.price_zeny
        FROM prices p
        JOIN items i ON i.id = p.item_id;
        """
    )


def get_all_prices_df() -> pd.DataFrame:
    return _get_all_prices_df_cached().copy()


def insert_price(item_id: int, date_str: str, price_zeny: float):
    """
    Insere um preço no histórico e limpa o cache de leitura,
    para que as telas mostrem os dados mais recentes.
    """
    execute(
        "INSERT INTO prices (item_id, date, price_zeny) VALUES (%s, %s, %s);",
        (item_id, date_str, price_zeny),
    )

    # Depois de inserir, limpamos o cache para forçar recarregar dados.
    st.cache_data.clear()
