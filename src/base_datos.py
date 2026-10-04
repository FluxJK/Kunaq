"""
Módulo de Persistencia Local (Base de Datos SQLite)
Diseñado para funcionar en equipos de bajos recursos sin dependencias externas.
"""

import sqlite3
import os

class BaseDatosLocal:
    """Clase encargada de gestionar la conexión y operaciones locales."""

    def __init__(self, db_name: str = "sistema_rural.db"):
        self.db_name = db_name
        self._inicializar_tablas()

    def _obtener_conexion(self):
        """Retorna una conexión a la base de datos local SQLite."""
        return sqlite3.connect(self.db_name)

    def _inicializar_tablas(self):
        """Crea las tablas necesarias si no existen."""
        with self._obtener_conexion() as conn:
            cursor = conn.cursor()
            
            # Tabla de pacientes (usa dni_hash para anonimización)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pacientes (
                    dni_hash TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    comunidad TEXT NOT NULL,
                    total_atenciones INTEGER DEFAULT 0
                )
            ''')
            
            # Tabla de atenciones médicas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS atenciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dni_hash TEXT NOT NULL,
                    medico TEXT NOT NULL,
                    diagnostico TEXT NOT NULL,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    es_emergencia INTEGER DEFAULT 0,
                    sincronizado INTEGER DEFAULT 0,
                    FOREIGN KEY (dni_hash) REFERENCES pacientes (dni_hash)
                )
            ''')
            conn.commit()

    def guardar_paciente(self, dni_hash: str, nombre: str, comunidad: str) -> bool:
        """Registra un nuevo paciente en la base local."""
        try:
            with self._obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR IGNORE INTO pacientes (dni_hash, nombre, comunidad) VALUES (?, ?, ?)",
                    (dni_hash, nombre, comunidad)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"Error en BBDD Local: {e}")
            return False

    def registrar_atencion(self, dni_hash: str, medico: str, diagnostico: str, es_emergencia: bool = False) -> bool:
        """Registra una atención médica localmente e incrementa el contador del paciente."""
        try:
            with self._obtener_conexion() as conn:
                cursor = conn.cursor()
                # Insertar atención
                cursor.execute(
                    "INSERT INTO atenciones (dni_hash, medico, diagnostico, es_emergencia) VALUES (?, ?, ?, ?)",
                    (dni_hash, medico, diagnostico, 1 if es_emergencia else 0)
                )
                # Incrementar total de atenciones
                cursor.execute(
                    "UPDATE pacientes SET total_atenciones = total_atenciones + 1 WHERE dni_hash = ?",
                    (dni_hash,)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"Error al registrar atención: {e}")
            return False