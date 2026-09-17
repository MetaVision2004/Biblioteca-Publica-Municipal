# Sistema de Gestión de Biblioteca Pública Municipal

Proyecto de la actividad integradora — Caso 1: Biblioteca.
Arquitectura basada en 3 servicios contenedorizados (equivalentes a las 3 VMs
definidas: web, aplicación/agente y base de datos), desplegados con Docker Compose.

## Componentes

| Servicio | Descripción | Puerto |
|----------|-------------|--------|
| `db`     | MySQL 8.0 — usuarios, libros, préstamos | 3306 |
| `agent`  | Agente de IA (Agent Development Kit) que recomienda libros | 8001 (interno) |
| `web`    | Aplicación Flask — gestión de usuarios/libros/préstamos y UI de recomendaciones | 5000 |

## Requisitos previos

- Docker y Docker Compose instalados.
- Una API key de Google AI Studio (https://aistudio.google.com/apikey) para que
  el agente ADK pueda usar el modelo Gemini. Sin esta key, el resto del sistema
  (usuarios, libros, préstamos) funciona normalmente; solo la pantalla de
  "Recomendaciones" requiere el agente activo.

## Puesta en marcha

```bash
cp .env.example .env
# Edita .env y coloca tu GOOGLE_API_KEY

docker compose up --build
```

La aplicación web queda disponible en `http://localhost:5000`.

## Estructura del proyecto

```
biblioteca-proyecto/
├── docker-compose.yml
├── .env.example
├── db/
│   └── init.sql            # esquema + datos de ejemplo
├── web/                     # app Flask (usuarios, libros, préstamos)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── templates/
│   └── static/
└── agent/                   # agente de IA con ADK
    ├── Dockerfile
    ├── requirements.txt
    ├── agent.py             # definición del LlmAgent
    └── main.py              # servicio FastAPI que expone el agente
```

## Flujo del agente de IA

1. La app web (`/recomendaciones`) envía el `usuario_id` al servicio del agente.
2. `agent/main.py` arma un contexto con el historial de préstamos del usuario y
   el catálogo disponible, consultando directamente la base de datos MySQL.
3. El `LlmAgent` definido en `agent/agent.py` (Agent Development Kit) procesa
   ese contexto y genera una recomendación en lenguaje natural.
4. La respuesta se muestra en la interfaz web.

## Notas para la entrega

- Cambia las contraseñas de `.env` antes de cualquier despliegue real.
- El `init.sql` crea automáticamente las tablas y algunos datos de ejemplo la
  primera vez que se levanta el contenedor de MySQL (volumen `db_data` vacío).
- Si se necesita reiniciar la base de datos desde cero: `docker compose down -v`.
