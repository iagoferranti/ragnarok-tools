# pages/03_🗑️_Admin_Excluir_Precos.py
from datetime import date

import pandas as pd
import streamlit as st
import unicodedata

from ui.theme import apply_theme
from db.database import (
    get_items_df,
    get_all_prices_df,
    get_price_history_df,
    delete_price,
    log_price_action,
)

# ============================================
#  Tema / layout base
# ============================================
apply_theme("Admin – Excluir registros de preço", page_icon="🗑️")


# --------------------------------------------
# Helpers básicos
# --------------------------------------------
def normalize_text(txt: str) -> str:
    if not isinstance(txt, str):
        return ""
    return (
        unicodedata.normalize("NFKD", txt)
        .encode("ASCII", "ignore")
        .decode("utf-8")
        .lower()
    )


def fmt_zeny(v: float | int | None) -> str:
    if v is None or pd.isna(v):
        return "-"
    return f"{float(v):,.0f}".replace(",", ".")


def build_display_name(
    item_name: str,
    refine: int | None,
    card_ids,
    extra_desc: str | None,
    card_id_to_name: dict[int, str],
) -> str:
    parts: list[str] = []

    if refine is not None:
        try:
            r = int(refine)
        except Exception:
            r = None
        if r and r > 0:
            parts.append(f"+{r}")

    if isinstance(extra_desc, str) and extra_desc.strip():
        parts.append(extra_desc.strip())

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
                    pass

    if ids_list:
        labels = [card_id_to_name.get(cid, str(cid)) for cid in ids_list]
        parts.append("Cartas: " + ", ".join(labels))

    if parts:
        return f"{item_name} — " + " | ".join(parts)
    else:
        return item_name


