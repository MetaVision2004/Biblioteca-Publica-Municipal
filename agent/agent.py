"""
Agente de recomendación de libros construido con Agent Development Kit (ADK).

El agente recibe el historial de préstamos de un usuario y el catálogo
disponible, y devuelve una recomendación en lenguaje natural razonada
sobre géneros/autores que el usuario ya ha leído.
"""
import os
import psycopg
from psycopg.rows import dict_row
from google.adk.agents import LlmAgent

MODEL_NAME = os.environ.get("ADK_MODEL", "gemini-2.0-flash")


def _get_conn():
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL no está configurada")
    return psycopg.connect(database_url, row_factory=dict_row)


def buscar_libros_disponibles(categoria: str, consulta: str) -> dict:
    """Busca en Supabase libros con copias disponibles en tiempo real.

    Usa esta herramienta antes de recomendar para no depender de un catálogo
    que puede haber cambiado desde el inicio de la conversación.
    """
    categoria = (categoria or "").strip()
    consulta = (consulta or "").strip()
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, titulo, autor, categoria, copias_disponibles
               FROM libros
               WHERE copias_disponibles > 0
                 AND (%s = '' OR categoria ILIKE %s)
                 AND (%s = '' OR titulo ILIKE %s OR autor ILIKE %s)
               ORDER BY titulo
               LIMIT 8""",
            (categoria, f"%{categoria}%", consulta, f"%{consulta}%", f"%{consulta}%"),
        )
        libros = cur.fetchall()
    conn.close()
    return {"status": "ok", "libros": [dict(libro) for libro in libros]}


def verificar_disponibilidad(titulo: str) -> dict:
    """Confirma por título que una recomendación sigue disponible."""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT titulo, autor, categoria, copias_disponibles
               FROM libros WHERE titulo ILIKE %s ORDER BY copias_disponibles DESC LIMIT 1""",
            (titulo.strip(),),
        )
        libro = cur.fetchone()
    conn.close()
    if not libro:
        return {"status": "not_found", "disponible": False}
    return {"status": "ok", "disponible": libro["copias_disponibles"] > 0, "libro": dict(libro)}


root_agent = LlmAgent(
    name="bibliotecario_virtual",
    model=MODEL_NAME,
    description="Agente que recomienda libros del catálogo de la biblioteca "
                 "municipal según el historial de préstamos de cada usuario.",
    instruction=(
        "Eres el asistente de recomendaciones de una biblioteca pública municipal. "
        "Recibirás el historial de préstamos de un usuario. Usa buscar_libros_disponibles "
        "para consultar el catálogo en vivo, interpretando también solicitudes como "
        "'quiero algo de terror corto'. Recomienda 1 a 3 libros basándote en el historial "
        "y la petición actual. Antes de responder, usa verificar_disponibilidad para cada "
        "título elegido. Nunca inventes libros ni recomiendes copias agotadas. Si el usuario "
        "pide otra opción, busca alternativas distintas a las anteriores. Responde en español, "
        "con tono cordial, breve y claro (máximo 6 líneas)."
    ),
    tools=[buscar_libros_disponibles, verificar_disponibilidad],
)
