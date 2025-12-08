# pages/01_📈_Monitor_de_Mercado.py
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st
import unicodedata

from ui.theme import apply_theme
from db.database import (
    get_items_df,
    insert_price,
    get_price_history_df,
    get_all_prices_df,
    get_existing_price,
    update_price,
    create_price_change_request,
    log_price_change,
    log_price_action,
    get_pending_requests,
)
from services.market import compute_summary

# ============================================
#  Tema / layout base
# ============================================
st.markdown(
    """
    <style>
    /* Layout das colunas do st.dataframe (nova estrutura) */

    /* 1ª coluna: Item */
    div[data-testid="stDataFrame"] div[role="row"] > div:nth-child(1) {
        min-width: 260px !important;
        max-width: 340px !important;
        white-space: nowrap;
    }

    /* 2ª coluna: Cartas */
    div[data-testid="stDataFrame"] div[role="row"] > div:nth-child(2) {
        min-width: 220px !important;
        max-width: 320px !important;
        white-space: nowrap;
    }

    /* 3ª coluna: Última data */
    div[data-testid="stDataFrame"] div[role="row"] > div:nth-child(3) {
        min-width: 120px !important;
        max-width: 140px !important;
        white-space: nowrap;
    }

    /* 4ª coluna: Últ. preço */
    div[data-testid="stDataFrame"] div[role="row"] > div:nth-child(4) {
        min-width: 130px !important;
        max-width: 150px !important;
        white-space: nowrap;
    }

    /* 5ª coluna: Média 5d */
    div[data-testid="stDataFrame"] div[role="row"] > div:nth-child(5) {
        min-width: 130px !important;
        max-width: 150px !important;
        white-space: nowrap;
    }

    /* 6ª coluna: Var % vs 5d */
    div[data-testid="stDataFrame"] div[role="row"] > div:nth-child(6) {
        min-width: 130px !important;
        max-width: 150px !important;
        white-space: nowrap;
    }

    /* 7ª coluna: Status */
    div[data-testid="stDataFrame"] div[role="row"] > div:nth-child(7) {
        min-width: 110px !important;
        max-width: 130px !important;
        white-space: nowrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

apply_theme("Monitor de Mercado – Ragnarok LATAM", page_icon="📈")


def is_admin() -> bool:
    """Retorna True se o e-mail logado estiver na lista de admins."""
    email = (st.session_state.get("user_email") or "").lower()
    admins = [e.lower() for e in st.secrets["roles"]["admins"]]
    return email in admins


def normalize_text(txt: str) -> str:
    if not isinstance(txt, str):
        return ""
    return (
        unicodedata.normalize("NFKD", txt)
        .encode("ASCII", "ignore")
        .decode("utf-8")
        .lower()
    )


# ============================================
#  Cache de dados
# ============================================
@st.cache_data(ttl=30, show_spinner=False)
def get_items_cached() -> pd.DataFrame:
    return get_items_df()


@st.cache_data(ttl=30, show_spinner=False)
def get_all_prices_cached() -> pd.DataFrame:
    return get_all_prices_df()


@st.cache_data(ttl=30, show_spinner=False)
def get_price_history_cached(item_id: int, variation_key: str | None) -> pd.DataFrame:
    """
    Wrapper cacheado para histórico.
    Se variation_key for informado, filtra; caso contrário, retorna histórico completo do item.
    """
    df = get_price_history_df(item_id)
    if variation_key:
        df = df[df["variation_key"] == variation_key]
    return df.copy()


def build_display_name(
    item_name: str,
    refine: int | None,
    card_ids,
    extra_desc: str | None,
    card_id_to_name: dict[int, str],
) -> str:
    """
    Monta o nome exibido no dashboard:
    Ex: "Memorável Vingança dos Mortos — +12 | IT 6, Sorte +3, Sor +3 | Cartas: Louva-a-deus Angra"
    - card_ids pode ser lista[int] OU string "4513,4520"
    """
    parts: list[str] = []

    # refino
    if refine is not None:
        try:
            r = int(refine)
        except Exception:
            r = None
        if r and r > 0:
            parts.append(f"+{r}")

    # extra / encantos
    if isinstance(extra_desc, str) and extra_desc.strip():
        parts.append(extra_desc.strip())

    # cartas
    ids_list: list[int] = []
    if isinstance(card_ids, list):
        ids_list = [int(c) for c in card_ids if c is not None]
    elif isinstance(card_ids, str) and card_ids.strip():
        for tok in card_ids.split(","):
            tok = tok.strip()
            if tok:
                try:
                    ids_list.append(int(tok))
                except ValueError:
                    # se vier lixo, ignora aquele token
                    pass

    if ids_list:
        labels = [card_id_to_name.get(cid, str(cid)) for cid in ids_list]
        parts.append("Cartas: " + ", ".join(labels))

    if parts:
        return f"{item_name} — " + " | ".join(parts)
    else:
        return item_name


@st.cache_data(ttl=30, show_spinner=False)
def get_global_summary_cached() -> pd.DataFrame:
    """
    Resumo global por VARIAÇÃO do item (cada combinação refino+cartas+extra vira uma linha).
    Agora já devolve também uma coluna 'Cartas' agregada
    (ex: "2x Carta Louva-a-deus Angra, 1x Carta Cavaleiro do Abismo").
    """
    df_prices_all = get_all_prices_cached()
    if df_prices_all.empty:
        return pd.DataFrame()

    # Mapa id -> nome (para cartas / display)
    items_df = get_items_cached()
    card_id_to_name = dict(zip(items_df["id"], items_df["name"]))

    df = df_prices_all.copy()

    # Nome exibido levando em conta refino, cartas e encantos
    df["item_display"] = df.apply(
        lambda r: build_display_name(
            item_name=r["item_name"],
            refine=r.get("refine"),
            card_ids=r.get("card_ids"),
            extra_desc=r.get("extra_desc"),
            card_id_to_name=card_id_to_name,
        ),
        axis=1,
    )

    # Garante coluna variation_key
    if "variation_key" not in df.columns:
        df["variation_key"] = "base"
    df["variation_key"] = df["variation_key"].fillna("base")

    # Cada combinação (item_id + variation_key) vira um "item" independente
    df["item_id_var"] = df["item_id"].astype(str) + "|" + df["variation_key"]

    # ---- Cartas agregadas por variação (para o resumo) ----
    df["date_parsed"] = pd.to_datetime(df["date"])

    last_per_var = (
        df.sort_values("date_parsed")
        .groupby("item_id_var", as_index=False)
        .last()
    )

    from collections import Counter

    def summarize_cards(card_ids_raw):
        ids_list: list[int] = []
        if isinstance(card_ids_raw, list):
            ids_list = [int(c) for c in card_ids_raw if c is not None]
        elif isinstance(card_ids_raw, str) and card_ids_raw.strip():
            for tok in card_ids_raw.split(","):
                tok = tok.strip()
                if tok:
                    try:
                        ids_list.append(int(tok))
                    except ValueError:
                        pass

        if not ids_list:
            return "-"

        counts = Counter(ids_list)
        labels: list[str] = []
        for cid, qty in counts.items():
            name = card_id_to_name.get(cid, str(cid))
            labels.append(f"{qty}x {name}")
        return ", ".join(labels)

    last_per_var["Cartas"] = last_per_var["card_ids"].apply(summarize_cards)

    df_cards_agg = last_per_var[["item_id_var", "item_display", "Cartas"]].rename(
        columns={"item_display": "Item"}
    )

    # ---- DataFrame de entrada para compute_summary ----
    df_summary_input = df[
        ["item_id_var", "item_display", "date", "price_zeny"]
    ].rename(
        columns={
            "item_id_var": "item_id",
            "item_display": "item",
        }
    )

    df_summary = compute_summary(df_summary_input)

    # Merge das cartas no resumo global
    df_summary = df_summary.merge(
        df_cards_agg[["item_id_var", "Cartas"]]
        .rename(columns={"item_id_var": "Item ID"}),
        left_on="Item ID",
        right_on="Item ID",
        how="left",
    ) if "Item ID" in df_summary.columns else df_summary.merge(
        df_cards_agg[["Item", "Cartas"]],
        on="Item",
        how="left",
    )

    if "Cartas" not in df_summary.columns:
        df_summary["Cartas"] = "-"

    df_summary["Cartas"] = df_summary["Cartas"].fillna("-")

    return df_summary


# ============================================
#  Helpers de formatação
# ============================================
def fmt_zeny(v: float | int | None) -> str:
    if v is None or pd.isna(v):
        return "-"
    return f"{float(v):,.0f}".replace(",", ".")


def fmt_pct(v: float | None, sinal: bool = True) -> str:
    if v is None or pd.isna(v):
        return "-"
    if sinal:
        return f"{v:+.1f}%"
    return f"{v:.1f}%"


def style_market_table(df: pd.DataFrame):
    """
    Aplica cores nas colunas de variação e Status.
    """

    def color_var(val):
        if not isinstance(val, str):
            return ""
        txt = val.replace("%", "").replace(",", ".")
        try:
            num = float(txt)
        except ValueError:
            return ""
        if num > 0:
            return "color:#22c55e;"
        if num < 0:
            return "color:#ef4444;"
        return ""

    def color_status(val):
        if isinstance(val, str) and val.lower() == "vender":
            return "color:#ef4444;"
        if isinstance(val, str) and val.lower() == "comprar":
            return "color:#22c55e;"
        return ""

    styler = df.style

    var_cols = []
    if "Variação % vs média 5" in df.columns:
        var_cols.append("Variação % vs média 5")
    if "Var % vs 5d" in df.columns:
        var_cols.append("Var % vs 5d")

    if var_cols:
        styler = styler.applymap(color_var, subset=var_cols)

    if "Status" in df.columns:
        styler = styler.applymap(color_status, subset=["Status"])

    return styler


def build_variation_key(refine: int, cards: list[int] | None, extra: str | None) -> str:
    """
    Gera chave de variação determinística para diferenciar:
    - refinos
    - combinações de cartas
    - encantos / observações
    """
    parts: list[str] = []

    # refino
    parts.append(f"r{int(refine)}")

    # cartas (ordenadas e únicas)
    if cards:
        cards_sorted = sorted(set(cards))
        cards_str = "-".join(str(cid) for cid in cards_sorted)
        parts.append(f"c{cards_str}")

    # extra (normalizado, sem acento, lower)
    if extra:
        norm = normalize_text(extra).replace("|", " ").strip()
        if norm:
            parts.append(f"e{norm}")

    return "|".join(parts)


def describe_variation(
    refine: int,
    cards: list[int] | None,
    extra: str | None,
    card_id_to_name: dict[int, str],
) -> str:
    """
    Descrição amigável p/ avisos de conflito.
    """
    parts: list[str] = []

    if refine:
        parts.append(f"+{int(refine)}")

    if cards:
        labels = [card_id_to_name.get(cid, str(cid)) for cid in cards]
        parts.append("Cartas: " + ", ".join(labels))

    if extra and extra.strip():
        parts.append(extra.strip())

    if not parts:
        return "Padrão (sem refino / cartas / encantos)"

    return " | ".join(parts)


# ============================================
#  Página principal
# ============================================
def render():
    ss = st.session_state

    # -------------------------------------------------
    # RESET DE CAMPOS DE VARIAÇÃO (rodado ANTES DOS WIDGETS)
    # -------------------------------------------------
    if ss.get("reset_variation_fields", False):
        ss["var_refine"] = 0
        ss["var_extra_desc"] = ""
        ss["var_card_slot_1"] = "(vazio)"
        ss["var_card_slot_2"] = "(vazio)"
        ss["var_card_slot_3"] = "(vazio)"
        ss["var_card_slot_4"] = "(vazio)"
        ss["reset_variation_fields"] = False

    st.title("📈 Monitor de Mercado – Ragnarok LATAM")

    if "is_saving" not in ss:
        ss["is_saving"] = False

    # Overlay global enquanto está salvando
    if ss.get("is_saving", False):
        st.markdown(
            """
            <style>
            .loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(0, 0, 0, 0.65);
                z-index: 9999;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .loading-overlay-content {
                background: rgba(15,23,42,0.95);
                padding: 1.5rem 2rem;
                border-radius: 0.75rem;
                border: 1px solid rgba(59,130,246,0.7);
                font-size: 0.95rem;
            }
            </style>
            <div class="loading-overlay">
              <div class="loading-overlay-content">
                ⏳ Processando sua ação...<br/>
                <small>Por favor, aguarde alguns segundos.</small>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ------------------------------
    #  Estado global simples
    # ------------------------------
    if "price_value" not in ss:
        ss["price_value"] = ""
    if "last_item_id" not in ss:
        ss["last_item_id"] = None
    if "clear_price" not in ss:
        ss["clear_price"] = False
    if "flash_message" not in ss:
        ss["flash_message"] = ""
    if "flash_type" not in ss:
        ss["flash_type"] = "success"
    if "pending_update" not in ss:
        ss["pending_update"] = None
    if "price_action" not in ss:
        ss["price_action"] = None
    if "var_refine" not in ss:
        ss["var_refine"] = 0
    if "var_extra_desc" not in ss:
        ss["var_extra_desc"] = ""
    for i in range(1, 5):
        key = f"var_card_slot_{i}"
        if key not in ss:
            ss[key] = "(vazio)"

    # ------------------------------
    #  Carrega itens e preços
    # ------------------------------
    items_df = get_items_cached()
    if items_df.empty:
        st.warning("Nenhum item encontrado. Verifique o arquivo items.json.")
        return

    df_prices_all = get_all_prices_cached()

    # Itens "canônicos" por nome
    items_df_sorted = items_df.sort_values("id")
    items_canonical = (
        items_df_sorted.groupby("name", as_index=False).first()[["id", "name"]]
    )

    item_list: list[dict] = []
    for row in items_canonical.to_dict(orient="records"):
        name = row["name"]
        item_list.append(
            {
                "id": int(row["id"]),
                "name": name,
                "norm": normalize_text(name),
            }
        )

    # Lista de cartas
    cards_df = items_df_sorted[
        items_df_sorted["name"].str.contains("carta", case=False, na=False)
    ]
    cards_list: list[dict] = []
    for row in cards_df.to_dict(orient="records"):
        name = row["name"]
        cards_list.append(
            {
                "id": int(row["id"]),
                "name": name,
                "norm": normalize_text(name),
            }
        )
    card_id_to_name: dict[int, str] = {c["id"]: c["name"] for c in cards_list}

    # ======================================================
    #  Seleção de item (somente fluxo normal, sem demo)
    # ======================================================
    item_selected = None

    col_search, col_btn_search = st.columns([4, 1])

    with col_search:
        query = st.text_input(
            "🔎 Buscar item",
            placeholder="Ex: edic, pocao, poçao, poção...",
            key="search_item",
        )

    with col_btn_search:
        st.markdown("<div style='height: 1.75rem'></div>", unsafe_allow_html=True)
        st.button(
            "Buscar",
            key="btn_search_item",
            use_container_width=True,
            help="Clique aqui ou pressione Enter após digitar para buscar o item",
        )

    query_norm = normalize_text(query)
    filtered_items = item_list

    if query_norm:
        starts = [it for it in item_list if it["norm"].startswith(query_norm)]
        contains = [
            it
            for it in item_list
            if (query_norm in it["norm"]) and (it not in starts)
        ]
        filtered_items = starts + contains

        if not filtered_items:
            st.warning("Nenhum item encontrado para esse termo de busca.")
            return

        n = len(filtered_items)

        if n == 1:
            item_selected = filtered_items[0]
            st.info(
                f"Item selecionado automaticamente: "
                f"**{item_selected['name']} ({item_selected['id']})**"
            )
        elif n <= 10:
            st.warning("Foram encontrados vários itens, selecione o correto:")

            labels = [f"{it['name']} ({it['id']})" for it in filtered_items]
            choice = st.radio(
                "Itens encontrados:",
                options=labels,
                key="search_radio",
            )
            idx = labels.index(choice)
            item_selected = filtered_items[idx]

        elif n <= 300:
            st.warning(
                f"Foram encontrados **{n} itens** para esse termo. "
                f"Você pode refinar a busca (ex: `pocao branca`) "
                f"ou escolher na lista abaixo."
            )

            labels = [f"{it['name']} ({it['id']})" for it in filtered_items]
            label_to_item = {lbl: it for lbl, it in zip(labels, filtered_items)}

            col_item, _, _, _ = st.columns([3, 2, 2, 1])
            with col_item:
                choice = st.selectbox(
                    "Itens encontrados:",
                    options=labels,
                    key="search_select_filtered",
                    label_visibility="collapsed",
                )

            item_selected = label_to_item[choice]
        else:
            st.warning(
                f"Foram encontrados **{n} itens**. "
                "Refine sua busca adicionando mais termos, "
                "por exemplo: `pocao branca pequena`."
            )
            return
    else:
        filtered_items = item_list
        if not filtered_items:
            st.warning("Nenhum item encontrado. Verifique o arquivo items.json.")
            return

        selectbox_kwargs: dict = {}
        default_item_id = None
        if not df_prices_all.empty:
            df_tmp = df_prices_all.copy()
            df_tmp["date_parsed"] = pd.to_datetime(df_tmp["date"])
            last_row = df_tmp.sort_values("date_parsed", ascending=False).iloc[0]
            default_item_id = int(last_row["item_id"])

        if default_item_id is not None:
            for i, it in enumerate(filtered_items):
                if it["id"] == default_item_id:
                    selectbox_kwargs["index"] = i
                    break

        col_item, _, _, _ = st.columns([3, 2, 2, 1])
        with col_item:
            item_selected = st.selectbox(
                "",
                options=filtered_items,
                format_func=lambda it: f"{it['name']} ({it['id']})",
                key="search_select",
                label_visibility="collapsed",
                **selectbox_kwargs,
            )

    if item_selected is None:
        st.info("Escolha um item para começar.")
        return

    item_id = item_selected["id"]
    item_name = item_selected["name"]

    # ======================================================
    #  Variações existentes desse item (para combo + análise)
    # ======================================================
    existing_variations: list[dict] = []
    if not df_prices_all.empty:
        df_item_vars = df_prices_all[
            (df_prices_all["item_id"] == item_id)
            & df_prices_all["variation_key"].notna()
        ].copy()

        if not df_item_vars.empty:
            df_item_vars["date_parsed"] = pd.to_datetime(df_item_vars["date"])
            df_item_vars = df_item_vars.sort_values("date_parsed")

            last_per_var = df_item_vars.groupby("variation_key", as_index=False).last()

            for _, row in last_per_var.iterrows():
                vk = row["variation_key"]
                refine_val = row.get("refine")
                extra_desc_val = row.get("extra_desc")
                card_ids_raw = row.get("card_ids")

                card_ids_list: list[int] = []
                if isinstance(card_ids_raw, list):
                    card_ids_list = [int(c) for c in card_ids_raw if c is not None]
                elif isinstance(card_ids_raw, str) and card_ids_raw.strip():
                    for tok in card_ids_raw.split(","):
                        tok = tok.strip()
                        if tok:
                            try:
                                card_ids_list.append(int(tok))
                            except ValueError:
                                pass

                display_name = build_display_name(
                    item_name=item_name,
                    refine=refine_val,
                    card_ids=card_ids_list,
                    extra_desc=extra_desc_val,
                    card_id_to_name=card_id_to_name,
                )

                existing_variations.append(
                    {
                        "variation_key": vk,
                        "refine": int(refine_val) if refine_val is not None else 0,
                        "extra_desc": extra_desc_val or "",
                        "card_ids_list": card_ids_list,
                        "display_name": display_name,
                    }
                )

    # ======================================================
    #  BLOCO DE EDIÇÃO / REGISTRO DE PREÇO
    # ======================================================
    current_variation_key: str | None = None
    current_display_name = item_name

    action = ss.get("price_action")

    if action == "confirm_update":
        pending = ss.get("pending_update")
        if pending is not None:
            admin_flag = is_admin()
            user_id = ss.get("user_email") or ss.get("username") or "desconhecido"
            vk = pending.get("variation_key", "") or ""

            if admin_flag:
                update_price(
                    pending["item_id"],
                    pending["date_str"],
                    pending["new_price"],
                    variation_key=vk,
                )
                try:
                    log_price_change(
                        item_id=pending["item_id"],
                        date_str=pending["date_str"],
                        old_price_zeny=pending["existing_price"],
                        new_price_zeny=pending["new_price"],
                        changed_by=user_id,
                        source="DIRECT_ADMIN",
                        refine=pending.get("refine"),
                        card_ids=pending.get("card_ids_str"),
                        extra_desc=pending.get("extra_desc"),
                        variation_key=vk,
                    )
                except Exception as e:
                    print(f"[WARN] Falha ao logar alteração de preço: {e}")

                try:
                    log_price_action(
                        item_id=pending["item_id"],
                        date_str=pending["date_str"],
                        action_type="update",
                        actor_email=user_id,
                        actor_role="admin",
                        old_price=pending["existing_price"],
                        new_price=pending["new_price"],
                        request_id=None,
                        refine=pending.get("refine"),
                        card_ids=pending.get("card_ids_str"),
                        extra_desc=pending.get("extra_desc"),
                        variation_key=vk,
                    )
                except Exception as e:
                    print(
                        f"[WARN] Falha ao logar ação de update em price_audit_log: {e}"
                    )

                get_all_prices_cached.clear()
                get_global_summary_cached.clear()
                get_price_history_cached.clear()

                ss["clear_price"] = True
                ss["flash_message"] = "Preço atualizado com sucesso!"
                ss["flash_type"] = "success"
                ss["pending_update"] = None
                ss["price_action"] = None
                st.rerun()
            else:
                try:
                    req_id = create_price_change_request(
                        pending["item_id"],
                        pending["date_str"],
                        pending["existing_price"],
                        pending["new_price"],
                        user_id,
                        None,
                        refine=pending.get("refine"),
                        card_ids=pending.get("card_ids_str"),
                        extra_desc=pending.get("extra_desc"),
                        variation_key=vk,
                    )
                    print(f"===== DEBUG: Solicitação criada com id={req_id} =====")
                    ss["flash_message"] = (
                        "Solicitação de alteração enviada para os administradores."
                    )
                    ss["flash_type"] = "info"
                except Exception as e:
                    print("\n===== DEBUG ERROR =====")
                    print("Erro no envio da solicitação:")
                    print(e)
                    print("Tipo:", type(e))
                    print("========================\n")
                    ss["flash_message"] = (
                        "Não foi possível enviar a solicitação. "
                        "Tente novamente mais tarde ou fale com um admin."
                    )

                ss["pending_update"] = None
                ss["price_action"] = None
                st.rerun()

    elif action == "cancel_update":
        ss["pending_update"] = None
        ss["flash_message"] = "Atualização cancelada. Nenhuma alteração foi feita."
        ss["flash_type"] = "info"
        ss["price_action"] = None
        st.rerun()

    # ------------------------------
    #  Bloco de variação do item
    # ------------------------------
    st.markdown("---")
    st.markdown(
        """
        <div class="card">
          <div class="section-title">
            <span class="icon">🎯</span>
            <span>Configuração do item (refino, cartas, encantos)</span>
          </div>
          <div class="section-subtitle">
            Essas informações descrevem a variação do item e serão usadas
            em todos os registros de preço que você fizer.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1) Combo de configuração base (existente x nova)
    base_options = ["Nova variação"] + [v["display_name"] for v in existing_variations]
    label_to_var = {v["display_name"]: v for v in existing_variations}

    config_choice = st.selectbox(
        "Configuração base para registrar",
        options=base_options,
        key=f"config_variation_select_{item_id}",
    )
    is_existing_config = config_choice != "Nova variação"

    # Se for variação existente, preenche state com a config e trava campos
    if is_existing_config:
        rec_cfg = label_to_var[config_choice]

        ss["var_refine"] = rec_cfg["refine"]
        ss["var_extra_desc"] = rec_cfg["extra_desc"]

        cards_ids_cfg = rec_cfg["card_ids_list"]
        for idx in range(4):
            slot_key = f"var_card_slot_{idx+1}"
            if idx < len(cards_ids_cfg):
                cid = cards_ids_cfg[idx]
                label = f"{card_id_to_name.get(cid, str(cid))} ({cid})"
            else:
                label = "(vazio)"
            ss[slot_key] = label

    # 2) Campos de edição (refino + extras)
    var_col_ref, var_col_extra = st.columns([1, 3])

    with var_col_ref:
        refine_val = st.number_input(
            "Refino",
            min_value=0,
            max_value=20,
            step=1,
            key="var_refine",
            disabled=is_existing_config,
        )

    refine_val = ss.get("var_refine", 0)



    with var_col_extra:
        extra_desc = st.text_input(
            "Encantos / Observações",
            key="var_extra_desc",
            placeholder="Opcional (ex: encantos, observações)",
            disabled=is_existing_config,
        )

    # 3) Cartas (até 4 slots)
    st.markdown("**Cartas (até 4 slots)**")
    card_slot_cols = st.columns(4)

    card_options = ["(vazio)"] + [f"{c['name']} ({c['id']})" for c in cards_list]

    card_slot_choices: list[str] = []
    for idx, col in enumerate(card_slot_cols, start=1):
        with col:
            choice = st.selectbox(
                f"Slot {idx}",
                options=card_options,
                key=f"var_card_slot_{idx}",
                disabled=is_existing_config,
            )
            card_slot_choices.append(choice)

    # Monta lista de IDs de cartas a partir dos slots
    card_ids_current: list[int] = []
    for choice in card_slot_choices:
        if choice and choice != "(vazio)":
            try:
                cid_str = choice.split("(")[-1].rstrip(")")
                card_ids_current.append(int(cid_str))
            except ValueError:
                pass

    cards_for_current: list[int] | None = card_ids_current if card_ids_current else None

    # variation_key e display_name atuais
    current_variation_key = build_variation_key(
        refine_val,
        cards_for_current,
        extra_desc,
    )
    current_display_name = build_display_name(
        item_name=item_name,
        refine=refine_val,
        card_ids=cards_for_current,
        extra_desc=extra_desc,
        card_id_to_name=card_id_to_name,
    )

    st.markdown("---")

    # ------------------------------
    #  Card de registro diário
    # ------------------------------
    st.markdown(
        """
        <div class="card">
          <div class="section-title">
            <span class="icon">📝</span>
            <span>Registrar preço diário</span>
          </div>
          <div class="section-subtitle">
            Informe a data e o preço para registrar mais um ponto no histórico.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Limpa input se precisou ou mudou de item
    if ss["clear_price"]:
        ss["price_value"] = ""
        ss["clear_price"] = False

    if item_id != ss["last_item_id"]:
        ss["price_value"] = ""
        ss["last_item_id"] = item_id

    # Flash message
    if ss["flash_message"]:
        level = ss.get("flash_type", "success")
        msg = ss["flash_message"]
        if level == "success":
            st.success(msg)
        elif level == "info":
            st.info(msg)
        elif level == "warning":
            st.warning(msg)
        else:
            st.write(msg)
        ss["flash_message"] = ""
        ss["flash_type"] = "success"

    # Formulário de registro (Data / Preço)
    with st.form(key="price_form"):
        form_col_date, form_col_price, form_col_btn = st.columns([2, 2, 1])

        with form_col_date:
            sel_date = st.date_input(
                "Data",
                value=date.today(),
                key="price_date",
            )

        with form_col_price:
            price_str = st.text_input(
                "Preço (zeny)",
                key="price_value",
                placeholder="Ex: 650.000 ou 600000",
            )

        with form_col_btn:
            st.markdown("<div style='height: 1.8rem'></div>", unsafe_allow_html=True)
            save_clicked = st.form_submit_button("Salvar", use_container_width=True)

    # Clique no salvar → decide entre INSERT ou fluxo de confirmação
    if save_clicked and not ss.get("is_saving", False):
        ss["is_saving"] = True
        try:
            if not price_str.strip():
                st.warning("Informe um preço.")
            else:
                variation_key = current_variation_key

                normalized = price_str.replace(".", "").replace(",", "")
                try:
                    price_val = int(normalized)

                    if price_val <= 0:
                        st.warning("Informe um preço maior que zero.")
                        return

                    if sel_date > date.today():
                        st.warning("Não é permitido registrar preço em data futura.")
                        return

                    date_str = sel_date.isoformat()

                    # verifica se já existe preço PARA ESSA MESMA VARIAÇÃO
                    existing_price = get_existing_price(
                        item_id,
                        date_str,
                        variation_key,
                    )

                    if existing_price is None:
                        # INSERT NOVO PREÇO
                        insert_price(
                            item_id=item_id,
                            date_str=date_str,
                            price_zeny=price_val,
                            refine=int(refine_val),
                            card_ids=cards_for_current,
                            extra_desc=extra_desc or None,
                            variation_key=variation_key,
                        )

                        get_all_prices_cached.clear()
                        get_global_summary_cached.clear()
                        get_price_history_cached.clear()

                        # Marca para resetar variação na próxima execução
                        ss["reset_variation_fields"] = True
                        ss["clear_price"] = True
                        ss["flash_message"] = "Preço salvo com sucesso!"
                        ss["flash_type"] = "success"
                        ss["pending_update"] = None
                        ss["is_saving"] = False

                        st.rerun()

                    else:
                        # Já existe preço nessa data PARA ESSA MESMA VARIAÇÃO
                        variation_desc = describe_variation(
                            refine_val,
                            cards_for_current,
                            extra_desc,
                            card_id_to_name,
                        )
                        card_ids_str = (
                            ",".join(map(str, cards_for_current))
                            if cards_for_current
                            else None
                        )

                        ss["pending_update"] = {
                            "item_id": item_id,
                            "item_name": item_name,
                            "date_str": date_str,
                            "existing_price": existing_price,
                            "new_price": price_val,
                            "variation_desc": variation_desc,
                            "variation_key": variation_key,
                            "refine": int(refine_val),
                            "card_ids_str": card_ids_str,
                            "extra_desc": extra_desc or None,
                        }
                        st.warning(
                            "Já existe um preço cadastrado para este item nesta data "
                            "nessa mesma configuração. "
                            "Confira abaixo antes de confirmar a atualização."
                        )
                except ValueError:
                    st.warning(
                        "Preço inválido. Use apenas números "
                        "(ex: 650000, 650.000 ou 650,000)."
                    )
        finally:
            ss["is_saving"] = False

    pending = ss.get("pending_update")
    if pending is not None:
        variation_desc = pending.get("variation_desc", "Configuração padrão")
        st.info(
            f"Para **{pending['item_name']}** em **{pending['date_str']}** "
            f"na variação **{variation_desc}**:\n\n"
            f"- Preço atual: **{fmt_zeny(pending['existing_price'])} zeny**\n"
            f"- Novo preço: **{fmt_zeny(pending['new_price'])} zeny**"
        )

        col_confirm, col_cancel = st.columns([1, 1])

        if is_admin():
            col_confirm.button(
                "✅ Atualizar preço do dia",
                key="btn_confirm_update",
                use_container_width=True,
                on_click=lambda: ss.update(price_action="confirm_update"),
            )
        else:
            col_confirm.button(
                "♻️ Enviar solicitação para admin",
                key="btn_request_change",
                use_container_width=True,
                on_click=lambda: ss.update(price_action="confirm_update"),
            )

        col_cancel.button(
            "❌ Cancelar atualização",
            key="btn_cancel_update",
            use_container_width=True,
            on_click=lambda: ss.update(price_action="cancel_update"),
        )

    st.markdown("---")

    # ======================================================
    #  KPIs e escolha de variação para análise
    # ======================================================
    analysis_variation_key = current_variation_key
    analysis_display_name = current_display_name

    if existing_variations:
        st.markdown("**Variação para análise**")
        labels_analysis = [v["display_name"] for v in existing_variations]
        label_to_var_analysis = {v["display_name"]: v for v in existing_variations}

        # chave de estado do selectbox de análise (uma por item)
        analysis_key = f"analysis_variation_select_{item_id}"

        # 🔄 Sincroniza automaticamente a variação de análise
        # com a variação escolhida em "Configuração base para registrar"
        if current_variation_key:
            matched_label = None
            for v in existing_variations:
                if v["variation_key"] == current_variation_key:
                    matched_label = v["display_name"]
                    break

            if matched_label is not None:
                if st.session_state.get(analysis_key) != matched_label:
                    st.session_state[analysis_key] = matched_label

        selected_label_analysis = st.selectbox(
            "",
            options=labels_analysis,
            key=analysis_key,
            label_visibility="collapsed",
        )

        rec_analysis = label_to_var_analysis[selected_label_analysis]
        analysis_variation_key = rec_analysis["variation_key"]
        analysis_display_name = rec_analysis["display_name"]

    # Histórico já filtrado pela variação em análise
    hist_local_raw = get_price_history_cached(item_id, analysis_variation_key)
    if not hist_local_raw.empty:
        hist_local = hist_local_raw.copy()
        hist_local["date"] = pd.to_datetime(hist_local["date"])
        hist_local = hist_local.sort_values("date")
    else:
        hist_local = pd.DataFrame()

    df_sum_global = get_global_summary_cached()
    kpi_cols = st.columns(4)

    last_price = mean_5 = var_pct = None
    status = "-"

    if not df_sum_global.empty:
        item_summary = df_sum_global[df_sum_global["Item"] == analysis_display_name]
        if not item_summary.empty:
            row = item_summary.iloc[0]
            try:
                last_price = float(row["Último preço (zeny)"])
            except Exception:
                last_price = None

            try:
                mean_5 = float(row["Média últimos 5"])
            except Exception:
                mean_5 = None

            try:
                var_pct = float(row["Variação % vs média 5"]) * 100.0
            except Exception:
                var_pct = None

            status = str(row.get("Status", "-"))

    labels = [
        "Último preço (zeny)",
        "Média últimos 5 dias",
        "Variação vs média 5",
        "Status",
    ]
    values = [
        fmt_zeny(last_price),
        fmt_zeny(mean_5),
        fmt_pct(var_pct) if var_pct is not None else "-",
        status or "-",
    ]

    for col, label, value in zip(kpi_cols, labels, values):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin-top: 0.75rem;'></div>", unsafe_allow_html=True)

    # ======================================================
    #  Painel de insights do item
    # ======================================================
    st.markdown(
        """
        <div class="section-title">
          <span class="icon">🧠</span>
          <span>Painel de insights do item</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if hist_local.empty:
        st.info("Ainda não há dados suficientes para gerar insights para esta variação.")
    else:
        hist_last5 = hist_local.tail(5)
        prices_5 = hist_last5["price_zeny"]

        min_5 = float(prices_5.min())
        max_5 = float(prices_5.max())
        media_5 = float(prices_5.mean())

        osc_pct = 0.0
        if media_5 > 0:
            osc_pct = (max_5 - min_5) / media_5 * 100

        std_5 = float(prices_5.std())
        preco_atual = float(prices_5.iloc[-1])

        if media_5 > 0:
            diff_media_pct = (preco_atual - media_5) / media_5 * 100
        else:
            diff_media_pct = 0.0

        if diff_media_pct > 3:
            msg_text = (
                "acima da média recente (tendência de alta / possível momento de venda)."
            )
        elif diff_media_pct < -3:
            msg_text = (
                "abaixo da média recente (tendência de baixa / possível oportunidade de compra)."
            )
        else:
            msg_text = "próximo da média recente (região neutra)."

        verdict_text = (
            f"Preço atual está {diff_media_pct:+.1f}% em relação à média "
            f"dos últimos 5 registros — {msg_text}"
        )

        col_left, col_right = st.columns([1.15, 1.1])

        with col_left:
            col_a, col_b = st.columns(2)

            with col_a:
                st.markdown(
                    "<p style='margin-bottom:0.15rem'><strong>Mínimo (últimos 5)</strong></p>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<h3 style='margin-top:0;margin-bottom:0.6rem'>{fmt_zeny(min_5)}</h3>",
                    unsafe_allow_html=True,
                )

                st.markdown(
                    "<p style='margin-bottom:0.15rem'><strong>Máximo (últimos 5)</strong></p>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<h3 style='margin-top:0'>{fmt_zeny(max_5)}</h3>",
                    unsafe_allow_html=True,
                )

            with col_b:
                st.markdown(
                    "<p style='margin-bottom:0.15rem'><strong>Oscilação (últimos 5)</strong></p>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<h3 style='margin-top:0;margin-bottom:0.6rem'>{osc_pct:.1f}%</h3>",
                    unsafe_allow_html=True,
                )

                st.markdown(
                    "<p style='margin-bottom:0.15rem'><strong>Desvio padrão (5)</strong></p>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<h3 style='margin-top:0'>{fmt_zeny(std_5)}</h3>",
                    unsafe_allow_html=True,
                )

        with col_right:
            st.markdown("**Tendência (últimos 5 registros)**")

            y_min = float(min_5) * 0.98
            y_max = float(max_5) * 1.02

            spark_data = hist_last5.copy()
            spark_data["date_str"] = spark_data["date"].dt.strftime("%Y-%m-%d")

            spark = (
                alt.Chart(spark_data)
                .mark_line(point=True)
                .encode(
                    x=alt.X(
                        "date_str:O",
                        axis=alt.Axis(title="", labels=False, ticks=False),
                    ),
                    y=alt.Y(
                        "price_zeny:Q",
                        axis=alt.Axis(title="", labels=False, ticks=False),
                        scale=alt.Scale(domain=[y_min, y_max]),
                    ),
                    tooltip=[
                        alt.Tooltip("date_str:O", title="Data"),
                        alt.Tooltip("price_zeny:Q", title="Preço (zeny)"),
                    ],
                )
                .properties(height=70)
            )

            st.altair_chart(spark, use_container_width=True)

        st.markdown(
            f"""
            <div style="
                margin-top:0.9rem;
                padding:0.75rem 1rem;
                border-radius:0.8rem;
                background:linear-gradient(90deg, #020617, #020617);
                border:1px solid rgba(59,130,246,0.6);
                font-size:0.95rem;">
              <span style="margin-right:0.5rem;">✨</span>
              <strong>Veredito do dia:</strong> {verdict_text}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ======================================================
    #  Histórico de preços (por variação)
    # ======================================================
    st.subheader(f"📈 Histórico de preços – {analysis_display_name}")

    if hist_local.empty:
        st.info("Ainda não há histórico para esta variação.")
    else:
        st.caption("Período do gráfico")
        periodo = st.radio(
            "",
            options=["7 dias", "30 dias", "Tudo"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if periodo == "7 dias":
            min_date = hist_local["date"].max() - timedelta(days=7)
            hist_plot = hist_local[hist_local["date"] >= min_date]
        elif periodo == "30 dias":
            min_date = hist_local["date"].max() - timedelta(days=30)
            hist_plot = hist_local[hist_local["date"] >= min_date]
        else:
            hist_plot = hist_local

        hist_plot = hist_plot.copy()
        hist_plot["date_str"] = hist_plot["date"].dt.date.astype(str)

        area = (
            alt.Chart(hist_plot)
            .mark_area(opacity=0.3)
            .encode(
                x=alt.X("date_str:O", title="Data", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("price_zeny:Q", title="Preço (zeny)"),
            )
            .properties(height=340)
        )

        line = (
            alt.Chart(hist_plot)
            .mark_line(point=True)
            .encode(
                x=alt.X("date_str:O", axis=alt.Axis(labelAngle=0)),
                y="price_zeny:Q",
                tooltip=[
                    alt.Tooltip("date_str:O", title="Data"),
                    alt.Tooltip("price_zeny:Q", title="Preço (zeny)"),
                ],
            )
        )

        chart_key = (
            f"hist_chart_{item_id}_{analysis_variation_key}_{periodo}_{len(hist_plot)}"
        )
        st.altair_chart(area + line, use_container_width=True, key=chart_key)

        with st.expander("📜 Ver tabela completa de histórico desta variação"):
            hist_display = hist_local.copy()
            hist_display["Data"] = hist_display["date"].dt.date.astype(str)
            hist_display["Preço (zeny)"] = hist_display["price_zeny"].apply(fmt_zeny)
            hist_display["Criado em"] = hist_display["created_at"]

            hist_display = hist_display[["Data", "Preço (zeny)", "Criado em"]]

            st.dataframe(
                hist_display.sort_values("Data", ascending=False).reset_index(
                    drop=True
                ),
                use_container_width=True,
                hide_index=True,
                height=400,
            )

    st.markdown("---")

    # ======================================================
    #  Top 5 maiores altas / quedas
    # ======================================================
    st.markdown(
        """
        <div class="section-title">
          <span class="icon">🔥</span>
          <span>Top 5 maiores altas / quedas</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    df_sum_all = get_global_summary_cached()
    if df_sum_all.empty:
        st.info("Ainda não há dados suficientes para montar o ranking.")
    else:
        top_gain = (
            df_sum_all.sort_values("Variação % vs média 5", ascending=False)
            .head(5)
            .copy()
        )
        top_loss = (
            df_sum_all.sort_values("Variação % vs média 5", ascending=True)
            .head(5)
            .copy()
        )

        def prepare_top(df_top: pd.DataFrame) -> pd.DataFrame:
            df = df_top.copy()
            df["Último preço (zeny)"] = df["Último preço (zeny)"].apply(fmt_zeny)
            df["Média últimos 5"] = df["Média últimos 5"].apply(fmt_zeny)
            df["Variação % vs média 5"] = df["Variação % vs média 5"].apply(
                lambda x: fmt_pct(x * 100.0 if abs(x) < 1.0 else x)
            )
            df = df.rename(
                columns={
                    "Último preço (zeny)": "Últ. preço",
                    "Média últimos 5": "Média 5d",
                    "Variação % vs média 5": "Var % vs 5d",
                }
            )

            return df[
                [
                    "Item",
                    "Última data",
                    "Últ. preço",
                    "Média 5d",
                    "Var % vs 5d",
                    "Status",
                ]
            ]

        tab_up, tab_down = st.tabs(["📈 Maiores altas", "📉 Maiores quedas"])

        with tab_up:
            df_up = prepare_top(top_gain)
            st.dataframe(
                style_market_table(df_up),
                use_container_width=True,
                hide_index=True,
                height=230,
            )

        with tab_down:
            df_down = prepare_top(top_loss)
            st.dataframe(
                style_market_table(df_down),
                use_container_width=True,
                hide_index=True,
                height=230,
            )

    st.markdown("---")

    # ======================================================
    #  Resumo geral do mercado
    # ======================================================
    st.subheader("🌐 Resumo geral do mercado")

    df_sum = get_global_summary_cached()
    if df_sum.empty:
        st.info("Ainda não há dados suficientes para montar o resumo.")
        return

    df_display = df_sum.copy()
    df_display["Último preço (zeny)"] = df_display["Último preço (zeny)"].apply(
        fmt_zeny
    )
    df_display["Média últimos 5"] = df_display["Média últimos 5"].apply(fmt_zeny)
    df_display["Variação % vs média 5"] = df_display["Variação % vs média 5"].apply(
        lambda x: fmt_pct(x * 100.0 if abs(x) < 1.0 else x)
    )

    df_display = df_display.rename(
        columns={
            "Último preço (zeny)": "Últ. preço",
            "Média últimos 5": "Média 5d",
            "Variação % vs média 5": "Var % vs 5d",
        }
    )

    # Garantir coluna Cartas preenchida
    if "Cartas" not in df_display.columns:
        df_display["Cartas"] = "-"

    df_display = df_display[
        [
            "Item",
            "Cartas",
            "Última data",
            "Últ. preço",
            "Média 5d",
            "Var % vs 5d",
            "Status",
        ]
    ]

    st.dataframe(
        style_market_table(df_display),
        use_container_width=True,
        hide_index=True,
        height=450,
        column_config={
            "Item": st.column_config.TextColumn(
                "Item",
                width="large",
            ),
            "Cartas": st.column_config.TextColumn(
                "Cartas",
                width="medium",
            ),
            "Última data": st.column_config.TextColumn(
                "Última data",
                width="small",
            ),
            "Últ. preço": st.column_config.TextColumn(
                "Últ. preço",
                width="small",
            ),
            "Média 5d": st.column_config.TextColumn(
                "Média 5d",
                width="small",
            ),
            "Var % vs 5d": st.column_config.TextColumn(
                "Var % vs 5d",
                width="small",
            ),
            "Status": st.column_config.TextColumn(
                "Status",
                width="small",
            ),
        },
    )


render()
