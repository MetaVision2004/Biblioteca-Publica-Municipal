import os
import re
import smtplib
import threading
import time
from datetime import date, timedelta
from email.message import EmailMessage

import psycopg
from psycopg.rows import dict_row
import requests
from dotenv import load_dotenv
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
)
DATABASE_URL = os.environ.get("DATABASE_URL", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
AGENT_URL = os.environ.get("AGENT_URL", "http://127.0.0.1:8001")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or "587")
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
SMTP_FROM = os.environ.get("SMTP_FROM") or os.environ.get("EMAIL_FROM", "")


def supabase_auth(path, payload):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL y SUPABASE_ANON_KEY son obligatorias")
    return requests.post(
        f"{SUPABASE_URL}/auth/v1/{path}",
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "access_token" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def require_login():
    public_endpoints = {"health", "login", "registro", "static"}
    if request.endpoint not in public_endpoints and "access_token" not in session:
        return redirect(url_for("login", next=request.path))


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada para Supabase")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def ensure_schema():
    """Create new objects and columns when an existing Docker volume is reused."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS reservas (
            id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            usuario_id INT NOT NULL,
            libro_id INT NOT NULL,
            fecha_reserva TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            estado VARCHAR(20) NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'notificada', 'cancelada')),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (libro_id) REFERENCES libros(id)
        )""")
        for definition in (
            "ADD COLUMN IF NOT EXISTS confirmacion_enviada BOOLEAN NOT NULL DEFAULT FALSE",
            "ADD COLUMN IF NOT EXISTS aviso_vencimiento_enviado BOOLEAN NOT NULL DEFAULT FALSE",
        ):
            cur.execute(f"ALTER TABLE prestamos {definition}")
    conn.commit()
    conn.close()


def enviar_correo(destinatario, asunto, html):
    if not destinatario:
        return False

    if SMTP_HOST and SMTP_FROM:
        try:
            plain_text = re.sub(r"<[^>]+>", " ", html)
            plain_text = re.sub(r"\s+", " ", plain_text).strip()
            message = EmailMessage()
            message["Subject"] = asunto
            message["From"] = SMTP_FROM
            message["To"] = destinatario
            message.set_content(plain_text or asunto)
            message.add_alternative(html, subtype="html")

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                if SMTP_USE_TLS:
                    server.starttls()
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
            return True
        except (smtplib.SMTPException, OSError, ValueError):
            return False

    api_key = os.environ.get("RESEND_API_KEY")
    remitente = os.environ.get("EMAIL_FROM")
    if not api_key or not remitente:
        return False
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"from": remitente, "to": [destinatario], "subject": asunto, "html": html},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        return False


def actualizar_atrasados():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("UPDATE prestamos SET estado='atrasado' WHERE estado='activo' AND fecha_limite < CURRENT_DATE")
    conn.commit()
    conn.close()


