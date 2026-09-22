import asyncio
import logging
import os
import psycopg
from psycopg.rows import dict_row
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from google.adk.runners import InMemoryRunner
from google.genai import types

from agent import root_agent

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="Agente de Recomendación - Biblioteca")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
logger = logging.getLogger(__name__)

runner = InMemoryRunner(agent=root_agent, app_name="biblioteca_agent")


class RecomendarRequest(BaseModel):
    usuario_id: int
    mensaje: str = "Recomiéndame una lectura según mi historial."
    session_id: str | None = None


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada para Supabase")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def construir_contexto(usuario_id: int) -> str:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT nombre FROM usuarios WHERE id = %s", (usuario_id,))
        usuario = cur.fetchone()

        cur.execute(
            """SELECT l.titulo, l.autor, l.categoria
               FROM prestamos p JOIN libros l ON l.id = p.libro_id
               WHERE p.usuario_id = %s""",
            (usuario_id,),
        )
        historial = cur.fetchall()

    conn.close()

    nombre = usuario["nombre"] if usuario else "Usuario desconocido"
    historial_txt = (
        "\n".join(f"- {h['titulo']} ({h['autor']}, {h['categoria']})" for h in historial)
        or "Sin préstamos previos."
    )
    return (
        f"Usuario: {nombre}\n\n"
        f"Historial de préstamos:\n{historial_txt}\n\n"
        "Consulta el catálogo con tus herramientas antes de recomendar."
    )


def recomendacion_respaldo(usuario_id: int) -> str:
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT categoria, autor FROM prestamos p JOIN libros l ON l.id = p.libro_id WHERE p.usuario_id = %s",
            (usuario_id,),
        )
        historial = cur.fetchall()
        cur.execute(
            "SELECT titulo, autor, categoria FROM libros WHERE copias_disponibles > 0 ORDER BY titulo"
        )
        catalogo = cur.fetchall()
    conn.close()

    categorias = {item["categoria"] for item in historial if item["categoria"]}
    autores = {item["autor"] for item in historial if item["autor"]}
    ordenados = sorted(
        catalogo,
        key=lambda libro: (
            libro["categoria"] not in categorias,
            libro["autor"] not in autores,
            libro["titulo"],
        ),
    )
    sugerencias = ordenados[:3]
    if not sugerencias:
        return "No hay libros disponibles para recomendar en este momento."

    detalles = "; ".join(
        f"{libro['titulo']} de {libro['autor']} ({libro['categoria']})"
        for libro in sugerencias
    )
    return f"Mientras el agente de IA vuelve a estar disponible, puedes consultar: {detalles}."


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/recomendar")
async def recomendar(req: RecomendarRequest):
    if not os.environ.get("GOOGLE_API_KEY"):
        return {
            "recomendacion": "El asistente de IA no está disponible ahora. "
            + recomendacion_respaldo(req.usuario_id),
            "session_id": req.session_id,
        }

    prompt = construir_contexto(req.usuario_id) + f"\n\nPetición actual del usuario: {req.mensaje}"

    for attempt in range(2):
        try:
            if req.session_id and attempt == 0:
                try:
                    session = await runner.session_service.get_session(
                        app_name="biblioteca_agent",
                        user_id=str(req.usuario_id),
                        session_id=req.session_id,
                    )
                except Exception:
                    session = await runner.session_service.create_session(
                        app_name="biblioteca_agent", user_id=str(req.usuario_id)
                    )
            else:
                session = await runner.session_service.create_session(
                    app_name="biblioteca_agent", user_id=str(req.usuario_id)
                )

            texto_final = ""
            async for event in runner.run_async(
                user_id=str(req.usuario_id),
                session_id=session.id,
                new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    texto_final = event.content.parts[0].text
            break
        except Exception as exc:
            logger.exception("Error generando recomendación ADK")
            if getattr(exc, "status_code", None) == 429 or attempt == 1:
                break
            if attempt == 0:
                await asyncio.sleep(1)
    else:
        return {
            "recomendacion": "El asistente no está disponible en este momento. "
            + recomendacion_respaldo(req.usuario_id),
            "session_id": req.session_id,
        }

    if not texto_final:
        return {
            "recomendacion": "El asistente de IA no está disponible ahora. "
            + recomendacion_respaldo(req.usuario_id),
            "session_id": req.session_id,
        }

    return {"recomendacion": texto_final, "session_id": session.id}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
