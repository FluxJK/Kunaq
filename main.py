"""
Punto de Entrada Principal del SistemaRural-PE
Orquesta la inicialización de módulos, patrones de diseño y flujo de atención.
"""

from src.base_datos import BaseDatosLocal
from src.patrones import ConfiguracionSistema, FabricaPersonalSalud
from src.inventario import ControlInventario
from src.sincronizacion import ServicioSincronizacionNube, GestorAlertasEmergencia
from src.api_movil import ServicioAppMovilPaciente
from src.seguridad import AnonimizadorDNI


def ejecutar_demostracion_sistema():
    print("==========================================================")
    print("      SISTEMA RURAL DE SALUD - LA LIBERTAD (PERÚ)")
    print("==========================================================\n")

    # 1. Cargar Configuración Singleton
    config = ConfiguracionSistema()
    print(f"[OK] Sistema inicializado en: {config.nombre_puesto}")
    print(f"[OK] Hospital de Referencia: {config.hospital_referencia}\n")

    # 2. Inicializar Base de Datos Local
    db = BaseDatosLocal()

    # 3. Utilizar Fábrica para instanciar Personal de Salud
    medico = FabricaPersonalSalud.crear_personal(
        tipo="medico", 
        nombre="Dr. Carlos Mendoza", 
        dni="45871239", 
        especialidad_o_turno="Medicina General"
    )
    print(f"[OK] Personal en Turno: {medico.obtener_resumen()}")

    # 4. Anonimizar DNI del Paciente (Seguridad y Privacidad)
    dni_real_paciente = "74125896"
    dni_hash = AnonimizadorDNI.generar_hash_dni(dni_real_paciente)
    print(f"[OK] Paciente Anonimizado (SHA-256): {dni_hash[:16]}...")

    # 5. Registrar Atención Médica Localmente
    atencion_exitosa = db.registrar_atencion(
        dni_hash=dni_hash,
        medico=medico.nombre,
        diagnostico="Resfrío Común / Fiebre Leve",
        es_emergencia=False
    )

    if atencion_exitosa:
        print("[OK] Atención registrada exitosamente en la base de datos local.")

    # 6. Consultar Inventario de Medicamentos
    inventario = ControlInventario()
    chequeo_paracetamol = inventario.verificar_disponibilidad("Paracetamol 500mg", 2)
    print(f"[OK] Control de Inventario: {chequeo_paracetamol['mensaje']}")

    # 7. Ejecutar Sincronización Diferida con la Nube
    sincronizador = ServicioSincronizacionNube(db)
    resumen_sync = sincronizador.ejecutar_sincronizacion()
    print(f"[OK] Sincronización Nube: {resumen_sync['mensaje']}")

    # 8. Probar Servicio API para la App Móvil
    api_movil = ServicioAppMovilPaciente(db)
    ficha = api_movil.obtener_ficha_salud(dni_hash)
    print(f"[OK] Ficha App Móvil Consultada: {len(ficha.get('historial_consultas', []))} atención(es) encontrada(s).")

    print("\n==========================================================")
    print(" Demostración completada con éxito. Listo para ejecución.")
    print("==========================================================")


if __name__ == "__main__":
    ejecutar_demostracion_sistema()