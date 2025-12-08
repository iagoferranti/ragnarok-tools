# db/database.py
import time

import pandas as pd
import psycopg2
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

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
#  Helpers
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
    first_line = sql.strip().splitlines()[0]
    print(f"[PERF][query_df] {elapsed:.3f}s  -> {first_line[:80]}...")
    return df


def to_int_or_none(value):
    """
    Converte qualquer tipo numérico (incluindo numpy.int64) para int normal.
    Retorna None se vier NaN ou None.
    """
    if value is None:
        return None
    # pd.isna cobre pandas/numpy
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return int(value)


# ======================================================
#  Função para checar preço existente
#  (agora considerando variation_key)
# ======================================================
def get_existing_price(
    item_id: int,
    date_str: str,
    variation_key: str | None = None,
) -> int | None:
    """
    Retorna o preço já cadastrado para (item_id, date, variation_key).
    Se variation_key não for informado, usa string vazia (variação padrão).
    """
    vk = variation_key or ""

    df = query_df(
        """
        SELECT price_zeny
        FROM prices
        WHERE item_id = %s
          AND date = %s
          AND variation_key = %s
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (item_id, date_str, vk),
    )

    if df.empty:
        return None

    return int(df.iloc[0]["price_zeny"])


# ======================================================
#  Função para atualizar preço existente
# ======================================================
def update_price(
    item_id: int,
    date_str: str,
    price_zeny: float,
    variation_key: str = "",
):
    """
    Atualiza o preço de um item em um dia específico
    para uma DETERMINADA variação (variation_key).
    """
    if price_zeny <= 0:
        raise ValueError("price_zeny deve ser > 0")

    execute(
        """
        UPDATE prices
           SET price_zeny = %s,
               updated_at = NOW()
         WHERE item_id = %s
           AND date = %s
           AND variation_key = %s;
        """,
        (price_zeny, item_id, date_str, variation_key or ""),
    )

    # Limpa cache de leitura após alteração
    st.cache_data.clear()


# ======================================================
#  Funções de auditoria básicas (logs simples)
# ======================================================
def log_price_change(
    item_id: int,
    date_str: str,
    old_price_zeny: int | None,
    new_price_zeny: int,
    changed_by: str,
    source: str = "DIRECT_ADMIN",
    refine: int | None = None,
    card_ids: str | None = None,
    extra_desc: str | None = None,
    variation_key: str | None = None,
):
    """
    Registra um log simples de alteração de preço.
    Usa tabela price_change_logs (se existir).
    Agora inclui campos de variação (refine, card_ids, extra_desc, variation_key).
    """
    try:
        execute(
            """
            INSERT INTO price_change_logs
                (item_id, date, old_price_zeny, new_price_zeny,
                 changed_by, source, refine, card_ids, extra_desc, variation_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                item_id,
                date_str,
                old_price_zeny,
                new_price_zeny,
                changed_by,
                source,
                refine,
                card_ids,
                extra_desc,
                variation_key or "",
            ),
        )
    except Exception as e:
        # Não queremos quebrar nada se essa tabela não existir ainda
        print(f"[WARN] Falha ao gravar em price_change_logs: {e}")


# ======================================================
#  Inicialização do schema (somente manual)
#  (mantida simples, já que hoje você cria as tabelas via script SQL separado)
# ======================================================
def init_db():
    """Cria tabelas base no PostgreSQL (roda só via script/init_supabase.py)."""
    q_items = """
    CREATE TABLE IF NOT EXISTS items (
        id   INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    );
    """

    # Versão atualizada da tabela prices para novos ambientes
    q_prices = """
    CREATE TABLE IF NOT EXISTS prices (
        id            SERIAL PRIMARY KEY,
        item_id       INTEGER NOT NULL REFERENCES items(id),
        date          DATE NOT NULL,
        price_zeny    INTEGER NOT NULL,
        refine        INTEGER NOT NULL DEFAULT 0,
        card_ids      TEXT,
        extra_desc    TEXT,
        variation_key TEXT NOT NULL DEFAULT '',
        created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at    TIMESTAMP
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
            p.price_zeny,
            p.refine,
            p.card_ids,
            p.extra_desc,
            p.variation_key
        FROM prices p
        JOIN items i ON i.id = p.item_id;
        """
    )


def get_all_prices_df() -> pd.DataFrame:
    return _get_all_prices_df_cached().copy()


