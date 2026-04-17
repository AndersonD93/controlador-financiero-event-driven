"""
Tests unitarios para calcular_monto_seguro en ConsolidaMovimientosFinancieros.py

Modelo mental correcto:
  - ProyeccionesFijas inserta conceptos con valor POSITIVO (ej: AUTOMOVIL = 160.000)
  - ConsolidaMovimientosFinancieros los escribe en FlujoDeCaja como POSITIVOS
    → GASTO#AUTOMOVIL = +160.000
  - Cuando llega un gasto real de -100.000 desde KUBO, CUENTA_DISMINUYE_GASTO
    aplica DECREMENTAR sobre la proyección:
    → aplicar_operacion: abs(-100.000) * -1 = -100.000
    → ADD -100.000 sobre +160.000 = +60.000 ✅ (quedan 60k por gastar)
  - Si el gasto real es -170.000:
    → DECREMENTAR: -170.000
    → ADD -170.000 sobre +160.000 = -10.000 ❌ (pasó a negativo)
    → calcular_monto_seguro ajusta a -160.000 (llega exactamente a 0)

  Lo mismo aplica a INGRESO HOGAR con INGRESO_HOGAR_DISMINUYE_PROYECCION:
  - Proyección INGRESO HOGAR = +2.492.820 (ingreso esperado)
  - Ingreso real +2.600.000 → DECREMENTAR -2.600.000
  - ADD -2.600.000 sobre +2.492.820 = -107.180 ❌
  - calcular_monto_seguro ajusta a -2.492.820 (llega a 0)
"""

import sys
import os
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../layer/python"))


