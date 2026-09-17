import os
import requests
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
import pymysql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

DB_CONFIG = dict(
    host=os.environ.get("DB_HOST", "127.0.0.1"),
    user=os.environ.get("DB_USER", "root"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "biblioteca"),
    cursorclass=pymysql.cursors.DictCursor,
)

AGENT_URL = os.environ.get("AGENT_URL", "http://127.0.0.1:8001")


def get_conn():
    return pymysql.connect(**DB_CONFIG)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/usuarios")
def usuarios():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM usuarios ORDER BY id")
        rows = cur.fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=rows)


@app.route("/usuarios/nuevo", methods=["POST"])
def nuevo_usuario():
    nombre = request.form["nombre"]
    email = request.form["email"]
    telefono = request.form.get("telefono", "")
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO usuarios (nombre, email, telefono) VALUES (%s, %s, %s)",
            (nombre, email, telefono),
        )
    conn.commit()
    conn.close()
    flash("Usuario registrado correctamente")
    return redirect(url_for("usuarios"))


@app.route("/libros")
def libros():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM libros ORDER BY id")
        rows = cur.fetchall()
    conn.close()
    return render_template("libros.html", libros=rows)


@app.route("/libros/nuevo", methods=["POST"])
def nuevo_libro():
    titulo = request.form["titulo"]
    autor = request.form["autor"]
    categoria = request.form.get("categoria", "")
    isbn = request.form.get("isbn", "")
    copias = int(request.form.get("copias", 1))
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO libros (titulo, autor, categoria, isbn, copias_totales, copias_disponibles)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (titulo, autor, categoria, isbn, copias, copias),
        )
    conn.commit()
    conn.close()
    flash("Libro agregado correctamente")
    return redirect(url_for("libros"))


@app.route("/prestamos")
def prestamos():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT p.id, u.nombre AS usuario, l.titulo AS libro,
                      p.fecha_prestamo, p.fecha_limite, p.fecha_devolucion, p.estado
               FROM prestamos p
               JOIN usuarios u ON u.id = p.usuario_id
               JOIN libros l ON l.id = p.libro_id
               ORDER BY p.id DESC"""
        )
        rows = cur.fetchall()
        cur.execute("SELECT id, nombre FROM usuarios ORDER BY nombre")
        usuarios = cur.fetchall()
        cur.execute("SELECT id, titulo FROM libros WHERE copias_disponibles > 0 ORDER BY titulo")
        libros_disp = cur.fetchall()
    conn.close()
    return render_template("prestamos.html", prestamos=rows, usuarios=usuarios, libros=libros_disp)


@app.route("/prestamos/nuevo", methods=["POST"])
def nuevo_prestamo():
    usuario_id = request.form["usuario_id"]
    libro_id = request.form["libro_id"]
    dias = int(request.form.get("dias", 14))
    fecha_limite = date.today() + timedelta(days=dias)

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT copias_disponibles FROM libros WHERE id = %s FOR UPDATE",
            (libro_id,),
        )
        libro = cur.fetchone()
        if not libro or libro["copias_disponibles"] < 1:
            conn.close()
            flash("No hay copias disponibles de ese libro")
            return redirect(url_for("prestamos"))

        cur.execute(
            """INSERT INTO prestamos (usuario_id, libro_id, fecha_limite, estado)
               VALUES (%s, %s, %s, 'activo')""",
            (usuario_id, libro_id, fecha_limite),
        )
        cur.execute(
            "UPDATE libros SET copias_disponibles = copias_disponibles - 1 WHERE id = %s",
            (libro_id,),
        )
    conn.commit()
    conn.close()
    flash("Préstamo registrado correctamente")
    return redirect(url_for("prestamos"))


@app.route("/prestamos/<int:prestamo_id>/devolver", methods=["POST"])
def devolver_prestamo(prestamo_id):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT libro_id, estado FROM prestamos WHERE id = %s", (prestamo_id,))
        p = cur.fetchone()
        if p and p["estado"] != "devuelto":
            cur.execute(
                "UPDATE prestamos SET estado = 'devuelto', fecha_devolucion = %s WHERE id = %s",
                (date.today(), prestamo_id),
            )
            cur.execute(
                "UPDATE libros SET copias_disponibles = copias_disponibles + 1 WHERE id = %s",
                (p["libro_id"],),
            )
    conn.commit()
    conn.close()
    flash("Devolución registrada")
    return redirect(url_for("prestamos"))


@app.route("/recomendaciones", methods=["GET", "POST"])
def recomendaciones():
    resultado = None
    error = None
    if request.method == "POST":
        usuario_id = request.form["usuario_id"]
        try:
            resp = requests.post(
                f"{AGENT_URL}/recomendar",
                json={"usuario_id": usuario_id},
                timeout=15,
            )
            resp.raise_for_status()
            resultado = resp.json()
        except Exception as exc:
            error = f"No se pudo contactar al agente de IA: {exc}"

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, nombre FROM usuarios ORDER BY nombre")
        usuarios = cur.fetchall()
    conn.close()
    return render_template(
        "recomendaciones.html", usuarios=usuarios, resultado=resultado, error=error
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
