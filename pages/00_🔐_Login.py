import streamlit as st
from ui.theme import apply_theme

apply_theme("🔐 Login – Ragnarok Tools", page_icon="🔐")


def render():
    st.title("🔐 Acesso – Ragnarok Market Tools")

    ss = st.session_state

    # ------------------------------------------------------------
    # 1) DETECTA MODO DEMO (?demo=1) E PULA LOGIN
    # ------------------------------------------------------------
    # --- Modo demo via query string (?demo=1) ---
    raw_demo = st.query_params.get("demo", None)

    # st.query_params pode retornar "1" ou ["1"]
    if isinstance(raw_demo, list):
        raw_demo = raw_demo[0]

    demo_mode = (raw_demo == "1")

    ss["demo_mode"] = demo_mode  # deixa disponível para o Monitor

    if demo_mode:
        st.info(
            "🧪 Você está acessando o **Modo Demo**.\n\n"
            "Não é necessário informar e-mail. "
            "Redirecionando automaticamente para o painel..."
        )
        st.switch_page("pages/01_📈_Monitor_de_Mercado.py")
        st.stop()

    # ------------------------------------------------------------
    # 2) LISTAS DE AUTORIZAÇÃO (modo normal)
    # ------------------------------------------------------------
    allowed_emails = [
        e.lower() for e in st.secrets["auth"].get("allowed_emails", [])
    ]
    admin_emails = [
        e.lower() for e in st.secrets["roles"].get("admins", [])
    ]

    # ------------------------------------------------------------
    # 3) Se já estiver logado → mostra info e botão de logout
    # ------------------------------------------------------------
    if ss.get("auth_ok", False):
        current_email = ss.get("user_email") or ss.get("username") or "desconhecido"
        st.success(f"Você já está logado como **{current_email}**.")

        if st.button("Sair", type="secondary"):
            for key in ("auth_ok", "user_email", "username"):
                ss.pop(key, None)
            st.rerun()
        return

    # ------------------------------------------------------------
    # 4) Formulário de login (modo normal)
    # ------------------------------------------------------------
    st.markdown(
        """
        Informe seu **e-mail cadastrado** para acessar o painel.  
        Se o e-mail não estiver na lista de liberados, fale com o administrador.
        """
    )

    with st.form("login_form"):
        email_input = st.text_input(
            "E-mail",
            placeholder="voce@exemplo.com",
        )
        submit = st.form_submit_button("Entrar")

    # ------------------------------------------------------------
    # 5) Validação do login
    # ------------------------------------------------------------
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

        # Redireciona para o Monitor
        st.switch_page("pages/01_📈_Monitor_de_Mercado.py")


render()
