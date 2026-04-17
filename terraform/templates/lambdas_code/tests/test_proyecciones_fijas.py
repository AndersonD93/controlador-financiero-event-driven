"""
Tests unitarios para ProyeccionesFijas.py
Escenario: ejecución el 01/05/2026 (mismo cron que CierreMensual)

La lambda proyecta desde el mes ACTUAL hacia adelante:
  Cortes evaluados → ['2026-05', '2026-06', '2026-07']

Estado previo simulado en las tablas de conceptos fijos:
  - CASA  / 2026-05 → YA tiene proyección automática  (omitir)
  - CASA  / 2026-06 → YA tiene proyección automática  (omitir)
  - CASA  / 2026-07 → NO tiene proyección              (insertar)
  - PERSONAL / 2026-05 → YA tiene proyección automática (omitir)
  - PERSONAL / 2026-06 → YA tiene proyección automática (omitir)
  - PERSONAL / 2026-07 → NO tiene proyección             (insertar)

Proyecciones configuradas en SSM (/flujo-caja/proyecciones-fijas):
  CASA:     SALUD=75000, ADMINISTRACION=185000, ALIMENTACION=940000
  PERSONAL: AHORRO PROYECTO FINCA=3323760, APORTE HOGAR=2492820

Resultado esperado:
  - 2026-05 y 2026-06: omitidos para ambos dominios (4 omisiones total)
  - 2026-07: insertados todos los conceptos de CASA y PERSONAL
  - Total put_item calls = len(conceptos_CASA) + len(conceptos_PERSONAL) = 3 + 2 = 5
"""

import sys
import os
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../layer/python"))

CATALOGO_MOCK = {
    "CASA": {
        "CAJA_ACTUAL": {
            "CUENTA": ["BDO", "KUBO", "NEQUI", "EFECTIVO"],
            "TARJETA": ["TARJETA VISA BDO", "TARJETA MASTERCARD BDO"]
        },
        "PROYECCION": {
            "CONCEPTOS": ["SALUD", "ADMINISTRACION", "ALIMENTACION", "SERVICIOS",
                          "HIPOTECARIO", "INGRESO HOGAR", "SALDO_INICIAL", "TRANSFERENCIA"]
        }
    },
    "PERSONAL": {
        "CAJA_ACTUAL": {
            "CUENTA": ["BDO", "KUBO", "NEQUI", "EFECTIVO"],
            "TARJETA": ["TARJETA VISA BDO"]
        },
        "PROYECCION": {
            "CONCEPTOS": ["AHORRO PROYECTO FINCA", "APORTE HOGAR", "DEUDA A CASA",
                          "INGRESO SALARIO", "SALDO_INICIAL", "TRANSFERENCIA"]
        }
    }
}

PROYECCIONES_MOCK = {
    "CASA": {
        "SALUD": 75000,
        "ADMINISTRACION": 185000,
        "ALIMENTACION": 940000
    },
    "PERSONAL": {
        "AHORRO PROYECTO FINCA": 3323760,
        "APORTE HOGAR": 2492820
    }
}


def make_gsi_response(count):
    return {"Count": count, "Items": [{"trx_id": "x"}] * count}


