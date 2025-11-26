# app.py – Home do Ragnarok Tools

import streamlit as st
from ui.theme import apply_theme

# Aplica tema global (usa o mesmo CSS e sidebar)
apply_theme("Ragnarok Tools – Painel Inicial", page_icon="🧙‍♂️")

# Título principal
st.title("🧙‍♂️ Ragnarok Tools – Painel Inicial")

st.markdown(
    """
Bem-vindo ao hub central de ferramentas de análise para **Ragnarok Online LATAM**.

Use o menu à esquerda para navegar entre os módulos.
"""
)

st.markdown("---")

# Cards dos módulos
col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
### 📈 Monitor de Mercado
Controle diário de preços de itens-chave, acompanhe variações e identifique oportunidades de compra/venda.
"""
    )

with col2:
    st.markdown(
        """
### 💰 Lucro por Instância
Monte rotas de instâncias, estime drops, custos e veja quanto cada run está rendendo em média.

### ☠️ Cálculo de Toxina
Apoio às builds venenosas: consumo, custo por hora, break-even de farm, etc.
"""
    )

st.markdown("---")
st.caption("Servidor: LATAM · v0.1")
