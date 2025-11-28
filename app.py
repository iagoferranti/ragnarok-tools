import streamlit as st

ss = st.session_state

# -------------------------------------------------
# 1) Detecta MODO DEMO pela query string (?demo=1)
# -------------------------------------------------
raw_demo = st.query_params.get("demo", None)

# st.query_params pode devolver "1" ou ["1"]
if isinstance(raw_demo, list):
    raw_demo = raw_demo[0]

demo_mode = (raw_demo == "1")

if demo_mode:
    # Marca sessão como "logada" em modo demo
    ss["demo_mode"] = True
    ss["auth_ok"] = True
    ss["user_email"] = "demo@preview"
    ss["username"] = "demo_preview"

    # Vai direto para o Monitor, sem passar pelo Login
    st.switch_page("pages/01_📈_Monitor_de_Mercado.py")

else:
    # -------------------------------------------------
    # 2) Fluxo normal: login obrigatório
    # -------------------------------------------------
    if ss.get("auth_ok", False):
        st.switch_page("pages/01_📈_Monitor_de_Mercado.py")
    else:
        st.switch_page("pages/00_🔐_Login.py")
