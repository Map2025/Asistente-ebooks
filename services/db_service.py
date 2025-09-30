from sqlalchemy import create_engine, text
from config import DATABASE_URL

engine = create_engine(DATABASE_URL)

def obtener_ebooks_disponibles():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT ebook FROM fragmentos_ebook")).fetchall()
    return [row[0] for row in result]

def buscar_fragmentos(ebook: str, embedding_str: str, limit: int = 3):
    query = text("""
        SELECT fragmento
        FROM fragmentos_ebook
        WHERE ebook = :ebook
        ORDER BY embedding <-> CAST(:embedding AS vector)
        LIMIT :limit
    """)
    with engine.connect() as conn:
        resultados = conn.execute(query, {"ebook": ebook, "embedding": embedding_str, "limit": limit}).fetchall()
    return [r[0] for r in resultados]
