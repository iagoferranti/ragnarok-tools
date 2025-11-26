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
)
from services.market import compute_summary

# ============================================
#  Tema / layout base
# ============================================
apply_theme("Monitor de Mercado – Ragnarok LATAM", page_icon="📈")

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
        return ""

    styler = df.style

    # tenta achar a coluna de variação por nome
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
    st.title("📈 Monitor de Mercado – Ragnarok LATAM")

    # ------------------------------
    #  Carrega itens e preços
    # ------------------------------
    items_df = get_items_df()
    if items_df.empty:
        st.warning("Nenhum item encontrado. Verifique o arquivo items.json.")
        return

    df_prices_all = get_all_prices_df()

    # Monta lista para o selectbox
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

    col_item, col_date, col_price, col_btn = st.columns([3, 2, 2, 1])

    with col_item:
        item_selected = st.selectbox(
            "Item",
            options=item_list,
            format_func=lambda it: f"{it['name']} ({it['id']})",
            **selectbox_kwargs,
        )

    # Se ainda não escolheu nada (primeiro uso, sem histórico)
    if item_selected is None:
        st.info("Escolha um item para começar.")
        return

    item_id = item_selected["id"]
    item_name = item_selected["name"]

    # ---- Estado do input de preço ----
    if "price_input" not in st.session_state:
        st.session_state["price_input"] = ""
    if "last_item_id" not in st.session_state:
        st.session_state["last_item_id"] = item_id
    if "clear_price" not in st.session_state:
        st.session_state["clear_price"] = False
    if "flash_message" not in st.session_state:
        st.session_state["flash_message"] = ""

    # Limpeza pós-salvar
    if st.session_state["clear_price"]:
        st.session_state["price_input"] = ""
        st.session_state["clear_price"] = False

    # Se mudou de item, limpa o campo
    if item_id != st.session_state["last_item_id"]:
        st.session_state["price_input"] = ""
        st.session_state["last_item_id"] = item_id

    # Mensagem de sucesso, se houver
    if st.session_state["flash_message"]:
        st.success(st.session_state["flash_message"])
        st.session_state["flash_message"] = ""

    with col_date:
        sel_date = st.date_input("Data", value=date.today())

    with col_price:
        price_str = st.text_input(
            "Preço (zeny)",
            key="price_input",
            placeholder="Ex: 650.000",
        )

    with col_btn:
        # empurra o botão para alinhar com os campos
        st.markdown("<div style='height: 1.7em;'></div>", unsafe_allow_html=True)
        save_clicked = st.button("Salvar", use_container_width=True)

    if save_clicked:
        if not price_str.strip():
            st.warning("Informe um preço.")
        else:
            normalized = price_str.replace(".", "").replace(",", "")
            try:
                price_val = int(normalized)
                if price_val <= 0:
                    st.warning("Informe um preço maior que zero.")
                else:
                    insert_price(item_id, sel_date.isoformat(), price_val)
                    st.session_state["clear_price"] = True
                    st.session_state["flash_message"] = "Preço salvo com sucesso!"
                    st.rerun()
            except ValueError:
                st.warning(
                    "Preço inválido. Use apenas números (ex: 650000, 650.000 ou 650,000)."
                )

    st.markdown("---")

    # ======================================================
    #  KPIs do item selecionado
    # ======================================================

    # Histórico do item para uso geral
    hist_local_raw = get_price_history_df(item_id)
    if not hist_local_raw.empty:
        hist_local = hist_local_raw.copy()
        hist_local["date"] = pd.to_datetime(hist_local["date"])
        hist_local = hist_local.sort_values("date")
    else:
        hist_local = pd.DataFrame()

    df_prices_all_summary = get_all_prices_df()
    kpi_cols = st.columns(4)

    last_price = mean_5 = var_pct = None
    status = "-"

    if not df_prices_all_summary.empty:
        df_summary_input = df_prices_all_summary.rename(columns={"item_name": "item"})
        df_sum_global = compute_summary(df_summary_input)

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

    # Renderiza KPIs
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

    # pequeno respiro antes dos insights
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
        # Trabalha só com os últimos 5 registros
        hist_last5 = hist_local.tail(5)
        prices_5 = hist_last5["price_zeny"]

        min_5 = float(prices_5.min())
        max_5 = float(prices_5.max())
        media_5 = float(prices_5.mean())

        # Oscilação = (máx - mín) / média
        osc_pct = 0.0
        if media_5 > 0:
            osc_pct = (max_5 - min_5) / media_5 * 100

        # Desvio padrão nos últimos 5
        std_5 = float(prices_5.std())

        # Preço atual = último registro
        preco_atual = float(prices_5.iloc[-1])

        # Texto de interpretação simples
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

        # ---- Layout: blocos numéricos à esquerda + gráfico à direita ----
        col_left, col_right = st.columns([1.15, 1.1])

        # -------------------------
        # Bloco numérico (esquerda)
        # -------------------------
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

        # -------------------------
        # Gráfico de tendência (direita)
        # -------------------------
        with col_right:
            st.markdown("**Tendência (últimos 5 registros)**")

            # Ajusta domínio do eixo Y para ficar colado nos valores
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

        # Veredito destacado logo abaixo dos números
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
    #  Histórico de preços (com filtro de período)
    # ======================================================

    st.subheader(f"📈 Histórico de preços – {item_name}")

    if hist_local.empty:
        st.info("Ainda não há histórico para este item.")
    else:
        # Filtro de período
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

        # --------- Tabela de histórico ---------
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
            height=400,  # 👈 altura fixa, o extra vira scroll interno
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

    df_prices_all_for_sum = get_all_prices_df()
    if df_prices_all_for_sum.empty:
        st.info("Ainda não há dados suficientes para montar o ranking.")
    else:
        df_sum_all = compute_summary(
            df_prices_all_for_sum.rename(columns={"item_name": "item"})
        )

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

            # rótulos mais curtos pra caber melhor em telas menores
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
                height=260,
            )


        with tab_down:
            df_down = prepare_top(top_loss)
            st.dataframe(
                style_market_table(df_down),
                use_container_width=True,
                hide_index=True,
                height=260,
            )


    st.markdown("---")

    # ======================================================
    #  Resumo geral do mercado
    # ======================================================

    st.subheader("🌐 Resumo geral do mercado")

    df_prices_all_summary2 = get_all_prices_df()
    if df_prices_all_summary2.empty:
        st.info("Ainda não há dados suficientes para montar o resumo.")
    else:
        df_summary_input2 = df_prices_all_summary2.rename(columns={"item_name": "item"})
        df_sum = compute_summary(df_summary_input2)

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
            height=450,  # ajusta se quiser maior/menor
        )



render()
