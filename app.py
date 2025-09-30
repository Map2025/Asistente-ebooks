import streamlit as st
from services.openai_service import generar_texto_openai, generar_embedding
from services.db_service import obtener_ebooks_disponibles, buscar_fragmentos
from services.ebook_service import crear_docx
from services.tts_service import reproducir_audio
from utils.helpers import limpiar_estado

st.set_page_config(page_title="Asistente Inteligente ebooks de IA", layout="centered")

# Estilos
st.markdown("""
<style>
body {background-color: #000; color: #fff;}
.titulo {color: #f00; font-size: 32px; font-weight: bold; text-align: center; margin-bottom: 30px;}
.chat-burbuja {background-color: #f2f2f2; border: 1px solid #f00; padding: 15px; border-radius: 10px; margin-top: 20px; color:#000;}
.boton-rojo button {background-color: #f00 !important; color: white !important; font-weight: bold; border-radius: 8px; margin-top: 20px;}
</style>
""", unsafe_allow_html=True)

# Estados iniciales
if "respuesta" not in st.session_state:
    st.session_state.respuesta = ""
if "modo" not in st.session_state:
    st.session_state.modo = "normal"
if "ebook_estado" not in st.session_state:
    st.session_state.ebook_estado = {
        "paso": "pedir_titulo",
        "datos": {},
        "contenido": [],
        "capitulo_actual": 1,
        "archivo_creado": False,
    }

pregunta_key = "pregunta_input"

# Selección de ebook
ebooks = obtener_ebooks_disponibles()
if not ebooks:
    st.warning("No hay ebooks disponibles.")
    st.stop()

ebook_seleccionado = st.selectbox("📚 Selecciona el ebook:", ebooks, key="ebook_seleccionado")

# Botón hacia tienda
tienda_url = "https://serviciosoft.odoo.com/shop"
st.markdown(f'''
    <a href="{tienda_url}" target="_blank" style="
        background-color:#ff0000;
        color:white;
        padding:10px 20px;
        border-radius:8px;
        text-decoration:none;
        font-weight:bold;
        display:inline-block;
        margin-top:20px;
    ">🛒 Ir a la Tienda</a>
''', unsafe_allow_html=True)

# Instrucciones
st.markdown("""
<div style="background-color:#222; padding:15px; border-radius:8px; margin-bottom:20px; color:#ddd;">
<b>Cómo usar este asistente:</b><br>
Este asistente responde preguntas sobre el ebook seleccionado.<br>
Ejemplo de Prompt: Cuáles son los temas que se incluyen en el ebook<br>
</div>
""", unsafe_allow_html=True)

# --- MODO NORMAL ---
if st.session_state.modo == "normal":
    st.markdown("""
    <div style="background-color:#222; padding:10px; border-radius:8px; margin-bottom:15px; color:#ddd; font-weight:bold;">
        ✨ Para crear un ebook completo, escribí <i>"crear ebook"</i> en la caja de preguntas.
    </div>
    """, unsafe_allow_html=True)

    pregunta = st.text_area(
        "✍️ Escribí tu pregunta sobre el ebook:",
        value=st.session_state.get(pregunta_key, ""),
        key=pregunta_key,
        height=100
    )

    if st.button("📘 Obtener respuesta", type="primary"):
        if not pregunta.strip():
            st.warning("Por favor, ingresa una pregunta.")
        elif pregunta.strip().lower().startswith("crear ebook"):
            st.session_state.modo = "ebook"
            st.rerun()
        else:
            with st.spinner("🧠 Pensando..."):
                try:
                    embedding = generar_embedding(pregunta)
                    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                    fragmentos = buscar_fragmentos(ebook_seleccionado, embedding_str)
                    contexto = "\n\n".join(fragmentos)
                    prompt = f"""Eres un asistente experto en ebooks técnicos.
Usa este contexto para responder la pregunta claramente:

Contexto:
{contexto}

Pregunta:
{pregunta}
"""
                    st.session_state.respuesta = generar_texto_openai(prompt, model="gpt-4", max_tokens=500)
                except Exception as e:
                    st.session_state.respuesta = f"❌ Error: {e}"

    if st.session_state.respuesta:
        st.markdown(f'<div class="chat-burbuja">{st.session_state.respuesta}</div>', unsafe_allow_html=True)
        if st.button("🔄 Hacer otra pregunta"):
            limpiar_estado()
        if st.button("🔊 Escuchar respuesta"):
            reproducir_audio(st.session_state.respuesta)

