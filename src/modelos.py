from abc import ABC, abstractmethod
from src.seguridad import SeguridadesDatos

# ==============================================================================
# ENTIDAD PACIENTE (Encapsulamiento con Atributos Privados)
# ==============================================================================
class Paciente:
    def __init__(self, nombre: str, dni: str, comunidad: str):
        self.__nombre = nombre
        self.__dni_hash = SeguridadesDatos.anonimizar_dni(dni)
        self.__comunidad = comunidad

    def obtener_nombre(self) -> str:
        return self.__nombre

    def obtener_dni_hash(self) -> str:
        return self.__dni_hash

    def obtener_comunidad(self) -> str:
        return self.__comunidad

# ==============================================================================
# JERARQUÍA ABSTRACTA: PERSONAL DE SALUD (Herencia y Polimorfismo)
# ==============================================================================
class PersonalSalud(ABC):
    def __init__(self, nombre: str, dni: str):
        self._nombre = nombre
        self._dni = dni

    @abstractmethod
    def atender(self, paciente: Paciente) -> str:
        pass


class Medico(PersonalSalud):
    def __init__(self, nombre: str, dni: str, especialidad: str):
        super().__init__(nombre, dni)
        self.__especialidad = especialidad

    def atender(self, paciente: Paciente) -> str:
        return (
            f"[MÉDICO]: Dr(a). {self._nombre} ({self.__especialidad})\n"
            f"  ├─ Paciente: {paciente.obtener_nombre()} (DNI Hash: {paciente.obtener_dni_hash()})\n"
            f"  └─ Estado  : Diagnóstico emitido"
        )


class Enfermero(PersonalSalud):
    def __init__(self, nombre: str, dni: str, area_trabajo: str):
        super().__init__(nombre, dni)
        self.__area_trabajo = area_trabajo

    def atender(self, paciente: Paciente) -> str:
        return (
            f"[ENFERMERÍA]: Lic. {self._nombre} ({self.__area_trabajo})\n"
            f"  ├─ Paciente: {paciente.obtener_nombre()} (DNI Hash: {paciente.obtener_dni_hash()})\n"
            f"  └─ Estado  : Triaje y signos vitales registrados"
        )