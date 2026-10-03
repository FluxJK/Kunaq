"""
Módulo API para la App Móvil del Paciente
Permite la consulta de ficha de salud, historial de atenciones y consultas médicas.
"""

from typing import Dict, Any
from src.base_datos import BaseDatosLocal


class ServicioAppMovilPaciente:
    """Proporciona endpoints de lectura para la aplicación móvil del paciente."""

    def __init__(self, db_local: BaseDatosLocal):
        self.db_local = db_local

    def obtener_ficha_salud(self, dni_hash: str) -> Dict[str, Any]:
        """
        Retorna la ficha médica del paciente identificada por su DNI anonimizado (hash).
        Incluye el total de atenciones y el detalle de cada consulta.
        """
        with self.db_local._obtener_conexion() as conn:
            cursor = conn.cursor()
            
            # Obtener datos generales del paciente
            cursor.execute(
                "SELECT nombre, comunidad, total_atenciones FROM pacientes WHERE dni_hash = ?", 
                (dni_hash,)
            )
            paciente = cursor.fetchone()

            if not paciente:
                return {
                    "status": "error",
                    "mensaje": "No se encontró ninguna ficha médica asociada al identificador."
                }

            # Obtener historial de consultas médicas
            cursor.execute(
                "SELECT medico, diagnostico, fecha, es_emergencia FROM atenciones WHERE dni_hash = ? ORDER BY fecha DESC", 
                (dni_hash,)
            )
            atenciones = cursor.fetchall()

            historial = list(map(lambda a: {
                "medico": a[0],
                "diagnostico": a[1],
                "fecha": a[2],
                "es_emergencia": bool(a[3])
            }, atenciones))

            return {
                "status": "exito",
                "datos_paciente": {
                    "nombre": paciente[0],
                    "comunidad": paciente[1],
                    "total_atenciones_registradas": paciente[2]
                },
                "historial_consultas": historial
            }