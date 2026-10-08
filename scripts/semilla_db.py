import os, sys, sqlite3
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # permite ejecutarlo desde cualquier carpeta
from cryptography.fernet import Fernet
from utils.seguridad import SeguridadKunaq
from models.inventario_base import INVENTARIO_BASE

def poblar_base_datos():
    # Generar llave para la demostración (en prod va en .env)
    llave_demo = Fernet.generate_key()
    seguridad = SeguridadKunaq(llave_demo)
    
    print(f"LLAVE MAESTRA (Guárdala para el panel): {llave_demo.decode()}")

    conexion = sqlite3.connect('kunaq_local.db')
    cursor = conexion.cursor()
    
    # Crear tabla estructurada
    cursor.execute('''CREATE TABLE IF NOT EXISTS pacientes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre TEXT,
                        dni_hash TEXT,
                        historial_cifrado BLOB,
                        es_emergencia INTEGER)''')

    # Inventario de medicamentos (20 productos; mismo listado que usa el panel web)
    cursor.execute('''CREATE TABLE IF NOT EXISTS inventario (
                        id INTEGER PRIMARY KEY,
                        nombre TEXT,
                        categoria TEXT,
                        stock INTEGER,
                        minimo INTEGER,
                        unidad TEXT,
                        ubicacion TEXT)''')
    if cursor.execute("SELECT COUNT(*) FROM inventario").fetchone()[0] == 0:
        cursor.executemany("INSERT INTO inventario VALUES (?, ?, ?, ?, ?, ?, ?)", INVENTARIO_BASE)
        print(f"Inventario sembrado con {len(INVENTARIO_BASE)} medicamentos.")

    # Data predeterminada: 8 Casos regulares, 2 Emergencias
    data_pacientes = [
        ("Juan Quispe", "70123456", "Control de niño sano - Estable", False),
        ("Maria Condori", "70123457", "Gripe leve - Paracetamol recetado", False),
        ("Pedro Mamani", "70123458", "Anemia moderada - Suplemento hierro", False),
        ("Ana Cusi", "70123459", "Control de presión arterial", False),
        ("Luis Vargas", "70123460", "Revisión odontológica", False),
        ("Rosa Flores", "70123461", "Vacunación COVID-19", False),
        ("Carlos Rojas", "70123462", "Dolor lumbar crónico", False),
        ("Carmen Tito", "70123463", "Asma controlada", False),
        # EMERGENCIAS CRÍTICAS
        ("Emergencia Desconocido", "00000001", "Shock Anafiláctico - URGENTE UCI", True),
        ("Lucia Ramos", "70123464", "Gestante 38 sem - Hemorragia Severa", True)
    ]

    try:
        for nombre, dni, historial, emergencia in data_pacientes:
            dni_h = seguridad.hashear_dni(dni)
            historial_c = seguridad.encriptar_historial(historial)
            cursor.execute("INSERT INTO pacientes (nombre, dni_hash, historial_cifrado, es_emergencia) VALUES (?, ?, ?, ?)",
                           (nombre, dni_h, historial_c, 1 if emergencia else 0))
        conexion.commit()
        print("Base de datos sembrada con 10 perfiles exitosamente.")
    except Exception as e:
        print(f"Error insertando datos: {e}")
    finally:
        conexion.close()

if __name__ == "__main__":
    poblar_base_datos()