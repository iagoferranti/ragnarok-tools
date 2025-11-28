import streamlit as st
from ui.theme import apply_theme

apply_theme("🔐 Login – Ragnarok Tools", page_icon="🔐")


def render():
    st.title("🔐 Acesso – Ragnarok Market Tools")

    ss = st.session_state

    # ======================================================
    #   1) DETECTA MODO DEMO
    # ======================================================
    raw_demo = st.query_params.get("demo", None)

    # st.query_params pode retornar ["1"] ou "1"
    if isinstance(raw_demo, list):
        raw_demo = raw_demo[0]

    demo_mode = (raw_demo == "1")

    # 🚨 Se for DEMO → pula tudo e vai direto para o Monitor
    if demo_mode:
        ss["auth_ok"] = True
        ss["user_email"] = "demo@preview"
        ss["username"] = "demo_preview"

        st.info("🔍 Entrando em **Modo Demo** (login desativado)...")

        st.switch_page("pages/01_📈_Monitor_de_Mercado.py")
        return

    # ======================================================
    #   2) LOGIN NORMAL
    # ======================================================
    allowed_emails = [e.lower() for e in st.secrets["auth"].get("allowed_emails", [])]
    admin_emails = [e.lower() for e in st.secrets["roles"].get("admins", [])]

    # Já logado
    if ss.get("auth_ok", False):
        current_email = ss.get("user_email") or ss.get("username") or "desconhecido"
        st.success(f"Você já está logado como **{current_email}**.")

        if st.button("Sair", type="secondary"):
            for key in ("auth_ok", "user_email", "username"):
                ss.pop(key, None)
            st.rerun()
        return

    st.markdown(
        """
        Informe seu **e-mail cadastrado** para acessar o painel.  
        Se o e-mail não estiver na lista de liberados, fale com o administrador.
        """
    )

    # FORM DE LOGIN
    with st.form("login_form"):
        email_input = st.text_input(
            "E-mail",
            placeholder="voce@exemplo.com",
            key="login_email_input",
        )
        submit = st.form_submit_button("Entrar")

    if submit:
        email_norm = (email_input or "").strip().lower()

        if not email_norm:
            st.warning("Informe um e-mail válido.")
            return

        if email_norm not in allowed_emails:
            st.error("Este e-mail não está autorizado. Fale com o administrador.")
            return

        ss["auth_ok"] = True
        ss["user_email"] = email_norm
        ss["username"] = email_norm

        if email_norm in admin_emails:
            st.success("Login realizado com sucesso. (Perfil: admin)")
        else:
            st.success("Login realizado com sucesso.")

        st.switch_page("pages/01_📈_Monitor_de_Mercado.py")


render()