def procesar_notificaciones():
    actualizar_atrasados()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""SELECT p.id, p.fecha_limite, u.nombre, u.email, l.titulo
                      FROM prestamos p JOIN usuarios u ON u.id=p.usuario_id JOIN libros l ON l.id=p.libro_id
                      WHERE p.estado='activo' AND p.fecha_limite=CURRENT_DATE + 2
                      AND p.aviso_vencimiento_enviado=FALSE""")
        por_vencer = cur.fetchall()
        cur.execute("""SELECT p.id, u.email, u.nombre, l.titulo FROM prestamos p
                      JOIN usuarios u ON u.id=p.usuario_id JOIN libros l ON l.id=p.libro_id
                      WHERE p.confirmacion_enviada=FALSE""")
        confirmaciones = cur.fetchall()
    conn.close()
    for loan in por_vencer:
        sent = enviar_correo(loan["email"], "Tu préstamo vence pronto", f"<p>Hola {loan['nombre']},</p><p>El préstamo de <strong>{loan['titulo']}</strong> vence el {loan['fecha_limite']}.</p>")
        if sent:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("UPDATE prestamos SET aviso_vencimiento_enviado=TRUE WHERE id=%s", (loan["id"],))
            conn.commit(); conn.close()
    for loan in confirmaciones:
        sent = enviar_correo(loan["email"], "Préstamo registrado", f"<p>Hola {loan['nombre']},</p><p>Tu préstamo de <strong>{loan['titulo']}</strong> ha sido registrado.</p>")
        if sent:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("UPDATE prestamos SET confirmacion_enviada=TRUE WHERE id=%s", (loan["id"],))
            conn.commit(); conn.close()


def iniciar_tarea_programada():
    def tarea():
        while True:
            try:
                procesar_notificaciones()
            except Exception:
                pass
            time.sleep(3600)

    threading.Thread(target=tarea, daemon=True, name="biblioteca-notificaciones").start()


ensure_schema()
iniciar_tarea_programada()


def safe_next_url():
    target = request.args.get("next") or request.form.get("next")
    return target if target and target.startswith("/") and not target.startswith("//") else url_for("index")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "access_token" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        try:
            response = supabase_auth("token?grant_type=password", {
                "email": request.form["email"].strip(),
                "password": request.form["password"],
            })
            if response.ok:
                data = response.json()
                session.clear()
                session["access_token"] = data["access_token"]
                session["user"] = data.get("user", {})
                return redirect(safe_next_url())
            flash("Correo o contraseña incorrectos")
        except (requests.RequestException, RuntimeError):
            flash("No se pudo conectar con Supabase Auth")
    return render_template("login.html", mode="login", next_url=request.args.get("next", ""))


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if "access_token" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        try:
            response = supabase_auth("signup", {
                "email": request.form["email"].strip(),
                "password": request.form["password"],
            })
            if response.ok:
                data = response.json()
                if data.get("access_token"):
                    session["access_token"] = data["access_token"]
                    session["user"] = data.get("user", {})
                    return redirect(url_for("index"))
                flash("Cuenta creada. Revisa tu correo para confirmarla y después inicia sesión.")
                return redirect(url_for("login"))
            flash("No se pudo crear la cuenta. Revisa el correo y la contraseña.")
        except (requests.RequestException, RuntimeError):
            flash("No se pudo conectar con Supabase Auth")
    return render_template("login.html", mode="register", next_url="")


@app.post("/logout")
def logout():
    access_token = session.get("access_token")
    if access_token and SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            requests.post(
                f"{SUPABASE_URL}/auth/v1/logout",
                headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
        except requests.RequestException:
            pass
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    actualizar_atrasados()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM usuarios")
        usuarios_total = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total, COALESCE(SUM(copias_disponibles),0) AS disponibles FROM libros")
        libros_resumen = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS total FROM prestamos WHERE estado='activo'")
        prestamos_activos = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS total FROM prestamos WHERE estado='atrasado'")
        prestamos_atrasados = cur.fetchone()["total"]
    conn.close()
    return render_template("index.html", usuarios_total=usuarios_total, libros_total=libros_resumen["total"],
                           copias_disponibles=libros_resumen["disponibles"], prestamos_activos=prestamos_activos,
                           prestamos_atrasados=prestamos_atrasados)


@app.route("/dashboard")
def dashboard():
    actualizar_atrasados()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""SELECT l.titulo, l.autor, COUNT(p.id) AS total FROM prestamos p
                      JOIN libros l ON l.id=p.libro_id GROUP BY l.id ORDER BY total DESC, l.titulo LIMIT 5""")
        libros_populares = cur.fetchall()
        cur.execute("""SELECT u.nombre, COUNT(p.id) AS total FROM prestamos p JOIN usuarios u ON u.id=p.usuario_id
                      GROUP BY u.id ORDER BY total DESC, u.nombre LIMIT 5""")
        usuarios_activos = cur.fetchall()
        cur.execute("SELECT estado, COUNT(*) AS total FROM prestamos GROUP BY estado")
        totales_estado = {row["estado"]: row["total"] for row in cur.fetchall()}
    conn.close()
    return render_template("dashboard.html", libros_populares=libros_populares, usuarios_activos=usuarios_activos,
                           totales_estado=totales_estado)


