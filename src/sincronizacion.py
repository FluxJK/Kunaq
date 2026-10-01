"""
Módulo de Sincronización y Alertas Prioritarias
Maneja la transferencia de datos diferida (Offline -> Nube) y el envío de alertas de traslado.
"""

from typing import List, Dict
from src.base_datos import BaseDatosLocal
from src.patrones import ConfiguracionSistema


class ServicioSincronizacionNube:
    """Encargado de sincronizar los registros locales con la base de datos central en la nube."""

    def __init__(self, db_local: BaseDatosLocal):
        self.db_local = db_local
        self.config = ConfiguracionSistema()

    def obtener_registros_pendientes(self) -> List[Dict]:
        """Consulta los registros de atenciones que aún no han sido subidos a la nube."""
        cursor = self.db_local._obtener_conexion().cursor()
        cursor.execute("SELECT id, dni_hash, medico, diagnostico, es_emergencia FROM atenciones WHERE sincronizado = 0")
        filas = cursor.fetchall()
        
        # Uso de programación funcional (map) para estructurar el payload ligero
        payload = list(map(lambda x: {
            "id_local": x[0],
            "dni_hash": x[1],
            "medico": x[2],
            "diagnostico": x[3],
            "es_emergencia": bool(x[4])
        }, filas))
        
        return payload

    def ejecutar_sincronizacion(() -> Dict[str, str]:
        """Simula el envío seguro de datos al servidor del Hospital Central."""
        pendientes = self.obtener_registros_pendientes()
        if not pendientes:
            return {"status": "info", "mensaje": "No hay registros pendientes por sincronizar."}

        # Marcar como sincronizados en SQLite local tras confirmación de red
        with self.db_local._obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE atenciones SET sincronizado = 1 WHERE sincronizado = 0")
            conn.commit()

        return {
            "status": "exito",
            "servidor_destino": self.config.hospital_referencia,
            "registros_sincronizados": len(pendientes),
            "mensaje": f"Se sincronizaron {len(pendientes)} registros con la nube exitosamente."
        }


class GestorAlertasEmergencia:
    """Emite alertas inmediatas cuando un paciente requiere traslado urgente a Trujillo."""

    @staticmethod
    def emitir_alerta_traslado(paciente_dni_hash: str, comunidad_origen: str, motivo_urgencia: str) -> Dict:
        alerta = {
            "prioridad": "CRÍTICA / Nivel 1",
            "paciente_hash": paciente_dni_hash,
            "origen": comunidad_origen,
            "destino": "Hospital Regional Docente de Trujillo",
            "motivo": motivo_urgencia,
            "alerta_activa": True
        }
        print(f"\n🚨 [ALERTA DE EMERGENCIA - TRASLADO]: Paciente {paciente_dni_hash[:8]}... enviado desde {comunidad_origen} a Trujillo.")
        return alerta