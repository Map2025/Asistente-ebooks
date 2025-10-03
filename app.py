import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
from services.openai_service import generar_texto_openai, generar_embedding
from services.db_service import obtener_ebooks_disponibles, buscar_fragmentos
from services.ebook_service import crear_docx
from services.tts_service import reproducir_audio
from utils.helpers import limpiar_estado

st.set_page_config(page_title="Asistente Inteligente ebooks de IA", layout="centered")

# --------------------------
# Solicitar correo del usuario
# --------------------------
if "user_email" not in st.session_state:
    email = st.text_input("✉️ Ingresa tu correo electrónico para usar el asistente:")
    if email:
        st.session_state["user_email"] = email.strip().lower()
        st.rerun()
    else:
        st.stop()

user_email = st.session_state["user_email"]

# --------------------------
# Conexión a Postgres
# --------------------------
@st.cache_resource
def init_connection():
    db = st.secrets["database"]
    return psycopg2.connect(
        dbname=db["name"],
        user=db["user"],
        password=db["password"],
        host=db["host"],
        port=db["port"],
        sslmode=db["sslmode"]
    )

conn = init_connection()

# --------------------------
# Funciones de control de créditos
# --------------------------
@st.cache_data
def get_or_create_user(email: str, conn):
    """
    Busca un usuario por email. Si no existe, crea uno nuevo con user_id tipo UUID.
    Devuelve: (user_id, credits)
    """
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        # 1️⃣ Buscar usuario existente
        cur.execute("SELECT user_id, credits FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if row:
            return row["user_id"], row["credits"]

        # 2️⃣ Usuario no existe: generar UUID
        new_user_id = str(uuid.uuid4())

        try:
            cur.execute(
                """
                INSERT INTO users (user_id, email, credits)
                VALUES (%s, %s, %s)
                RETURNING user_id, credits
                """,
                (new_user_id, email, 20)
            )
            row = cur.fetchone()  # obtener datos insertados
            conn.commit()         # confirmar inserción
            return row["user_id"], row["credits"]
        except psycopg2.Error:
            conn.rollback()       # limpiar si falla
            raise


def update_credits(user_id: str, amount: int, action_type: str):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            UPDATE users SET credits = credits - %s
            WHERE user_id = %s AND credits >= %s
            RETURNING credits
        """, (amount, user_id, amount))
        row = cur.fetchone()
        if row:
            new_credits = row["credits"]
            cur.execute("""
                INSERT INTO credit_transactions (user_id, action_type, amount)
                VALUES (%s, %s, %s)
            """, (user_id, action_type, -amount))
            conn.commit()
            return new_credits
        else:
            return None

@st.cache_data
def get_transaction_history(user_id: str):
    query = """
        SELECT created_at, action_type, amount
        FROM credit_transactions
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 50
    """
    return pd.read_sql(query, conn, params=(user_id,))

# --------------------------
# Inicialización de estados
# --------------------------
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

# --------------------------
# Obtener saldo actual
# --------------------------
user_id, credits = get_or_create_user(user_email, conn)
if "credits" not in st.session_state:
    st.session_state["credits"] = credits
st.sidebar.metric("💰 Créditos disponibles", st.session_state["credits"])

# --------------------------
# Estilos
# --------------------------
st.markdown("""
<style>
body {background-color: #000; color: #fff;}
.titulo {color: #f00; font-size: 32px; font-weight: bold; text-align: center; margin-bottom: 30px;}
.chat-burbuja {background-color: #f2f2f2; border: 1px solid #f00; padding: 15px; border-radius: 10px; margin-top: 20px; color:#000;}
.boton-rojo button {background-color: #f00 !important; color: white !important; font-weight: bold; border-radius: 8px; margin-top: 20px;}
</style>
""", unsafe_allow_html=True)

# --------------------------
# Selección de ebook
# --------------------------
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

# --------------------------
# Instrucciones
# --------------------------
st.markdown("""
<div style="background-color:#222; padding:15px; border-radius:8px; margin-bottom:20px; color:#ddd;">
<b>Cómo usar este asistente:</b><br>
Este asistente responde preguntas sobre el ebook seleccionado.<br>
Ejemplo de Prompt: Cuáles son los temas que se incluyen en el ebook<br>
</div>
""", unsafe_allow_html=True)

# --------------------------
# --- MODO NORMAL PREGUNTAS
# --------------------------
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
            credit_cost = 1
            nuevo_balance = update_credits(user_id, credit_cost, "pregunta")
            if nuevo_balance is None:
                st.error("❌ No tienes créditos suficientes para hacer esta pregunta.")
            else:
                st.session_state["credits"] = nuevo_balance
                st.sidebar.metric("💰 Créditos disponibles", st.session_state["credits"])
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

# --------------------------
# --- MODO EBOOK ---
# --------------------------
elif st.session_state.modo == "ebook":
    estado = st.session_state.ebook_estado

    def avanzar_ebook(respuesta):
        current_paso = estado["paso"]

        if current_paso == "pedir_titulo":
            estado["datos"]["titulo"] = respuesta
            estado["paso"] = "pedir_tema"
        elif current_paso == "pedir_tema":
            estado["datos"]["tema"] = respuesta
            estado["paso"] = "pedir_publico"
        elif current_paso == "pedir_publico":
            estado["datos"]["publico"] = respuesta
            estado["paso"] = "pedir_tono"
        elif current_paso == "pedir_tono":
            estado["datos"]["tono"] = respuesta
            estado["paso"] = "pedir_cantidad_capitulos"
        elif current_paso == "pedir_cantidad_capitulos":
            try:
                capitulos = int(respuesta)
                if capitulos < 1:
                    st.warning("Ingresa un número mayor que 0.")
                    return
                estado["datos"]["capitulos"] = capitulos
                estado["paso"] = "generar_indice"
            except:
                st.warning("Ingresa un número válido.")
        elif current_paso == "confirmar_indice":
            if respuesta.lower() in ["sí", "si", "s"]:
                total_cost = 5 * estado["datos"]["capitulos"]
                nuevo_balance = update_credits(user_id, total_cost, "generar_ebook")
                if nuevo_balance is None:
                    st.error("❌ No tienes créditos suficientes para generar el ebook completo.")
                    return
                else:
                    st.session_state["credits"] = nuevo_balance
                    st.sidebar.metric("💰 Créditos disponibles", st.session_state["credits"])
                    estado["paso"] = "generar_todos_capitulos"
            elif respuesta.lower() in ["no", "n"]:
                estado["paso"] = "pedir_cantidad_capitulos"
            else:
                st.warning("Responde sí o no.")
        elif current_paso == "finalizar":
            if respuesta.lower() in ["sí", "si", "s"]:
                archivo = crear_docx(estado["contenido"], estado["datos"]["titulo"])
                estado["archivo_creado"] = True
                estado["paso"] = "completo"
                st.success(f"Ebook generado: {archivo}")
            else:
                st.info("Proceso finalizado sin crear archivo.")
                estado["paso"] = "completo"

    # Generar índice
    if estado["paso"] == "generar_indice":
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

    # Generar capítulos
    elif estado["paso"] == "generar_todos_capitulos":
        st.info("Generando todos los capítulos, esto puede tardar un poco...")

        # Limpiar capítulos anteriores y dejar solo el índice
        estado["contenido"] = [item for item in estado["contenido"] if item["tipo"] == "indice"]

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

    # Entrada de usuario para cada paso del ebook
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
        prompt = pregunta_ebook.get(estado["paso"])
        if prompt and estado["paso"] not in ["generar_indice", "generar_todos_capitulos"]:
            respuesta = st.text_input(prompt, key="input_ebook")
            if respuesta:
                avanzar_ebook(respuesta)
                st.rerun()

    # Descargar ebook
    if estado.get("archivo_creado"):
        with open("ebook_generado.docx", "rb") as f:
            st.download_button(
                label="Descargar ebook generado",
                data=f,
                file_name="ebook_generado.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