@app.route("/usuarios")
def usuarios():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM usuarios ORDER BY id")
        rows = cur.fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=rows)


@app.post("/usuarios/nuevo")
def nuevo_usuario():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO usuarios (nombre,email,telefono) VALUES (%s,%s,%s)",
                    (request.form["nombre"], request.form["email"], request.form.get("telefono", "")))
    conn.commit(); conn.close(); flash("Usuario registrado correctamente")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>")
def historial_usuario(usuario_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM usuarios WHERE id=%s", (usuario_id,)); usuario = cur.fetchone()
        cur.execute("""SELECT p.*, l.titulo FROM prestamos p JOIN libros l ON l.id=p.libro_id
                      WHERE p.usuario_id=%s ORDER BY p.fecha_prestamo DESC""", (usuario_id,))
        prestamos_usuario = cur.fetchall()
    conn.close()
    if not usuario:
        flash("Usuario no encontrado"); return redirect(url_for("usuarios"))
    return render_template("usuario_historial.html", usuario=usuario, prestamos=prestamos_usuario)


@app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
def editar_usuario(usuario_id):
    conn = get_conn()
    if request.method == "POST":
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET nombre=%s,email=%s,telefono=%s WHERE id=%s",
                        (request.form["nombre"], request.form["email"], request.form.get("telefono", ""), usuario_id))
        conn.commit(); conn.close(); flash("Usuario actualizado correctamente")
        return redirect(url_for("usuarios"))
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM usuarios WHERE id=%s", (usuario_id,)); usuario = cur.fetchone()
    conn.close()
    return render_template("editar_usuario.html", usuario=usuario)


