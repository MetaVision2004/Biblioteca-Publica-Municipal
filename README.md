# Sistema de Gestión de Biblioteca Pública Municipal

Proyecto de la actividad integradora — Caso 1: Biblioteca.
Arquitectura basada en dos servicios contenedorizados (web y agente), con
Supabase PostgreSQL como base de datos administrada.

## Componentes

| Servicio | Descripción | Puerto |
|----------|-------------|--------|
| `Supabase` | PostgreSQL administrado — usuarios, libros, préstamos y reservas | externo |
| `agent`  | Agente de IA (Agent Development Kit) que recomienda libros | 8001 (interno) |
| `web`    | Aplicación Flask — gestión de usuarios/libros/préstamos y UI de recomendaciones | 5000 |

## Requisitos previos

- Docker y Docker Compose instalados.
- Un proyecto de Supabase y su cadena de conexión PostgreSQL.
- Una API key de Google AI Studio (https://aistudio.google.com/apikey) para que
  el agente ADK pueda usar el modelo Gemini. Sin esta key, el resto del sistema
  (usuarios, libros, préstamos) funciona normalmente; solo la pantalla de
  "Recomendaciones" requiere el agente activo.

## Puesta en marcha

```bash
cp .env.example .env
# Configura DATABASE_URL con la conexión PostgreSQL de Supabase.
# Configura también SUPABASE_URL y SUPABASE_ANON_KEY desde Project Settings > API.
# Edita también GOOGLE_API_KEY si quieres activar el agente Gemini.
# Para notificaciones, configura SMTP_HOST/SMTP_PORT/SMTP_USERNAME/SMTP_PASSWORD
# y SMTP_FROM, o usa RESEND_API_KEY + EMAIL_FROM como alternativa.

docker compose up --build
```

La aplicación web queda disponible en `http://localhost:5000`.

El acceso administrativo usa Supabase Auth con correo y contraseña. Ejecuta el
SQL de `db/init.sql` en Supabase, configura `SUPABASE_URL` y la clave pública
`SUPABASE_ANON_KEY`, y crea la primera cuenta desde `/registro`.

## Estructura del proyecto

```
biblioteca-proyecto/
├── docker-compose.yml
├── .env.example
├── db/
│   └── init.sql            # SQL PostgreSQL para ejecutar en Supabase
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

1. La app web (`/recomendaciones`) envía el usuario, el mensaje y el `session_id`.
2. `agent/main.py` consulta el historial en Supabase PostgreSQL y conserva la sesión
  mediante `InMemoryRunner` para permitir preguntas de seguimiento.
3. El `LlmAgent` usa `buscar_libros_disponibles` y `verificar_disponibilidad` como
  tools reales con function calling; no recibe un catálogo estático inyectado.
4. La pantalla acepta lenguaje natural, como "quiero algo de terror corto", y
  muestra un mensaje amigable si Gemini no está disponible.

## Notas para la entrega

- Cambia las contraseñas de `.env` antes de cualquier despliegue real.
- Las notificaciones usan SMTP si `SMTP_HOST` y `SMTP_FROM` están configurados; si no, se hace fallback a Resend con `RESEND_API_KEY` y `EMAIL_FROM`. Sin ningún proveedor configurado, la gestión funciona normalmente.
- Ejecuta `db/init.sql` en el SQL Editor de Supabase para crear tablas y datos de ejemplo.
- No se necesita un contenedor local de base de datos; `DATABASE_URL` es obligatoria.