class TestCalcularMontoSeguro(unittest.TestCase):

    def setUp(self):
        self.patches = [
            patch.dict("os.environ", {"flujo_caja_table": "FlujoDeCaja_test"}),
            patch("boto3.resource"),
            patch("boto3.client"),
            patch("catalogo_financiero.cargar_catalogo", return_value={}),
            patch("catalogo_financiero.resolver_tipo_cuenta", return_value=None),
        ]
        for p in self.patches:
            p.start()

        import boto3
        self.mock_table = MagicMock()
        boto3.resource.return_value.Table.return_value = self.mock_table

        import importlib
        import terraform.templates.lambdas_code.ConsolidaMovimientosFinancieros as cm
        importlib.reload(cm)
        self.cm = cm

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _set_valor_actual(self, valor):
        self.mock_table.get_item.return_value = {
            "Item": {"valor": Decimal(str(valor))}
        }

    def _set_item_no_existe(self):
        self.mock_table.get_item.return_value = {"Item": None}

    # ─── Gasto real < proyección: pasa completo ─────────────────────────────

    def test_gasto_menor_a_proyeccion_pasa_completo(self):
        """
        Proyección AUTOMOVIL en FlujoDeCaja: +160.000
        Gasto real: -100.000 → DECREMENTAR aplica -100.000
        resultado = +160.000 + (-100.000) = +60.000 → no pasa de 0 → pasa completo
        Proyección queda en +60.000 (aún hay 60k pendientes de gastar)
        """
        self._set_valor_actual(160000)
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#AUTOMOVIL", Decimal("-100000"))
        self.assertEqual(monto, Decimal("-100000"))

    # ─── Gasto real == proyección exacta: llega a cero ──────────────────────

    def test_gasto_igual_a_proyeccion_llega_a_cero(self):
        """
        Proyección AUTOMOVIL: +160.000
        Gasto real: -160.000 → DECREMENTAR aplica -160.000
        resultado = +160.000 + (-160.000) = 0 → exactamente 0, no activa ajuste
        """
        self._set_valor_actual(160000)
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#AUTOMOVIL", Decimal("-160000"))
        self.assertEqual(monto, Decimal("-160000"))

    # ─── Gasto real > proyección: ajusta para no pasar de cero ──────────────

    def test_gasto_mayor_a_proyeccion_ajusta_a_cero(self):
        """
        Proyección AUTOMOVIL: +160.000
        Gasto real: -170.000 → DECREMENTAR aplica -170.000
        resultado = +160.000 + (-170.000) = -10.000 → pasa de 0 → AJUSTAR
        monto_ajustado = 0 - 160.000 = -160.000
        Cuenta KUBO sí recibe los -170.000 completos (eso lo maneja la otra acción)
        Proyección queda en 0
        """
        self._set_valor_actual(160000)
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#AUTOMOVIL", Decimal("-170000"))
        self.assertEqual(monto, Decimal("-160000"))

    def test_gasto_muy_superior_a_proyeccion_ajusta_a_cero(self):
        """
        Proyección AUTOMOVIL: +160.000
        Gasto real: -500.000 → DECREMENTAR aplica -500.000
        resultado = +160.000 + (-500.000) = -340.000 → pasa de 0 → AJUSTAR
        monto_ajustado = -160.000
        """
        self._set_valor_actual(160000)
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#AUTOMOVIL", Decimal("-500000"))
        self.assertEqual(monto, Decimal("-160000"))

    # ─── Proyección ya en cero: bloquea cualquier decremento ────────────────

    def test_proyeccion_en_cero_bloquea_decremento(self):
        """
        Proyección AUTOMOVIL: 0 (ya completamente consumida)
        Gasto real: -50.000 → DECREMENTAR aplica -50.000
        resultado = 0 + (-50.000) = -50.000 → pasa de 0 → AJUSTAR a 0
        No hay proyección que consumir
        """
        self._set_valor_actual(0)
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#AUTOMOVIL", Decimal("-50000"))
        self.assertEqual(monto, Decimal("0"))

    # ─── Proyección parcialmente consumida ──────────────────────────────────

    def test_proyeccion_parcialmente_consumida_gasto_mayor(self):
        """
        Proyección AUTOMOVIL inicial: +160.000
        Ya se registró un gasto de -60.000 → proyección actual: +100.000
        Nuevo gasto: -120.000 → DECREMENTAR aplica -120.000
        resultado = +100.000 + (-120.000) = -20.000 → pasa de 0 → AJUSTAR
        monto_ajustado = 0 - 100.000 = -100.000
        """
        self._set_valor_actual(100000)
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#AUTOMOVIL", Decimal("-120000"))
        self.assertEqual(monto, Decimal("-100000"))

    # ─── Ítem no existe en DynamoDB ─────────────────────────────────────────

    def test_item_no_existe_retorna_cero(self):
        """
        Si no hay proyección registrada para el concepto, no hay nada que consumir.
        El decremento se bloquea completamente.
        """
        self._set_item_no_existe()
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#AUTOMOVIL", Decimal("-170000"))
        self.assertEqual(monto, Decimal("0"))

    # ─── INGRESO HOGAR: mismo comportamiento ────────────────────────────────

    def test_ingreso_hogar_menor_al_proyectado_pasa_completo(self):
        """
        Proyección INGRESO HOGAR: +2.492.820
        Ingreso real: +2.000.000 → DECREMENTAR aplica -2.000.000
        resultado = +2.492.820 + (-2.000.000) = +492.820 → no pasa de 0 → pasa completo
        Proyección queda en +492.820 (aún hay 492.820 de ingreso pendiente)
        """
        self._set_valor_actual(2492820)
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#INGRESO HOGAR", Decimal("-2000000"))
        self.assertEqual(monto, Decimal("-2000000"))

    def test_ingreso_hogar_mayor_al_proyectado_ajusta_a_cero(self):
        """
        Proyección INGRESO HOGAR: +2.492.820
        Ingreso real: +2.600.000 → DECREMENTAR aplica -2.600.000
        resultado = +2.492.820 + (-2.600.000) = -107.180 → pasa de 0 → AJUSTAR
        monto_ajustado = 0 - 2.492.820 = -2.492.820
        """
        self._set_valor_actual(2492820)
        monto = self.cm.calcular_monto_seguro("CASA#2026-05", "GASTO#INGRESO HOGAR", Decimal("-2600000"))
        self.assertEqual(monto, Decimal("-2492820"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