@app.post("/usuarios/<int:usuario_id>/eliminar")
def eliminar_usuario(usuario_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM prestamos WHERE usuario_id=%s AND estado IN ('activo','atrasado')", (usuario_id,))
        if cur.fetchone()["total"]:
            conn.close(); flash("No se puede eliminar un usuario con préstamos pendientes"); return redirect(url_for("usuarios"))
        try:
            cur.execute("DELETE FROM usuarios WHERE id=%s", (usuario_id,)); conn.commit()
        except psycopg.errors.ForeignKeyViolation:
            conn.rollback(); conn.close(); flash("No se puede eliminar un usuario con historial de préstamos"); return redirect(url_for("usuarios"))
    conn.close(); flash("Usuario eliminado")
    return redirect(url_for("usuarios"))


@app.route("/libros")
def libros():
    busqueda = request.args.get("q", "").strip(); categoria = request.args.get("categoria", "").strip()
    conn = get_conn()
    with conn.cursor() as cur:
        query = "SELECT * FROM libros WHERE (titulo ILIKE %s OR autor ILIKE %s)"; params = [f"%{busqueda}%", f"%{busqueda}%"]
        if categoria:
            query += " AND categoria=%s"; params.append(categoria)
        cur.execute(query + " ORDER BY titulo", params); rows = cur.fetchall()
        cur.execute("SELECT DISTINCT categoria FROM libros WHERE categoria IS NOT NULL AND categoria<>'' ORDER BY categoria")
        categorias = [row["categoria"] for row in cur.fetchall()]
        cur.execute("SELECT id,nombre FROM usuarios ORDER BY nombre"); usuarios_lista = cur.fetchall()
    conn.close()
    return render_template("libros.html", libros=rows, categorias=categorias, usuarios=usuarios_lista,
                           busqueda=busqueda, categoria=categoria)


@app.post("/libros/nuevo")
def nuevo_libro():
    copias = int(request.form.get("copias", 1)); conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO libros (titulo,autor,categoria,isbn,copias_totales,copias_disponibles)
                      VALUES (%s,%s,%s,%s,%s,%s)""", (request.form["titulo"], request.form["autor"],
                      request.form.get("categoria", ""), request.form.get("isbn", "") or None, copias, copias))
    conn.commit(); conn.close(); flash("Libro agregado correctamente")
    return redirect(url_for("libros"))


@app.route("/libros/<int:libro_id>/editar", methods=["GET", "POST"])
def editar_libro(libro_id):
    conn = get_conn()
    if request.method == "POST":
        copias_totales = int(request.form["copias_totales"])
        with conn.cursor() as cur:
            cur.execute("SELECT copias_totales,copias_disponibles FROM libros WHERE id=%s", (libro_id,)); actual = cur.fetchone()
            prestadas = actual["copias_totales"] - actual["copias_disponibles"]
            if copias_totales < prestadas:
                conn.close(); flash("Las copias totales no pueden ser menores que las prestadas"); return redirect(url_for("editar_libro", libro_id=libro_id))
            cur.execute("""UPDATE libros SET titulo=%s,autor=%s,categoria=%s,isbn=%s,copias_totales=%s,
                          copias_disponibles=%s WHERE id=%s""", (request.form["titulo"], request.form["autor"],
                          request.form.get("categoria", ""), request.form.get("isbn", "") or None, copias_totales,
                          copias_totales - prestadas, libro_id))
        conn.commit(); conn.close(); flash("Libro actualizado correctamente")
        return redirect(url_for("libros"))
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM libros WHERE id=%s", (libro_id,)); libro = cur.fetchone()
    conn.close()
    return render_template("editar_libro.html", libro=libro)


@app.post("/libros/<int:libro_id>/eliminar")
def eliminar_libro(libro_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM prestamos WHERE libro_id=%s AND estado IN ('activo','atrasado')", (libro_id,))
        if cur.fetchone()["total"]:
            conn.close(); flash("No se puede eliminar un libro con préstamos activos o atrasados"); return redirect(url_for("libros"))
        try:
            cur.execute("DELETE FROM libros WHERE id=%s", (libro_id,)); conn.commit()
        except psycopg.errors.ForeignKeyViolation:
            conn.rollback(); conn.close(); flash("No se puede eliminar un libro que tiene historial de préstamos"); return redirect(url_for("libros"))
    conn.close(); flash("Libro eliminado")
    return redirect(url_for("libros"))


@app.post("/reservas/nueva")
def nueva_reserva():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT copias_disponibles FROM libros WHERE id=%s", (request.form["libro_id"],)); libro = cur.fetchone()
            if not libro or libro["copias_disponibles"] > 0:
                flash("Ese libro ya tiene copias disponibles")
            else:
                cur.execute("SELECT id FROM reservas WHERE usuario_id=%s AND libro_id=%s AND estado='activa'", (request.form["usuario_id"], request.form["libro_id"]))
                if cur.fetchone():
                    flash("Ya existe una reserva activa para este usuario")
                else:
                    cur.execute("INSERT INTO reservas (usuario_id,libro_id) VALUES (%s,%s)", (request.form["usuario_id"], request.form["libro_id"]))
                    conn.commit(); flash("Reserva registrada en la lista de espera")
    finally:
        conn.close()
    return redirect(url_for("libros"))


@app.route("/prestamos")
def prestamos():
    actualizar_atrasados(); conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""SELECT p.id,u.nombre AS usuario,l.titulo AS libro,p.fecha_prestamo,p.fecha_limite,
                      p.fecha_devolucion,p.estado FROM prestamos p JOIN usuarios u ON u.id=p.usuario_id
                      JOIN libros l ON l.id=p.libro_id ORDER BY p.id DESC""")
        rows = cur.fetchall()
        cur.execute("SELECT id,nombre FROM usuarios ORDER BY nombre"); usuarios_lista = cur.fetchall()
        cur.execute("SELECT id,titulo FROM libros WHERE copias_disponibles>0 ORDER BY titulo"); libros_disp = cur.fetchall()
    conn.close()
    return render_template("prestamos.html", prestamos=rows, usuarios=usuarios_lista, libros=libros_disp)


