# pages/01_📈_Monitor_de_Mercado.py
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

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
apply_theme("Monitor de Mercado – Ragnarok LATAM", page_icon="📈")

def is_admin() -> bool:
    """Retorna True se o usuário logado estiver na lista de admins."""
    username = st.session_state.get("username", "")
    admins = st.secrets["roles"]["admins"]
    return username in admins


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
def get_price_history_cached(item_id: int) -> pd.DataFrame:
    return get_price_history_df(item_id)


@st.cache_data(ttl=30, show_spinner=False)
def get_global_summary_cached() -> pd.DataFrame:
    df_prices_all = get_all_prices_cached()
    if df_prices_all.empty:
        return pd.DataFrame()
    df_summary_input = df_prices_all.rename(columns={"item_name": "item"})
    return compute_summary(df_summary_input)

# ============================================
#  Helpers
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
    Aplica cores em:
    - Coluna de variação percentual (nome pode ser 'Variação % vs média 5'
      ou 'Var % vs 5d', dependendo da tabela)
    - Status ('Vender' em vermelho)
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
            return "color:#22c55e;"  # verde
        if num < 0:
            return "color:#ef4444;"  # vermelho
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

# ============================================
#  Página principal
# ============================================
def render():
    
    if not st.session_state.get("auth_ok", False):
        st.warning("Você não está autenticado. Faça login para continuar.")
        st.stop()

    st.title("📈 Monitor de Mercado – Ragnarok LATAM")

    ss = st.session_state

    # ---------------------------------------
    # Barra superior: usuário logado + sininho (se admin)
    # ---------------------------------------
    user_display = ss.get("user_email") or ss.get("username") or "desconhecido"

    col_user, col_notif = st.columns([4, 1])

    with col_user:
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
                gap: 0.4rem;
            ">
                <span>👤</span>
                <span>Logado como <strong>{user_display}</strong></span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_notif:
        if is_admin():
            try:
                df_req = get_pending_requests()
                n_pending = len(df_req)
            except Exception as e:
                print(f"[WARN] Falha ao carregar pending_requests: {e}")
                n_pending = 0

            if n_pending > 0:
                label = f"🔔 {n_pending}"
                help_txt = "Ver solicitações de alteração pendentes"
                disabled = False
            else:
                label = "🔔 0"
                help_txt = "Nenhuma solicitação pendente"
                disabled = True

            # 👇 sem callback; navegação feita no if
            notif_clicked = st.button(
                label,
                key="btn_admin_requests",
                help=help_txt,
                disabled=disabled,
            )

            if notif_clicked and not disabled:
                st.switch_page("pages/02_🛠️_Admin_Solicitações.py")
        else:
            st.empty()




    # ------------------------------
    #  Carrega itens e preços (COM CACHE)
    # ------------------------------
    items_df = get_items_cached()
    if items_df.empty:
        st.warning("Nenhum item encontrado. Verifique o arquivo items.json.")
        return

    df_prices_all = get_all_prices_cached()

    item_list = [
        {"id": int(row["id"]), "name": row["name"]}
        for row in items_df.to_dict(orient="records")
    ]

    # Descobre item padrão (último que teve preço registrado)
    selectbox_kwargs: dict = {}
    if not df_prices_all.empty:
        df_tmp = df_prices_all.copy()
        df_tmp["date_parsed"] = pd.to_datetime(df_tmp["date"])
        last_row = df_tmp.sort_values("date_parsed", ascending=False).iloc[0]
        default_item_id = int(last_row["item_id"])

        default_index = 0
        for i, it in enumerate(item_list):
            if it["id"] == default_item_id:
                default_index = i
                break
        selectbox_kwargs["index"] = default_index
    else:
        selectbox_kwargs["index"] = None
        selectbox_kwargs["placeholder"] = "Selecione um item..."

    # ------------------------------
    #  Estado global simples
    # ------------------------------
    if "price_input" not in ss:
        ss["price_input"] = ""
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
        ss["price_action"] = None  # "confirm_update" | "cancel_update" | None

    # ------------------------------
    #  Processa ações pendentes (confirmar/cancelar update)
    #  -> isso roda ANTES de desenhar os botões, então não tem duplicação
    # ------------------------------
    
    # ======================================================
    #  Ação pós-clique (confirmar / cancelar atualização)
    # ======================================================
    action = ss.get("price_action")

    if action == "confirm_update":
        pending = ss.get("pending_update")
        if pending is not None:
            admin_flag = is_admin()  # usa a função que olha secrets
            user_id = (
                ss.get("user_email")   # se tiver email, usa
                or ss.get("username")  # senão usa o username
                or "desconhecido"
            )

            if admin_flag:
                # 👑 ADMIN: atualiza direto
                update_price(
                    pending["item_id"],
                    pending["date_str"],
                    pending["new_price"],
                )

                # Log técnico de alteração (tabela macro)
                try:
                    log_price_change(
                        item_id=pending["item_id"],
                        date_str=pending["date_str"],
                        old_price_zeny=pending["existing_price"],
                        new_price_zeny=pending["new_price"],
                        changed_by=user_id,
                        source="DIRECT_ADMIN",
                    )
                except Exception as e:
                    print(f"[WARN] Falha ao logar alteração de preço: {e}")

                # 🔒 Log de auditoria fina (price_audit_log)
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
                    )
                except Exception as e:
                    print(f"[WARN] Falha ao logar ação de update em price_audit_log: {e}")


                # limpa caches relacionados
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
                # 🙋 Usuário normal: cria SOLICITAÇÃO para admin
                try:
                    print("\n===== DEBUG: Enviando solicitação =====")
                    print(f"item_id: {pending['item_id']}")
                    print(f"date: {pending['date_str']}")
                    print(f"old_price: {pending['existing_price']}")
                    print(f"new_price: {pending['new_price']}")
                    print(f"user: {user_id}")
                    print("========================================\n")

                    # chamada POSICIONAL, sem keywords
                    req_id = create_price_change_request(
                        pending["item_id"],          # item_id
                        pending["date_str"],         # date_str
                        pending["existing_price"],   # old_price_zeny
                        pending["new_price"],        # new_price_zeny
                        user_id,                     # requested_by
                        None,                        # reason
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
                    ss["flash_type"] = "warning"

                ss["pending_update"] = None
                ss["price_action"] = None
                st.rerun()

    elif action == "cancel_update":
        # CANCELAR: só limpa o estado e mostra mensagem
        ss["pending_update"] = None
        ss["flash_message"] = (
            "Atualização cancelada. Nenhuma alteração foi feita."
        )
        ss["flash_type"] = "info"
        ss["price_action"] = None
        st.rerun()

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
            Selecione o item e registre o preço do dia para alimentar o histórico.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Linha 1 – seleção do item (fora do form)
    col_item, _, _, _ = st.columns([3, 2, 2, 1])

    with col_item:
        item_selected = st.selectbox(
            "Item",
            options=item_list,
            format_func=lambda it: f"{it['name']} ({it['id']})",
            **selectbox_kwargs,
        )

    if item_selected is None:
        st.info("Escolha um item para começar.")
        return

    item_id = item_selected["id"]
    item_name = item_selected["name"]

    # Limpa input se precisou ou mudou de item
    if ss["clear_price"]:
        ss["price_input"] = ""
        ss["clear_price"] = False

    if item_id != ss["last_item_id"]:
        ss["price_input"] = ""
        ss["last_item_id"] = item_id

    # Flash message (sucesso / info após insert/update/cancel)
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

    # Linha 2 – formulário (Enter dispara o submit)
    with st.form(key=f"form_registro_preco_{item_id}"):
        form_col_date, form_col_price, form_col_btn = st.columns([2, 2, 1])

        with form_col_date:
            sel_date = st.date_input(
                "Data",
                value=date.today(),
                key=f"date_input_{item_id}",
            )

        with form_col_price:
            price_str = st.text_input(
                "Preço (zeny)",
                key="price_input",
                placeholder="Ex: 650.000 ou 600000",
            )

        with form_col_btn:
            st.write("")
            save_clicked = st.form_submit_button("Salvar", use_container_width=True)

    # Clique no salvar → decide entre INSERT ou fluxo de confirmação
    if save_clicked:
        if not price_str.strip():
            st.warning("Informe um preço.")
        else:
            normalized = price_str.replace(".", "").replace(",", "")
            try:
                price_val = int(normalized)

                if price_val <= 0:
                    st.warning("Informe um preço maior que zero.")
                    return

                # Bloqueia data futura antes de consultar o banco
                if sel_date > date.today():
                    st.warning("Não é permitido registrar preço em data futura.")
                    return

                date_str = sel_date.isoformat()
                existing_price = get_existing_price(item_id, date_str)

                if existing_price is None:
                    # Não existe registro → insere direto
                    insert_price(item_id, date_str, price_val)

                    get_all_prices_cached.clear()
                    get_global_summary_cached.clear()
                    get_price_history_cached.clear()

                    ss["clear_price"] = True
                    ss["flash_message"] = "Preço salvo com sucesso!"
                    ss["flash_type"] = "success"
                    ss["pending_update"] = None
                    st.rerun()

                else:
                    # Já existe → abre fluxo de atualização
                    ss["pending_update"] = {
                        "item_id": item_id,
                        "item_name": item_name,
                        "date_str": date_str,
                        "existing_price": existing_price,
                        "new_price": price_val,
                    }
                    st.warning(
                        "Já existe um preço cadastrado para este item nesta data. "
                        "Confira abaixo antes de confirmar a atualização."
                    )

            except ValueError:
                st.warning(
                    "Preço inválido. Use apenas números (ex: 650000, 650.000 ou 650,000)."
                )

    pending = ss.get("pending_update")

    if pending is not None:
        st.info(
            f"Para **{pending['item_name']}** em **{pending['date_str']}**:\n\n"
            f"- Preço atual: **{fmt_zeny(pending['existing_price'])} zeny**\n"
            f"- Novo preço: **{fmt_zeny(pending['new_price'])} zeny**"
        )

        col_confirm, col_cancel = st.columns([1, 1])

        if is_admin():
            # 👑 Admin confirma e aplica direto
            col_confirm.button(
                "✅ Atualizar preço do dia",
                key="btn_confirm_update",
                use_container_width=True,
                on_click=lambda: ss.update(price_action="confirm_update"),
            )
        else:
            # 🙋 Usuário normal: envia solicitação para admin
            col_confirm.button(
                "♻️ Enviar solicitação para admin",
                key="btn_request_change",
                use_container_width=True,
                on_click=lambda: ss.update(price_action="confirm_update"),
            )

        # Todos podem cancelar
        col_cancel.button(
            "❌ Cancelar atualização",
            key="btn_cancel_update",
            use_container_width=True,
            on_click=lambda: ss.update(price_action="cancel_update"),
        )



    st.markdown("---")


    # ======================================================
    #  KPIs do item selecionado
    # ======================================================
    hist_local_raw = get_price_history_cached(item_id)
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
        item_summary = df_sum_global[df_sum_global["Item"] == item_name]
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
        st.info("Ainda não há dados suficientes para gerar insights para este item.")
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
    #  Histórico de preços
    # ======================================================
    st.subheader(f"📈 Histórico de preços – {item_name}")

    if hist_local.empty:
        st.info("Ainda não há histórico para este item.")
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

        st.altair_chart(area + line, use_container_width=True)

        st.subheader("📜 Tabela de histórico")

        hist_display = hist_local.copy()
        hist_display["Data"] = hist_display["date"].dt.date.astype(str)
        hist_display["Preço (zeny)"] = hist_display["price_zeny"].apply(fmt_zeny)
        hist_display["Criado em"] = hist_display["created_at"]

        hist_display = hist_display[["Data", "Preço (zeny)", "Criado em"]]

        st.dataframe(
            hist_display.sort_values("Data", ascending=False).reset_index(drop=True),
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

    df_display = df_display[
        [
            "Item",
            "Última data",
            "Último preço (zeny)",
            "Média últimos 5",
            "Variação % vs média 5",
            "Status",
        ]
    ]

    st.dataframe(
        style_market_table(df_display),
        use_container_width=True,
        hide_index=True,
        height=450,
    )


render()
