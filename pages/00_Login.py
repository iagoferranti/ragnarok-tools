import streamlit as st

def render_login():
    st.title("🔒 Acesso ao Monitor – Ragnarok LATAM")

    st.write("Entre com a senha do clã para continuar.")

    pwd = st.text_input("Senha de acesso", type="password")

    if st.button("Entrar", use_container_width=True):
        if pwd == st.secrets["auth"]["clan_password"]:
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Senha incorreta!")

# ----------- EXECUÇÃO DA PÁGINA -----------

if "auth" not in st.session_state:
    st.session_state["auth"] = False

if not st.session_state["auth"]:
    render_login()
else:
    st.switch_page("pages/01_📈_Monitor_de_Mercado.py")