@app.post("/prestamos/nuevo")
def nuevo_prestamo():
    usuario_id, libro_id = request.form["usuario_id"], request.form["libro_id"]
    fecha_limite = date.today() + timedelta(days=int(request.form.get("dias", 14)))
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT copias_disponibles FROM libros WHERE id=%s FOR UPDATE", (libro_id,)); libro = cur.fetchone()
        if not libro or libro["copias_disponibles"] < 1:
            conn.close(); flash("No hay copias disponibles de ese libro"); return redirect(url_for("prestamos"))
        cur.execute("INSERT INTO prestamos (usuario_id,libro_id,fecha_limite) VALUES (%s,%s,%s)", (usuario_id, libro_id, fecha_limite))
        cur.execute("UPDATE libros SET copias_disponibles=copias_disponibles-1 WHERE id=%s", (libro_id,))
    conn.commit(); conn.close(); procesar_notificaciones(); flash("Préstamo registrado correctamente")
    return redirect(url_for("prestamos"))


@app.post("/prestamos/<int:prestamo_id>/devolver")
def devolver_prestamo(prestamo_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT libro_id,estado FROM prestamos WHERE id=%s", (prestamo_id,)); loan = cur.fetchone()
        waiting = None
        if loan and loan["estado"] != "devuelto":
            cur.execute("UPDATE prestamos SET estado='devuelto',fecha_devolucion=%s WHERE id=%s", (date.today(), prestamo_id))
            cur.execute("UPDATE libros SET copias_disponibles=copias_disponibles+1 WHERE id=%s", (loan["libro_id"],))
            cur.execute("""SELECT r.id,u.email,u.nombre,l.titulo FROM reservas r JOIN usuarios u ON u.id=r.usuario_id
                          JOIN libros l ON l.id=r.libro_id WHERE r.libro_id=%s AND r.estado='activa'
                          ORDER BY r.fecha_reserva LIMIT 1""", (loan["libro_id"],)); waiting = cur.fetchone()
    conn.commit(); conn.close()
    if waiting:
        notified = enviar_correo(waiting["email"], "Tu reserva ya está disponible", f"<p>Hola {waiting['nombre']},</p><p>Ya hay una copia disponible de <strong>{waiting['titulo']}</strong>.</p>")
        if notified:
            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute("UPDATE reservas SET estado='notificada' WHERE id=%s", (waiting["id"],))
            conn.commit(); conn.close()
            flash("Devolución registrada y primera reserva notificada")
        else:
            flash("Devolución registrada; la reserva queda pendiente de notificación")
    else:
        flash("Devolución registrada")
    return redirect(url_for("prestamos"))


@app.route("/recomendaciones", methods=["GET", "POST"])
def recomendaciones():
    resultado = error = None
    usuario_id = request.form.get("usuario_id", "")
    mensaje = request.form.get("mensaje", "Recomiéndame una lectura según mi historial.").strip()
    session_id = request.form.get("session_id", "") or None
    if request.method == "POST":
        try:
            resp = requests.post(
                f"{AGENT_URL}/recomendar",
                json={"usuario_id": usuario_id, "mensaje": mensaje, "session_id": session_id},
                timeout=(5, 60),
            )
            resp.raise_for_status(); resultado = resp.json()
            session_id = resultado.get("session_id") or session_id
        except Exception as exc:
            error = "El asistente no está disponible en este momento. Inténtalo de nuevo en unos segundos."
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id,nombre FROM usuarios ORDER BY nombre"); usuarios_lista = cur.fetchall()
    conn.close()
    return render_template("recomendaciones.html", usuarios=usuarios_lista, resultado=resultado, error=error,
                           usuario_id=usuario_id, mensaje=mensaje, session_id=session_id)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
