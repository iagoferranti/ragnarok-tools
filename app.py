import streamlit as st

ss = st.session_state

# -------------------------------------------------
# 1) Modo sem login — sempre entra direto no monitor
# -------------------------------------------------

# Definimos valores padrão para evitar erros em telas que usam user_email / username
ss["auth_ok"] = True
ss["demo_mode"] = False
ss["user_email"] = "anonimo_cla"
ss["username"] = "anonimo"

# Redireciona direto para o monitor
st.switch_page("pages/01_📈_Monitor_de_Mercado.py")
