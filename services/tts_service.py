from gtts import gTTS
import tempfile
import streamlit as st

def reproducir_audio(texto: str):
    tts = gTTS(text=texto, lang='es')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tts.save(tmp.name)
        st.audio(tmp.name)