def insert_price(
    item_id: int,
    date_str: str,
    price_zeny: int,
    refine: int | None = 0,
    card_ids: list[int] | None = None,
    extra_desc: str | None = None,
    variation_key: str | None = None,
):
    """
    Insere um preço no histórico.
    Assumimos que (item_id, date, variation_key) ainda NÃO existe.

    OBS:
      - refine / card_ids / extra_desc / variation_key têm default,
        então chamadas antigas com 3 parâmetros continuam funcionando
        (variação "default": variation_key = "").
    """

    # garante que refine nunca vai como NULL
    if refine is None:
        refine = 0

    if price_zeny <= 0:
        raise ValueError("price_zeny deve ser > 0")

    vk = variation_key or ""

    # Converte card_ids (lista) para string, pois a coluna é text
    if isinstance(card_ids, list):
        card_ids_db = ",".join(map(str, card_ids)) if card_ids else None
    else:
        card_ids_db = card_ids  # já é string ou None

    execute(
        """
        INSERT INTO prices
            (item_id, date, price_zeny, refine, card_ids, extra_desc, variation_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
        """,
        (item_id, date_str, int(price_zeny), refine, card_ids_db, extra_desc, vk),
    )

    # Descobre quem é o usuário (uma vez só)
    user_email = (
        st.session_state.get("user_email")
        or st.session_state.get("username")
        or "desconhecido"
    )

    # 🔍 Log fino de auditoria (price_audit_log)
    try:
        log_price_action(
            item_id=item_id,
            date_str=date_str,
            action_type="insert",
            actor_email=user_email,
            actor_role="admin"
            if user_email in st.secrets["roles"]["admins"]
            else "user",
            old_price=None,
            new_price=int(price_zeny),
            request_id=None,
            refine=refine,
            card_ids=card_ids_db,
            extra_desc=extra_desc,
            variation_key=vk,
        )
    except Exception as e:
        print(f"[WARN] Falha ao logar insert em price_audit_log: {e}")

    # 📚 Log macro na price_change_logs (criação de preço)
    try:
        log_price_change(
            item_id=item_id,
            date_str=date_str,
            old_price_zeny=0,  # ou None, se você preferir marcar como "sem valor anterior"
            new_price_zeny=int(price_zeny),
            changed_by=user_email,
            source="INSERT",
            refine=refine,
            card_ids=card_ids_db,
            extra_desc=extra_desc,
            variation_key=vk,
        )
    except Exception as e:
        print(f"[WARN] Falha ao logar criação de preço: {e}")

    # Depois de inserir, limpamos o cache para forçar recarregar dados.
    st.cache_data.clear()


def delete_price(item_id: int, date_str: str, variation_key: str | None) -> None:
    """
    Remove o registro único de preço de (item_id, date, variation_key).
    Como em todo o resto do código, tratamos variation_key None como string vazia ("").
    """
    vk = variation_key or ""

    execute(
        """
        DELETE FROM prices
        WHERE item_id = %s
          AND date = %s
          AND variation_key = %s;
        """,
        (item_id, date_str, vk),
    )

    # Limpa caches para refletir o delete na UI
    st.cache_data.clear()


