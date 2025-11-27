import streamlit as st

# Se já está autenticado, manda pro Monitor.
# Senão, manda pra página de Login.
if st.session_state.get("auth_ok", False):
    st.switch_page("pages/01_📈_Monitor_de_Mercado.py")
else:
    st.switch_page("pages/00_🔐_Login.py")  # use o nome real do seu arquivo de login
