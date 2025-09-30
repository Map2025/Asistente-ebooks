import streamlit as st

def limpiar_estado(pregunta_key="pregunta_input"):
    if pregunta_key in st.session_state:
        del st.session_state[pregunta_key]
    st.session_state.respuesta = ""
    st.session_state.modo = "normal"
    st.session_state.ebook_estado = {
        "paso": "pedir_titulo",
        "datos": {},
        "contenido": [],
        "capitulo_actual": 1,
        "archivo_creado": False,
    }
    st.rerun()