# ======================================================
#  Auditoria avançada (price_change_requests + price_audit_log)
# ======================================================
def log_price_action(
    item_id: int,
    date_str: str,
    action_type: str,
    actor_email: str,
    actor_role: str,
    old_price: int | None = None,
    new_price: int | None = None,
    request_id: int | None = None,
    refine: int | None = None,
    card_ids: str | None = None,
    extra_desc: str | None = None,
    variation_key: str | None = None,
):
    """
    Grava um log de qualquer ação de preço.
    action_type: insert | update | delete | request_create | request_approve | request_reject
    Usa tabela price_audit_log (se existir).
    Agora registra também os campos de variação.
    """
    try:
        execute(
            """
            INSERT INTO price_audit_log
                (item_id, date, action_type, old_price, new_price,
                 actor_email, actor_role, request_id,
                 refine, card_ids, extra_desc, variation_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                item_id,
                date_str,
                action_type,
                old_price,
                new_price,
                actor_email,
                actor_role,
                request_id,
                refine,
                card_ids,
                extra_desc,
                variation_key or "",
            ),
        )
    except Exception as e:
        print(f"[WARN] Falha ao gravar em price_audit_log: {e}")


def create_price_change_request(
    item_id: int,
    date_str: str,
    old_price_zeny: int,
    new_price_zeny: int,
    requested_by: str,
    reason: str | None = None,
    refine: int | None = None,
    card_ids: str | None = None,
    extra_desc: str | None = None,
    variation_key: str | None = None,
) -> int:
    """
    Cria um pedido de alteração e retorna seu ID.

    OBS: refine / card_ids / extra_desc / variation_key têm default,
    então chamadas antigas continuam válidas.
    """
    conn = psycopg2.connect(
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
    )
    cur = conn.cursor()
    vk = variation_key or ""
    cur.execute(
        """
        INSERT INTO price_change_requests
            (item_id, date, old_price, new_price,
             reason, created_by, refine, card_ids, extra_desc, variation_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (
            item_id,
            date_str,
            old_price_zeny,
            new_price_zeny,
            reason,
            requested_by,
            refine,
            card_ids,
            extra_desc,
            vk,
        ),
    )
    req_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    # tenta logar na price_audit_log (se existir)
    try:
        log_price_action(
            item_id=item_id,
            date_str=date_str,
            action_type="request_create",
            actor_email=requested_by,
            actor_role="user",
            old_price=old_price_zeny,
            new_price=new_price_zeny,
            request_id=req_id,
            refine=refine,
            card_ids=card_ids,
            extra_desc=extra_desc,
            variation_key=vk,
        )
    except Exception as e:
        print(f"[WARN] Falha ao gravar em price_audit_log (create): {e}")

    return req_id


@st.cache_data(ttl=5, show_spinner=False)
def get_pending_requests():
    """
    Retorna todos os pedidos pendentes (para admins).
    """
    return query_df(
        """
        SELECT r.*, i.name AS item_name
        FROM price_change_requests r
        JOIN items i ON i.id = r.item_id
        WHERE r.status = 'pending'
        ORDER BY r.created_at ASC;
        """
    )


def approve_price_request(
    request_id: int,
    reviewer_email: str,
):
    """
    Admin aprova a solicitação → atualiza o preço e fecha o pedido.
    """
    # 1. Pega dados da solicitação
    df = query_df(
        "SELECT * FROM price_change_requests WHERE id = %s;",
        (request_id,),
    )
    if df.empty:
        raise ValueError("Solicitação não encontrada.")

    row = df.iloc[0]
    item_id = int(row["item_id"])
    date_str = str(row["date"])
    old_price = int(row["old_price"]) if row["old_price"] is not None else None
    new_price = int(row["new_price"])
    refine = to_int_or_none(row.get("refine"))
    card_ids = row.get("card_ids")
    extra_desc = row.get("extra_desc")
    variation_key = row.get("variation_key") or ""

    # 2. Atualiza preço real
    update_price(item_id, date_str, new_price, variation_key=variation_key)

    # 3. Marca solicitação como aprovada
    execute(
        """
        UPDATE price_change_requests
        SET status = 'approved',
            reviewed_by = %s,
            reviewed_at = NOW()
        WHERE id = %s;
        """,
        (reviewer_email, request_id),
    )

    # 4. Log da aprovação na trilha "macro"
    log_price_action(
        item_id=item_id,
        date_str=date_str,
        action_type="request_approve",
        actor_email=reviewer_email,
        actor_role="admin",
        old_price=old_price,
        new_price=new_price,
        request_id=request_id,
        refine=refine,
        card_ids=card_ids,
        extra_desc=extra_desc,
        variation_key=variation_key,
    )

    # 5. Log simples de alteração efetiva (price_change_logs), se existir
    try:
        log_price_change(
            item_id=item_id,
            date_str=date_str,
            old_price_zeny=old_price if old_price is not None else 0,
            new_price_zeny=new_price,
            changed_by=reviewer_email,
            source="REQUEST_APPROVED",
            refine=refine,
            card_ids=card_ids,
            extra_desc=extra_desc,
            variation_key=variation_key,
        )
    except Exception as e:
        print(f"[WARN] Falha ao gravar em price_change_logs na aprovação: {e}")


def reject_price_request(
    request_id: int,
    reviewer_email: str,
    comment: str | None = None,
):
    """
    Admin rejeita a solicitação.
    """
    execute(
        """
        UPDATE price_change_requests
        SET status = 'rejected',
            reviewed_by = %s,
            reviewed_at = NOW(),
            review_comment = %s
        WHERE id = %s;
        """,
        (reviewer_email, comment, request_id),
    )

    # Log da rejeição
    df = query_df(
        """
        SELECT item_id, date, old_price, new_price,
               refine, card_ids, extra_desc, variation_key
        FROM price_change_requests
        WHERE id = %s;
        """,
        (request_id,),
    )

    if not df.empty:
        row = df.iloc[0]
        item_id = int(row["item_id"])
        date_str = str(row["date"])
        old_price = to_int_or_none(row["old_price"])
        new_price = to_int_or_none(row["new_price"])
        refine = to_int_or_none(row.get("refine"))
        card_ids = row.get("card_ids")
        extra_desc = row.get("extra_desc")
        variation_key = row.get("variation_key") or ""

        log_price_action(
            item_id=item_id,
            date_str=date_str,
            action_type="request_reject",
            actor_email=reviewer_email,
            actor_role="admin",
            old_price=old_price,
            new_price=new_price,
            request_id=request_id,
            refine=refine,
            card_ids=card_ids,
            extra_desc=extra_desc,
            variation_key=variation_key,
        )

    # Limpa caches (inclusive lista de pendentes)
    st.cache_data.clear()
