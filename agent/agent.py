"""
Agente de recomendación de libros construido con Agent Development Kit (ADK).

El agente recibe el historial de préstamos de un usuario y el catálogo
disponible, y devuelve una recomendación en lenguaje natural razonada
sobre géneros/autores que el usuario ya ha leído.
"""
import os
from google.adk.agents import LlmAgent

MODEL_NAME = os.environ.get("ADK_MODEL", "gemini-2.0-flash")


def obtener_catalogo_disponible(categoria: str) -> dict:
    """Herramienta del agente: no se usa directamente aquí porque el catálogo
    y el historial se inyectan en el prompt desde el servicio `main.py`.
    Se deja como ejemplo de herramienta ADK por si se conecta a una API real."""
    return {"status": "not_implemented", "detail": "usar datos inyectados en el prompt"}


root_agent = LlmAgent(
    name="bibliotecario_virtual",
    model=MODEL_NAME,
    description="Agente que recomienda libros del catálogo de la biblioteca "
                 "municipal según el historial de préstamos de cada usuario.",
    instruction=(
        "Eres el asistente de recomendaciones de una biblioteca pública municipal. "
        "Recibirás el historial de préstamos de un usuario y el catálogo de libros "
        "disponibles (con copias en stock). Tu tarea es recomendar 1 a 3 libros del "
        "catálogo disponible que probablemente le interesen al usuario, basándote en "
        "los autores y categorías que ya ha leído. No recomiendes libros sin copias "
        "disponibles. Explica brevemente por qué cada libro es una buena sugerencia. "
        "Responde en español, en un tono cordial y breve (máximo 4 líneas)."
    ),
    tools=[obtener_catalogo_disponible],
)