# ==========================================================
#  Página principal
# ==========================================================
def render():
    ss = st.session_state

    if not ss.get("auth_ok", False):
        st.warning("Você não está autenticado. Faça login para continuar.")
        st.stop()

    user_email = ss.get("user_email") or ss.get("username") or "desconhecido"

    st.title("🗑️ Admin – Excluir registros de preço")

    st.markdown(
        """
        Esta página permite **remover registros de preço** cadastrados por engano.
        A exclusão é permanente, mas fica registrada na auditoria.
        """
    )

    # -------------------------------------------------
    # Carrega itens e preços
    # -------------------------------------------------
    items_df = get_items_df()
    df_prices_all = get_all_prices_df()

    if df_prices_all.empty:
        st.info("Ainda não há registros de preço cadastrados para excluir.")
        return

    item_ids_with_prices = sorted(df_prices_all["item_id"].unique())
    items_df = items_df[items_df["id"].isin(item_ids_with_prices)]

    if items_df.empty:
        st.info("Nenhum item com preços encontrados.")
        return

    # Lista de cartas
    items_df_sorted = items_df.sort_values("id")
    cards_df = items_df_sorted[
        items_df_sorted["name"].str.contains("carta", case=False, na=False)
    ].copy()
    card_id_to_name = dict(zip(cards_df["id"], cards_df["name"]))

    # =================================================
    # 1️⃣ Selecionar item
    # =================================================
    st.markdown("### 1️⃣ Escolha o item")

    options_items = (
        items_df[["id", "name"]]
        .drop_duplicates()
        .sort_values("name")
        .to_dict(orient="records")
    )

    item_selected = st.selectbox(
        "",
        options=options_items,
        format_func=lambda it: f"{it['name']} ({it['id']})",
        key="delete_item_select",
        label_visibility="collapsed",
    )

    if item_selected is None:
        st.stop()

    item_id = int(item_selected["id"])
    item_name = item_selected["name"]

    df_item = df_prices_all[df_prices_all["item_id"] == item_id].copy()
    if df_item.empty:
        st.info("Este item não possui registros.")
        st.stop()

    # =================================================
    # 2️⃣ Selecionar variação
    # =================================================
    st.markdown("### 2️⃣ Escolha a variação")

    if "variation_key" not in df_item.columns:
        df_item["variation_key"] = None

    df_item["date_parsed"] = pd.to_datetime(df_item["date"])
    last_per_var = (
        df_item.sort_values("date_parsed")
        .groupby("variation_key", dropna=False, as_index=False)
        .last()
    )

    variation_records = []
    for _, row in last_per_var.iterrows():
        vk = row["variation_key"]
        refine_val = row.get("refine")
        extra_desc_val = row.get("extra_desc")
        card_ids_raw = row.get("card_ids")

        card_ids_list = []
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

        n_reg = len(df_item[df_item["variation_key"].fillna("") == (vk or "")])

        variation_records.append(
            {
                "label": f"{display_name}  —  {n_reg} registro(s)",
                "variation_key": vk,
                "refine": refine_val,
                "extra_desc": extra_desc_val,
                "card_ids_list": card_ids_list,
                "display_name": display_name,
            }
        )

    var_choice_label = st.selectbox(
        "",
        options=[v["label"] for v in variation_records],
        key="delete_variation_select",
        label_visibility="collapsed",
    )

    var_selected = next(v for v in variation_records if v["label"] == var_choice_label)
    variation_key = var_selected["variation_key"]
    refine_val = var_selected["refine"]
    extra_desc_val = var_selected["extra_desc"]
    card_ids_list = var_selected["card_ids_list"]

    df_hist = (
        df_item[df_item["variation_key"].fillna("") == (variation_key or "")]
        .copy()
    )

    df_hist["date_parsed"] = pd.to_datetime(df_hist["date"])
    df_hist = df_hist.sort_values("date_parsed")

    if df_hist.empty:
        st.info("Nenhum registro nesta variação.")
        st.stop()

    # =================================================
    # 3️⃣ Seleção do registro a excluir
    # =================================================
    st.markdown("### 3️⃣ Escolha o registro a excluir")

    df_hist["date_str"] = df_hist["date_parsed"].dt.date.astype(str)
    df_hist["price_fmt"] = df_hist["price_zeny"].apply(fmt_zeny)

    # 🔥 Correção do erro — created_at pode não existir
    if "created_at" in df_hist.columns:
        df_hist["created_fmt"] = (
            pd.to_datetime(df_hist["created_at"])
            .dt.strftime("%Y-%m-%d %H:%M")
        )
    else:
        df_hist["created_fmt"] = "(sem data)"

    labels_rows = []
    for _, row in df_hist.iterrows():
        lbl = (
            f"{row['date_str']} — {row['price_fmt']} zeny "
            f"(criado em {row['created_fmt']})"
        )
        labels_rows.append(lbl)

    selected_row_label = st.radio(
        "Selecione o registro para remoção:",
        options=labels_rows,
        key="delete_row_radio",
    )

    idx_selected = labels_rows.index(selected_row_label)
    row_sel = df_hist.iloc[idx_selected]

    date_sel = row_sel["date_parsed"].date()
    price_sel = int(row_sel["price_zeny"])

    # =================================================
    # 4️⃣ Confirmação de exclusão
    # =================================================
    st.markdown("---")
    st.markdown("### 4️⃣ Confirmar exclusão")

    st.warning(
        f"""
        Você está prestes a **excluir definitivamente**:

        - Item: **{item_name}**
        - Variação: **{var_selected['display_name']}**
        - Data: **{date_sel}**
        - Preço: **{fmt_zeny(price_sel)} zeny**

        Essa ação não poderá ser desfeita.
        """
    )

    delete_clicked = st.button(
        "🗑️ Excluir registro",
        type="primary",
        use_container_width=True,
    )

    if delete_clicked:
        date_str = date_sel.isoformat()

        try:
            delete_price(item_id=item_id, date_str=date_str, variation_key=variation_key)
        except Exception as e:
            st.error("Erro ao excluir o registro.")
            st.stop()

        card_ids_str = ",".join(map(str, card_ids_list)) if card_ids_list else None

        try:
            log_price_action(
                item_id=item_id,
                date_str=date_str,
                action_type="delete",
                actor_email=user_email,
                actor_role="admin",
                old_price=price_sel,
                new_price=None,
                refine=int(refine_val) if refine_val is not None else None,
                card_ids=card_ids_str,
                extra_desc=extra_desc_val,
                variation_key=variation_key or "",
            )
        except Exception as e:
            print(f"[WARN] Falha ao gravar log de exclusão: {e}")

        st.success(
            f"Registro de **{item_name}** em **{date_str}** excluído com sucesso."
        )
        st.rerun()


if __name__ == "__main__":
    render()
