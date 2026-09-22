"""
Módulo de Patrones de Diseño (Singleton y Factory)
Proporciona gestión centralizada de configuración y creación desacoplada de objetos.
"""

from typing import Optional
from src.modelos import Medico, Enfermero, PersonalSalud


class ConfiguracionSistema:
    """Patrón Singleton: Mantiene una única instancia de configuración en memoria."""
    _instancia: Optional['ConfiguracionSistema'] = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super(ConfiguracionSistema, cls).__new__(cls)
            cls._instancia._cargar_valores_defecto()
        return cls._instancia

    def _cargar_valores_defecto(self):
        """Inicializa las variables globales del entorno."""
        self.nombre_puesto = "Puesto de Salud Rural - La Libertad"
        self.hospital_referencia = "Hospital Regional Docente de Trujillo"
        self.url_nube_api = "https://api.sistemarural.gob.pe/v1"
        self.modo_offline = True
        self.version = "1.0.0"


class FabricaPersonalSalud:
    """Patrón Factory: Encargado de instanciar el personal de salud de forma dinámica."""

    @staticmethod
    def crear_personal(tipo: str, nombre: str, dni: str, especialidad_o_turno: str) -> PersonalSalud:
        """
        Instancia un Medico o Enfermero según el parámetro 'tipo'.
        evitando el acoplamiento directo en la capa de presentación o BD.
        """
        tipo_normalizado = tipo.strip().lower()

        if tipo_normalizado == "medico":
            return Medico(nombre=nombre, dni=dni, especialidad=especialidad_o_turno)
        elif tipo_normalizado == "enfermero":
            return Enfermero(nombre=nombre, dni=dni, turno=especialidad_o_turno)
        else:
            raise ValueError(f"Tipo de personal no reconocido: '{tipo}'. Use 'medico' o 'enfermero'.")