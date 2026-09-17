-- Esquema inicial: Biblioteca Pública Municipal
CREATE DATABASE IF NOT EXISTS biblioteca CHARACTER SET utf8mb4;
USE biblioteca;

CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    telefono VARCHAR(30),
    fecha_registro DATE DEFAULT (CURRENT_DATE)
);

CREATE TABLE libros (
    id INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    autor VARCHAR(150) NOT NULL,
    categoria VARCHAR(100),
    isbn VARCHAR(20) UNIQUE,
    copias_totales INT NOT NULL DEFAULT 1,
    copias_disponibles INT NOT NULL DEFAULT 1
);

CREATE TABLE prestamos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    libro_id INT NOT NULL,
    fecha_prestamo DATE DEFAULT (CURRENT_DATE),
    fecha_limite DATE NOT NULL,
    fecha_devolucion DATE NULL,
    estado ENUM('activo', 'devuelto', 'atrasado') DEFAULT 'activo',
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    FOREIGN KEY (libro_id) REFERENCES libros(id)
);

-- Datos de ejemplo
INSERT INTO libros (titulo, autor, categoria, isbn, copias_totales, copias_disponibles) VALUES
('Cien años de soledad', 'Gabriel García Márquez', 'Novela', '9780307474728', 3, 3),
('1984', 'George Orwell', 'Ciencia ficción', '9780451524935', 2, 2),
('El principito', 'Antoine de Saint-Exupéry', 'Infantil', '9780156012195', 4, 4),
('Clean Code', 'Robert C. Martin', 'Tecnología', '9780132350884', 2, 2),
('Sapiens', 'Yuval Noah Harari', 'Historia', '9780062316097', 2, 2);

INSERT INTO usuarios (nombre, email, telefono) VALUES
('Ana Torres', 'ana.torres@example.com', '5551234567'),
('Luis Pérez', 'luis.perez@example.com', '5559876543');
