# pages/00_🔐_Login.py
import streamlit as st
from ui.theme import apply_theme

apply_theme("Login – Monitor de Mercado", page_icon="🔐")


def render():
    st.title("🔐 Login – Monitor de Mercado")

    # Se já estiver logado, só oferece atalho
    if st.session_state.get("auth_ok", False):
        user = st.session_state.get("user_email") or st.session_state.get("username")
        st.success(f"Você já está logado como {user}.")
        if st.button("Ir para o Monitor"):
            st.switch_page("pages/01_📈_Monitor_de_Mercado.py")
        st.stop()

    # FORM: Enter agora submete
    with st.form("login_form"):
        username = st.text_input("Usuário", key="login_username")
        password = st.text_input("Senha", type="password", key="login_password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        clan_pwd = st.secrets["auth"]["clan_password"]
        admins = st.secrets["roles"]["admins"]

        if not username.strip():
            st.error("Informe um usuário.")
            return

        if password != clan_pwd:
            st.error("Usuário ou senha inválidos.")
            return

        # Autenticado com sucesso
        st.session_state["auth_ok"] = True
        st.session_state["username"] = username
        # por enquanto usamos o próprio username como “email”
        st.session_state["user_email"] = username

        # (Opcional) flag de admin se quiser em outros lugares
        st.session_state["is_admin"] = username in admins

        st.success("Login realizado com sucesso!")
        st.switch_page("pages/01_📈_Monitor_de_Mercado.py")


render()