class TestProyeccionesFijas(unittest.TestCase):

    def setUp(self):
        self.mock_table_casa = MagicMock()
        self.mock_table_personal = MagicMock()

        self.patches = [
            patch.dict("os.environ", {
                "conceptos_fijos_table": "ConceptosFijosObligaciones_test",
                "conceptos_fijos_persona_table": "ConceptosFijosPersonal_test"
            }),
            patch("boto3.resource"),
            patch("boto3.client"),
            patch("catalogo_financiero.cargar_catalogo", return_value=CATALOGO_MOCK),
        ]

        for p in self.patches:
            p.start()

        import boto3
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.side_effect = lambda name: (
            self.mock_table_casa if "Obligaciones" in name else self.mock_table_personal
        )
        boto3.resource.return_value = mock_dynamodb

        mock_ssm = MagicMock()
        mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": json.dumps(PROYECCIONES_MOCK)}
        }
        boto3.client.return_value = mock_ssm

        import importlib
        import terraform.templates.lambdas_code.ProyeccionesFijas as pf_module
        importlib.reload(pf_module)
        self.pf = pf_module

    def tearDown(self):
        for p in self.patches:
            p.stop()

    # ─── Tests de calcular_cortes ───────────────────────────────────────────

    @patch("terraform.templates.lambdas_code.ProyeccionesFijas.datetime")
    def test_cortes_desde_mayo_2026(self, mock_dt):
        """01/05/2026 → cortes [2026-05, 2026-06, 2026-07]"""
        mock_dt.utcnow.return_value = MagicMock(
            replace=lambda **kw: MagicMock(month=5, year=2026)
        )
        mock_dt.strptime.side_effect = lambda s, f: __import__("datetime").datetime.strptime(s, f)

        cortes = self.pf.calcular_cortes()
        self.assertEqual(cortes, ["2026-05", "2026-06", "2026-07"])

    def test_cortes_con_base_explicito(self):
        """corte_base='2026-05' → [2026-05, 2026-06, 2026-07]"""
        cortes = self.pf.calcular_cortes("2026-05")
        self.assertEqual(cortes, ["2026-05", "2026-06", "2026-07"])

    def test_cortes_cambio_de_anio(self):
        """corte_base='2026-11' → [2026-11, 2026-12, 2027-01]"""
        cortes = self.pf.calcular_cortes("2026-11")
        self.assertEqual(cortes, ["2026-11", "2026-12", "2027-01"])

    def test_cortes_diciembre(self):
        """corte_base='2026-12' → [2026-12, 2027-01, 2027-02]"""
        cortes = self.pf.calcular_cortes("2026-12")
        self.assertEqual(cortes, ["2026-12", "2027-01", "2027-02"])

    # ─── Tests de idempotencia ──────────────────────────────────────────────

    def test_corte_ya_proyectado_retorna_true(self):
        """Si el GSI devuelve Count > 0, el corte ya fue proyectado"""
        self.mock_table_casa.query.return_value = make_gsi_response(1)
        resultado = self.pf.corte_ya_proyectado_automaticamente(
            self.mock_table_casa, "CASA", "2026-05"
        )
        self.assertTrue(resultado)

    def test_corte_no_proyectado_retorna_false(self):
        """Si el GSI devuelve Count = 0, el corte no ha sido proyectado"""
        self.mock_table_casa.query.return_value = make_gsi_response(0)
        resultado = self.pf.corte_ya_proyectado_automaticamente(
            self.mock_table_casa, "CASA", "2026-07"
        )
        self.assertFalse(resultado)

    # ─── Test principal: escenario 01/05/2026 ──────────────────────────────

    def _setup_gsi_side_effect(self):
        """
        2026-05 y 2026-06 ya proyectados para ambos dominios.
        2026-07 no proyectado para ninguno.
        """
        def gsi_side_effect(**kwargs):
            cond = kwargs.get("KeyConditionExpression")
            # Extraer corte del valor de la condición
            filter_expr = kwargs.get("FilterExpression")
            # Inspeccionar los valores pasados al query
            key_values = kwargs.get("ExpressionAttributeValues", {})
            # boto3 conditions no exponen valores directamente en mock,
            # usamos el call count para simular el orden de consultas
            return make_gsi_response(0)  # sobreescrito por side_effect por tabla

        # CASA: 2026-05 y 2026-06 ya proyectados, 2026-07 no
        self.mock_table_casa.query.side_effect = [
            make_gsi_response(1),  # CASA / 2026-05 → ya proyectado
            make_gsi_response(1),  # CASA / 2026-06 → ya proyectado
            make_gsi_response(0),  # CASA / 2026-07 → no proyectado
        ]

        # PERSONAL: igual
        self.mock_table_personal.query.side_effect = [
            make_gsi_response(1),  # PERSONAL / 2026-05 → ya proyectado
            make_gsi_response(1),  # PERSONAL / 2026-06 → ya proyectado
            make_gsi_response(0),  # PERSONAL / 2026-07 → no proyectado
        ]

    def test_solo_inserta_corte_no_proyectado(self):
        """Solo 2026-07 debe generar put_item; 2026-05 y 2026-06 se omiten"""
        self._setup_gsi_side_effect()

        result = self.pf.lambda_handler({"Corte": "2026-05"}, {})

        body = json.loads(result["body"])

        # 2026-05 y 2026-06 omitidos para CASA y PERSONAL
        self.assertIn("CASA", body["resultado"]["2026-05"]["omitidos_por_duplicado"])
        self.assertIn("PERSONAL", body["resultado"]["2026-05"]["omitidos_por_duplicado"])
        self.assertIn("CASA", body["resultado"]["2026-06"]["omitidos_por_duplicado"])
        self.assertIn("PERSONAL", body["resultado"]["2026-06"]["omitidos_por_duplicado"])

        # 2026-07 no tiene omitidos
        self.assertEqual(body["resultado"]["2026-07"]["omitidos_por_duplicado"], [])

    def test_cantidad_inserciones_en_corte_nuevo(self):
        """2026-07: 3 conceptos CASA + 2 conceptos PERSONAL = 5 put_item"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        total_puts = self.mock_table_casa.put_item.call_count + \
                     self.mock_table_personal.put_item.call_count
        self.assertEqual(total_puts, 5)

    def test_conceptos_casa_insertados_en_2026_07(self):
        """SALUD, ADMINISTRACION y ALIMENTACION deben insertarse para CASA/2026-07"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        put_calls = self.mock_table_casa.put_item.call_args_list
        conceptos_insertados = {c.kwargs["Item"]["concepto"] for c in put_calls}
        cortes_insertados = {c.kwargs["Item"]["corte"] for c in put_calls}

        self.assertIn("SALUD", conceptos_insertados)
        self.assertIn("ADMINISTRACION", conceptos_insertados)
        self.assertIn("ALIMENTACION", conceptos_insertados)
        self.assertEqual(cortes_insertados, {"2026-07"})

    def test_conceptos_personal_insertados_en_2026_07(self):
        """AHORRO PROYECTO FINCA y APORTE HOGAR deben insertarse para PERSONAL/2026-07"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        put_calls = self.mock_table_personal.put_item.call_args_list
        conceptos_insertados = {c.kwargs["Item"]["concepto"] for c in put_calls}
        cortes_insertados = {c.kwargs["Item"]["corte"] for c in put_calls}

        self.assertIn("AHORRO PROYECTO FINCA", conceptos_insertados)
        self.assertIn("APORTE HOGAR", conceptos_insertados)
        self.assertEqual(cortes_insertados, {"2026-07"})

    def test_origen_registro_es_automatico(self):
        """Todos los items insertados deben tener origen_registro = PROYECCION_AUTOMATICA"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        all_puts = (
            self.mock_table_casa.put_item.call_args_list +
            self.mock_table_personal.put_item.call_args_list
        )
        for c in all_puts:
            self.assertEqual(
                c.kwargs["Item"]["origen_registro"],
                "PROYECCION_AUTOMATICA",
                f"Item sin origen_registro correcto: {c.kwargs['Item']}"
            )

    def test_valores_correctos_casa(self):
        """Los valores insertados para CASA deben coincidir con el JSON de proyecciones"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        put_calls = self.mock_table_casa.put_item.call_args_list
        valores = {c.kwargs["Item"]["concepto"]: c.kwargs["Item"]["valor"] for c in put_calls}

        self.assertEqual(valores.get("SALUD"), 75000)
        self.assertEqual(valores.get("ADMINISTRACION"), 185000)
        self.assertEqual(valores.get("ALIMENTACION"), 940000)

    def test_todos_los_cortes_proyectados_no_inserta_nada(self):
        """Si los 3 cortes ya están proyectados, no debe haber ningún put_item"""
        self.mock_table_casa.query.side_effect = [
            make_gsi_response(1),
            make_gsi_response(1),
            make_gsi_response(1),
        ]
        self.mock_table_personal.query.side_effect = [
            make_gsi_response(1),
            make_gsi_response(1),
            make_gsi_response(1),
        ]

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        self.assertEqual(self.mock_table_casa.put_item.call_count, 0)
        self.assertEqual(self.mock_table_personal.put_item.call_count, 0)

    def test_respuesta_exitosa_contiene_cortes_evaluados(self):
        """La respuesta debe incluir los 3 cortes evaluados"""
        self._setup_gsi_side_effect()

        result = self.pf.lambda_handler({"Corte": "2026-05"}, {})

        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body["cortes_evaluados"], ["2026-05", "2026-06", "2026-07"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
