# 1. HERENCIA Y ENCAPSULAMIENTO
class Persona:
    def __init__(self, nombres: str):
        self._nombres = nombres # Atributo protegido

    def obtener_identidad(self) -> str:
        return self._nombres

class FichaMedica: # Para Composición
    def __init__(self, diagnostico_cifrado: bytes, es_emergencia: bool):
        self.diagnostico = diagnostico_cifrado
        self.es_emergencia = es_emergencia

class Paciente(Persona):
    def __init__(self, nombres: str, dni_hash: str, ficha: FichaMedica):
        super().__init__(nombres)
        self.__dni_hash = dni_hash # Atributo privado
        self.ficha = ficha         # 2. COMPOSICIÓN

    # 3. POLIMORFISMO
    def obtener_identidad(self) -> str:
        return f"Paciente: {self._nombres} (DNI Protegido)"

# --- CONTROLADOR (Aplicando map y filter) ---
class GestorPacientes:
    def __init__(self, pacientes: list):
        self.pacientes = pacientes

    def extraer_emergencias_criticas(self) -> list:
        """Uso de Función de Orden Superior: filter + lambda"""
        try:
            emergencias = list(filter(lambda p: p.ficha.es_emergencia, self.pacientes))
            return emergencias
        except Exception as e:
            print(f"Fallo al filtrar emergencias: {e}")
            return []

    def generar_reporte_nombres(self) -> list:
        """Uso de Función de Orden Superior: map + lambda"""
        try:
            nombres = list(map(lambda p: p.obtener_identidad(), self.pacientes))
            return nombres
        except Exception as e:
            print(f"Fallo al mapear nombres: {e}")
            return []


# =====================================================================
#  RED DE EMERGENCIAS (NUEVO)
#  Dispositivos vinculados + Controlador con Funciones de Orden Superior
# =====================================================================
import math
from functools import reduce

CAPACIDADES = {
    "UCI": "UCI",
    "VENTILADOR": "Ventilador mecánico",
    "QUIROFANO": "Quirófano",
    "OBSTETRICIA": "Sala de partos / Gineco-obstetricia",
    "NEONATOLOGIA": "Neonatología",
    "BANCO_SANGRE": "Banco de sangre",
    "TOMOGRAFO": "Tomógrafo",
    "TRAUMA": "Trauma shock",
}

class Dispositivo:
    """Un equipo (PC) vinculado a la red Kunaq: posta, centro de salud u hospital."""

    def __init__(self, id: str, nombre: str, tipo: str, categoria: str = "I-1",
                 capacidades=None, camas_uci: int = 0, lat=None, lng=None,
                 visto_hace: float = 0):
        self.id = id
        self.nombre = nombre
        self.tipo = tipo                       # POSTA | CENTRO_SALUD | HOSPITAL
        self.categoria = categoria             # categoría MINSA: I-1 ... III-2
        self.capacidades = list(capacidades or [])
        self.camas_uci = int(camas_uci or 0)
        self.lat = lat
        self.lng = lng
        self.visto_hace = visto_hace           # segundos desde su última señal

    @property
    def nivel(self) -> int:
        """I -> 1, II -> 2, III -> 3 (según la categoría MINSA)."""
        return {"I": 1, "II": 2, "III": 3}.get(self.categoria.split("-")[0], 1)

    @property
    def senal(self) -> str:
        if self.visto_hace <= 45:
            return "en_linea"
        if self.visto_hace <= 180:
            return "debil"
        return "sin_senal"

    @staticmethod
    def desde_dict(d: dict) -> "Dispositivo":
        return Dispositivo(d["id"], d["nombre"], d["tipo"], d.get("categoria", "I-1"),
                           d.get("capacidades"), d.get("camas_uci", 0),
                           d.get("lat"), d.get("lng"), d.get("visto_hace", 0))


class ControladorEmergencias:
    """CONTROLADOR con Funciones de Orden Superior.

    Decide a qué hospital enviar una emergencia. Todo se resuelve combinando
    funciones: filter + map + sorted(key=lambda) + reduce, y 'fábricas de
    predicados' (funciones que DEVUELVEN otras funciones).
    El mismo algoritmo existe en JavaScript (assets/kunaq-core.js) para que la
    posta pueda decidir aunque no tenga internet.
    """

    # --- Fábricas de predicados (HOF que retornan funciones) -----------
    @staticmethod
    def es_receptor(d: Dispositivo) -> bool:
        return d.tipo == "HOSPITAL"

    @staticmethod
    def esta_vivo(d: Dispositivo) -> bool:
        return d.senal != "sin_senal"

    @staticmethod
    def no_excluido(ids):
        return lambda d: d.id not in ids

    @staticmethod
    def cumple_todo(requisitos):
        return lambda d: all(r in d.capacidades for r in requisitos)

    # --- Utilitario matemático -----------------------------------------
    @staticmethod
    def distancia_km(a: Dispositivo, b: Dispositivo):
        if None in (a.lat, a.lng, b.lat, b.lng):
            return None
        p1, p2 = math.radians(a.lat), math.radians(b.lat)
        dphi, dlam = p2 - p1, math.radians(b.lng - a.lng)
        h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
        return 2 * 6371 * math.asin(math.sqrt(h))

    # --- Función que devuelve una función de puntuación ----------------
    @staticmethod
    def puntuar(requisitos, origen: Dispositivo = None):
        def _puntuar(d: Dispositivo) -> dict:
            cubiertos = list(filter(lambda r: r in d.capacidades, requisitos))
            faltantes = list(filter(lambda r: r not in d.capacidades, requisitos))
            cobertura = len(cubiertos) / len(requisitos) if requisitos else 1
            dist = ControladorEmergencias.distancia_km(origen, d) if origen else None
            puntaje = (100 * cobertura
                       + 12 * d.nivel
                       + (3 * min(d.camas_uci, 5) if "UCI" in requisitos else 0)
                       - (0.5 * min(dist, 100) if dist is not None else 0)
                       - (40 if d.senal == "debil" else 0))
            return {"dispositivo": d, "puntaje": round(puntaje, 1), "cobertura": cobertura,
                    "cumple_todo": not faltantes, "faltantes": faltantes,
                    "distancia_km": None if dist is None else round(dist, 1)}
        return _puntuar

    # --- Pipeline principal --------------------------------------------
    @staticmethod
    def ranking(dispositivos, requisitos, origen=None, excluir=()):
        C = ControladorEmergencias
        candidatos = list(filter(C.es_receptor, dispositivos))                 # filter
        candidatos = list(filter(C.no_excluido(set(excluir)), candidatos))     # filter
        vivos = list(filter(C.esta_vivo, candidatos)) or candidatos            # filter (con respaldo)
        evaluados = list(map(C.puntuar(requisitos, origen), vivos))            # map
        return sorted(evaluados, key=lambda e: e["puntaje"], reverse=True)     # sorted + lambda

    @staticmethod
    def elegir_mejor(ranking: list):
        """reduce: se queda con el mejor puntaje de la lista."""
        return reduce(lambda a, b: b if b["puntaje"] > a["puntaje"] else a, ranking) if ranking else None

    @staticmethod
    def contar_por_prioridad(emergencias) -> dict:
        """reduce: cuántas emergencias hay de cada prioridad (I, II, III)."""
        def acumular(acc, e):
            acc[e["prioridad"]] = acc.get(e["prioridad"], 0) + 1
            return acc
        return reduce(acumular, emergencias, {})
