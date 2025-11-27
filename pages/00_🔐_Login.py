import streamlit as st
from ui.theme import apply_theme

apply_theme("🔐 Login – Ragnarok Tools", page_icon="🔐")


def render():
    st.title("🔐 Acesso – Ragnarok Market Tools")

    ss = st.session_state

    # Lê listas do secrets
    allowed_emails = [
        e.lower() for e in st.secrets["auth"].get("allowed_emails", [])
    ]
    admin_emails = [
        e.lower() for e in st.secrets["roles"].get("admins", [])
    ]

    # Se já estiver logado, mostra info e opção de logout
    if ss.get("auth_ok", False):
        current_email = ss.get("user_email") or ss.get("username") or "desconhecido"
        st.success(f"Você já está logado como **{current_email}**.")

        if st.button("Sair", type="secondary"):
            for key in ("auth_ok", "user_email", "username"):
                ss.pop(key, None)
            st.experimental_rerun()
        return

    st.markdown(
        """
        Informe seu **e-mail cadastrado** para acessar o painel.
        Se o e-mail não estiver na lista de liberados, fale com o administrador.
        """
    )

    email_input = st.text_input(
        "E-mail",
        placeholder="voce@exemplo.com",
    )

    login_clicked = st.button("Entrar", use_container_width=True)

    if login_clicked:
        email_norm = (email_input or "").strip().lower()

        if not email_norm:
            st.warning("Informe um e-mail válido.")
            return

        if email_norm not in allowed_emails:
            st.error("Este e-mail não está autorizado. Fale com o administrador.")
            return

        # Marca sessão como autenticada
        ss["auth_ok"] = True
        ss["user_email"] = email_norm
        ss["username"] = email_norm  # se quiser usar como chave única

        # Feedback rápido
        if email_norm in admin_emails:
            st.success("Login realizado com sucesso. (Perfil: admin)")
        else:
            st.success("Login realizado com sucesso.")

        # Redireciona para o Monitor
        st.switch_page("pages/01_📈_Monitor_de_Mercado.py")


render()
