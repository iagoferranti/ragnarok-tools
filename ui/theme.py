# ui/theme.py
from pathlib import Path
import streamlit as st


def apply_theme(page_title: str, page_icon: str = "📊") -> None:
    """
    Aplica o tema padrão do Ragnarok Tools:
    - layout wide
    - título e ícone da aba
    - CSS customizado
    - sidebar com branding e versão do servidor
    """

    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Carrega CSS customizado (tradingview.css)
    css_path = Path("styles/tradingview.css")
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    # Sidebar enxuta e profissional
    with st.sidebar:
        st.markdown("### 🧙‍♂️ Ragnarok Tools")
        st.markdown(
            """
Ferramentas pessoais para análise de **Ragnarok Online LATAM**.
"""
        )
        st.markdown("---")
        st.caption("Servidor: LATAM · v0.1")
