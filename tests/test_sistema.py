"""
Pruebas Automatizadas Unitarias con Unittest (Nativo de Python)
Verifica el correcto funcionamiento de seguridad, patrones de diseño e inventario.
"""

import unittest
from src.seguridad import AnonimizadorDNI
from src.patrones import ConfiguracionSistema
from src.inventario import ControlInventario


class TestSistemaRural(unittest.TestCase):

    def test_hash_dni_anonimizado(self):
        """Verifica que el hashing de DNI genera una cadena de 64 caracteres de forma consistente."""
        dni_ejemplo = "73542189"
        hash_1 = AnonimizadorDNI.generar_hash_dni(dni_ejemplo)
        hash_2 = AnonimizadorDNI.generar_hash_dni(dni_ejemplo)

        self.assertEqual(len(hash_1), 64)
        self.assertEqual(hash_1, hash_2)
        self.assertNotEqual(hash_1, dni_ejemplo)

    def test_patron_singleton_configuracion(self):
        """Garantiza que múltiples llamadas a ConfiguracionSistema retornan la misma instancia."""
        config_a = ConfiguracionSistema()
        config_b = ConfiguracionSistema()

        self.assertIs(config_a, config_b)
        self.assertEqual(config_a.hospital_referencia, "Hospital Regional Docente de Trujillo")

    def test_control_inventario_criticos(self):
        """Valida la lógica de filtrado funcional para insumos con stock por debajo del mínimo."""
        inv = ControlInventario()
        criticos = inv.obtener_medicamentos_criticos()

        self.assertIsInstance(criticos, list)
        self.assertGreaterEqual(len(criticos), 1)
        for med in criticos:
            self.assertLess(med["stock"], med["stock_minimo"])


if __name__ == "__main__":
    unittest.main()