# --- MODO EBOOK ---
elif st.session_state.modo == "ebook":
    estado = st.session_state.ebook_estado
    paso = estado["paso"]

    def avanzar_ebook(respuesta):
        if paso == "pedir_titulo":
            estado["datos"]["titulo"] = respuesta
            estado["paso"] = "pedir_tema"
        elif paso == "pedir_tema":
            estado["datos"]["tema"] = respuesta
            estado["paso"] = "pedir_publico"
        elif paso == "pedir_publico":
            estado["datos"]["publico"] = respuesta
            estado["paso"] = "pedir_tono"
        elif paso == "pedir_tono":
            estado["datos"]["tono"] = respuesta
            estado["paso"] = "pedir_cantidad_capitulos"
        elif paso == "pedir_cantidad_capitulos":
            try:
                capitulos = int(respuesta)
                if capitulos < 1:
                    st.warning("Ingresa un número mayor que 0.")
                    return
                estado["datos"]["capitulos"] = capitulos
                estado["paso"] = "generar_indice"
            except:
                st.warning("Ingresa un número válido.")
        elif paso == "confirmar_indice":
            if respuesta.lower() in ["sí", "si", "s"]:
                estado["paso"] = "generar_todos_capitulos"
            elif respuesta.lower() in ["no", "n"]:
                estado["paso"] = "pedir_cantidad_capitulos"
            else:
                st.warning("Responde sí o no.")
        elif paso == "finalizar":
            if respuesta.lower() in ["sí", "si", "s"]:
                archivo = crear_docx(estado["contenido"], estado["datos"]["titulo"])
                estado["archivo_creado"] = True
                estado["paso"] = "completo"
                st.success(f"Ebook generado: {archivo}")
            else:
                st.info("Proceso finalizado sin crear archivo.")
                estado["paso"] = "completo"

    if paso == "generar_indice":
        st.info("Generando índice, por favor esperá...")
        prompt_indice = f"""
Crea un índice para un ebook titulado '{estado['datos']['titulo']}', 
tema: {estado['datos']['tema']}, público objetivo: {estado['datos']['publico']}, 
tono: {estado['datos']['tono']}, con {estado['datos']['capitulos']} capítulos.
Separa títulos y subtítulos claramente.
"""
        indice = generar_texto_openai(prompt_indice)
        st.text_area("Índice generado", indice, height=200)
        estado["contenido"].append({"tipo": "indice", "texto": indice})
        estado["paso"] = "confirmar_indice"
        st.rerun()

    elif paso == "generar_todos_capitulos":
        st.info("Generando todos los capítulos, esto puede tardar un poco...")
        indice = next((item['texto'] for item in estado["contenido"] if item['tipo'] == 'indice'), "")
        for i in range(1, estado["datos"]["capitulos"] + 1):
            prompt_cap = f"""
Escribe el capítulo {i} del ebook titulado '{estado['datos']['titulo']}'.
Tema general: {estado['datos']['tema']}
Público objetivo: {estado['datos']['publico']}
Tono: {estado['datos']['tono']}
Índice: {indice}

Desarrolla el capítulo con subtítulos y ejemplos. Extensión mínima: 800 palabras.
"""
            cap_texto = generar_texto_openai(prompt_cap)
            estado["contenido"].append({"tipo": "capitulo", "numero": i, "texto": cap_texto})
            st.text(f"Capítulo {i} generado.")

        estado["paso"] = "finalizar"
        st.rerun()

    else:
        pregunta_ebook = {
            "pedir_titulo": "¿Cuál será el título del ebook?",
            "pedir_tema": "¿Cuál es el tema principal?",
            "pedir_publico": "¿Quién es tu público objetivo?",
            "pedir_tono": "¿Qué tono quieres para la redacción? (formal, motivador, etc.)",
            "pedir_cantidad_capitulos": "¿Cuántos capítulos aproximadamente querés?",
            "confirmar_indice": "¿Querés que comience a escribir todos los capítulos? (sí/no)",
            "finalizar": "¿Querés que cree el archivo DOCX para descargar? (sí/no)",
            "completo": "Proceso finalizado. Recargá la página para crear otro ebook."
        }
        prompt = pregunta_ebook.get(paso)
        if prompt:
            respuesta = st.text_input(prompt, key="input_ebook")
            if paso == "pedir_titulo":
                if st.button("Cancelar creación de ebook"):
                    limpiar_estado()
                    st.rerun()
            if respuesta:
                avanzar_ebook(respuesta)
                st.rerun()
        else:
            st.write("Esperando...")

    if estado.get("archivo_creado"):
        with open("ebook_generado.docx", "rb") as f:
            st.download_button(
                label="Descargar ebook generado",
                data=f,
                file_name="ebook_generado.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
