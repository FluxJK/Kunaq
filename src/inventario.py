"""
Módulo de Gestión de Inventario y Stock de Medicamentos
Aplica programación funcional (map/filter) para el control inmutable de insumos médicos.
"""

from typing import List, Dict


class ControlInventario:
    """Gestiona la existencia y disponibilidad de medicamentos en el centro rural."""

    def __init__(self):
        # Stock inicial simulado
        self._inventario = [
            {"id": "MED01", "nombre": "Paracetamol 500mg", "stock": 150, "stock_minimo": 30},
            {"id": "MED02", "nombre": "Amoxicilina 500mg", "stock": 12, "stock_minimo": 25},
            {"id": "MED03", "nombre": "Ibuprofeno 400mg", "stock": 80, "stock_minimo": 20},
            {"id": "MED04", "nombre": "Suero Oral Rehidratante", "stock": 5, "stock_minimo": 15},
            {"id": "MED05", "nombre": "Azitromicina 500mg", "stock": 40, "stock_minimo": 10}
        ]

    def obtener_todo_el_inventario(self) -> List[Dict]:
        """Retorna la lista completa de medicamentos registrados."""
        return self._inventario

    def verificar_disponibilidad(self, nombre_medicina: str, cantidad_requerida: int) -> Dict:
        """Verifica si existe suficiente stock para entregar al paciente."""
        medicina = next((m for m in self._inventario if m["nombre"].lower() == nombre_medicina.lower()), None)
        
        if not medicina:
            return {"disponible": False, "mensaje": f"El medicamento '{nombre_medicina}' no existe en el catálogo."}
        
        if medicina["stock"] >= cantidad_requerida:
            return {
                "disponible": True, 
                "stock_actual": medicina["stock"],
                "mensaje": f"Stock suficiente ({medicina['stock']} unidades disponibles)."
            }
        
        return {
            "disponible": False, 
            "stock_actual": medicina["stock"],
            "mensaje": f"Stock insuficiente. Solo quedan {medicina['stock']} unidades disponibles."
        }

    def obtener_medicamentos_criticos(self) -> List[Dict]:
        """Uso de PROGRAMACIÓN FUNCIONAL (filter): Filtra insumos con stock por debajo del mínimo."""
        meds_criticos = list(filter(lambda m: m["stock"] < m["stock_minimo"], self._inventario))
        return meds_criticos

    def generar_resumen_proyectado(self) -> List[Dict]:
        """Uso de PROGRAMACIÓN FUNCIONAL (map): Retorna estado estructurado del inventario."""
        return list(map(lambda m: {
            "codigo": m["id"],
            "insumo": m["nombre"],
            "cantidad": m["stock"],
            "requiere_reposicion": m["stock"] < m["stock_minimo"]
        }, self._inventario))