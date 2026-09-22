-- Esquema PostgreSQL para Supabase.
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    telefono VARCHAR(30),
    fecha_registro DATE DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS libros (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    autor VARCHAR(150) NOT NULL,
    categoria VARCHAR(100),
    isbn VARCHAR(20) UNIQUE,
    copias_totales INTEGER NOT NULL DEFAULT 1 CHECK (copias_totales > 0),
    copias_disponibles INTEGER NOT NULL DEFAULT 1 CHECK (copias_disponibles >= 0)
);

CREATE TABLE IF NOT EXISTS prestamos (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    libro_id INTEGER NOT NULL REFERENCES libros(id),
    fecha_prestamo DATE DEFAULT CURRENT_DATE,
    fecha_limite DATE NOT NULL,
    fecha_devolucion DATE,
    estado VARCHAR(20) NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'devuelto', 'atrasado')),
    confirmacion_enviada BOOLEAN NOT NULL DEFAULT FALSE,
    aviso_vencimiento_enviado BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS reservas (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    libro_id INTEGER NOT NULL REFERENCES libros(id),
    fecha_reserva TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    estado VARCHAR(20) NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'notificada', 'cancelada')),
    UNIQUE (usuario_id, libro_id, estado)
);

INSERT INTO libros (titulo, autor, categoria, isbn, copias_totales, copias_disponibles)
SELECT * FROM (VALUES
    ('Cien años de soledad', 'Gabriel García Márquez', 'Novela', '9780307474728', 3, 3),
    ('1984', 'George Orwell', 'Ciencia ficción', '9780451524935', 2, 2),
    ('El principito', 'Antoine de Saint-Exupéry', 'Infantil', '9780156012195', 4, 4),
    ('Clean Code', 'Robert C. Martin', 'Tecnología', '9780132350884', 2, 2),
    ('Sapiens', 'Yuval Noah Harari', 'Historia', '9780062316097', 2, 2)
) AS datos(titulo, autor, categoria, isbn, copias_totales, copias_disponibles)
WHERE NOT EXISTS (SELECT 1 FROM libros);

INSERT INTO usuarios (nombre, email, telefono)
SELECT * FROM (VALUES
    ('Ana Torres', 'ana.torres@example.com', '5551234567'),
    ('Luis Pérez', 'luis.perez@example.com', '5559876543')
) AS datos(nombre, email, telefono)
WHERE NOT EXISTS (SELECT 1 FROM usuarios);
