# pages/02_🛠️_Admin_Solicitações.py
import streamlit as st

from ui.theme import apply_theme
from db.database import (
    get_pending_requests,
    approve_price_request,
    reject_price_request,
)

# ---------------------------------------
# Mesmo helper de admin usado no Monitor
# ---------------------------------------
def is_admin() -> bool:
    username = st.session_state.get("username", "")
    admins = st.secrets["roles"]["admins"]
    return username in admins


apply_theme("Admin – Solicitações de Preço", page_icon="🛠️")


def render():
    st.title("🛠️ Painel de Admin – Solicitações de preço")

    ss = st.session_state

    # Autenticação básica
    if not ss.get("auth_ok", False):
        st.error("Você não está autenticado. Faça login para continuar.")
        st.stop()

    if not is_admin():
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()

    user_display = ss.get("user_email") or ss.get("username") or "admin"

    # Badge de admin logado
    st.markdown(
        f"""
        <div style="
            margin-bottom: 0.75rem;
            padding: 0.4rem 0.75rem;
            border-radius: 0.6rem;
            font-size: 0.9rem;
            background-color: rgba(15,23,42,0.85);
            border: 1px solid rgba(148,163,184,0.4);
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;">
            <span>👑</span>
            <span>Admin logado como <strong>{user_display}</strong></span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Carrega solicitações pendentes
    df_req = get_pending_requests()

    if df_req.empty:
        st.success("Nenhuma solicitação pendente no momento. 🎉")
        return

    st.subheader("Solicitações pendentes")

    # Ordena por data de criação (só por garantia)
    df_req = df_req.sort_values("created_at", ascending=True)

    # Visão geral (tabela compacta)
    with st.expander("📋 Ver tabela geral", expanded=False):
        df_display = df_req.copy()
        df_display["Data"] = df_display["date"].astype(str)
        df_display["Preço antigo"] = df_display["old_price"]
        df_display["Preço novo"] = df_display["new_price"]
        df_display["Criado em"] = df_display["created_at"].astype(str)
        df_display["Criado por"] = df_display["created_by"]

        st.dataframe(
            df_display[
                [
                    "id",
                    "item_name",
                    "Data",
                    "Preço antigo",
                    "Preço novo",
                    "Criado por",
                    "Criado em",
                ]
            ].reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")
    st.markdown("### Analisar uma por uma")

    # Loop em cada solicitação com blocos individuais
    for _, row in df_req.iterrows():
        req_id = int(row["id"])
        item_name = row["item_name"]
        date_str = str(row["date"])
        old_price = row["old_price"]
        new_price = row["new_price"]
        created_by = row["created_by"]
        created_at = row["created_at"]

        with st.container(border=True):
            # Cabeçalho do card
            st.markdown(
                f"**#{req_id} – {item_name} ({date_str})** · "
                f"criado por **{created_by}** em `{created_at}`"
            )

            # Resumo dos preços
            if old_price is None:
                old_txt = "N/A"
            else:
                old_txt = f"{int(old_price):,}".replace(",", ".")

            new_txt = f"{int(new_price):,}".replace(",", ".")

            st.markdown(
                f"- Preço atual registrado: **{old_txt} zeny**  \n"
                f"- Preço solicitado: **{new_txt} zeny**"
            )

            # Campo de comentário ocupa a largura inteira
            comment_key = f"comment_{req_id}"
            comment = st.text_input(
                f"Comentário (opcional) – #{req_id}",
                key=comment_key,
                placeholder="Motivo da rejeição (opcional)...",
            )

            # Linha de botões alinhados
            col_approve, col_reject = st.columns([1, 1])

            with col_approve:
                approve_clicked = st.button(
                    f"✅ Aprovar #{req_id}",
                    key=f"approve_{req_id}",
                    use_container_width=True,
                )

            with col_reject:
                reject_clicked = st.button(
                    f"❌ Rejeitar #{req_id}",
                    key=f"reject_{req_id}",
                    use_container_width=True,
                )

            # Trata clique em Aprovar
            if approve_clicked:
                try:
                    reviewer_email = user_display
                    approve_price_request(req_id, reviewer_email)
                    # limpa cache para recarregar lista sem essa solicitação
                    get_pending_requests.clear()
                    st.success(f"Solicitação #{req_id} aprovada com sucesso.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao aprovar solicitação #{req_id}: {e}")

            # Trata clique em Rejeitar
            if reject_clicked:
                try:
                    reviewer_email = user_display
                    reject_price_request(req_id, reviewer_email, comment or None)
                    get_pending_requests.clear()
                    st.info(f"Solicitação #{req_id} rejeitada.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao rejeitar solicitação #{req_id}: {e}")

            st.markdown("---")


render()
