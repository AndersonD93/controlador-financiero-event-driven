"""
Tests unitarios para ProyeccionesFijas.py
Escenario: ejecución el 01/05/2026 (mismo cron que CierreMensual)

Cambios respecto a versión anterior:
  1. calcular_cortes ahora arranca desde el mes SIGUIENTE al base/actual.
     corte_base='2026-05' → ['2026-06', '2026-07', '2026-08']  (antes era ['2026-05', ...])
     Sin corte_base en mayo 2026 → ['2026-06', '2026-07', '2026-08']

  2. corte_ya_proyectado_automaticamente ya no usa Limit=1.
     Pagina con LastEvaluatedKey hasta encontrar un match o agotar resultados.
     El mock debe retornar {"Count": N, "Items": [...]} sin LastEvaluatedKey
     para terminar el loop (o con LastEvaluatedKey para simular paginación).

Estado previo simulado en las tablas de conceptos fijos:
  - CASA  / 2026-06 → YA tiene proyección automática  (omitir)
  - CASA  / 2026-07 → YA tiene proyección automática  (omitir)
  - CASA  / 2026-08 → NO tiene proyección              (insertar)
  - PERSONAL / 2026-06 → YA tiene proyección automática (omitir)
  - PERSONAL / 2026-07 → YA tiene proyección automática (omitir)
  - PERSONAL / 2026-08 → NO tiene proyección             (insertar)

Proyecciones configuradas en SSM (/flujo-caja/proyecciones-fijas):
  CASA:     SALUD=75000, ADMINISTRACION=185000, ALIMENTACION=940000
  PERSONAL: AHORRO PROYECTO FINCA=3323760, APORTE HOGAR=2492820

Resultado esperado con corte_base='2026-05':
  - 2026-06 y 2026-07: omitidos para ambos dominios
  - 2026-08: insertados todos los conceptos de CASA (3) y PERSONAL (2) = 5 put_item
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


def make_gsi_response(count, last_key=None):
    """
    Simula respuesta de DynamoDB query con paginación opcional.
    Sin last_key → termina el loop de paginación en corte_ya_proyectado_automaticamente.
    """
    resp = {
        "Count": count,
        "Items": [{"trx_id": f"x{i}", "origen_registro": "PROYECCION_AUTOMATICA"}
                  for i in range(count)]
    }
    if last_key:
        resp["LastEvaluatedKey"] = last_key
    return resp


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
    # Bug corregido: el inicio es el mes SIGUIENTE al base/actual

    @patch("terraform.templates.lambdas_code.ProyeccionesFijas.datetime")
    def test_cortes_desde_mayo_2026_sin_base(self, mock_dt):
        """
        Ejecutando en mayo 2026 sin corte_base → ['2026-06', '2026-07', '2026-08']
        Bug anterior: devolvía ['2026-05', '2026-06', '2026-07'] pisando el mes actual.
        """
        mock_fecha = MagicMock()
        mock_fecha.month = 5
        mock_fecha.year = 2026
        mock_fecha.replace.return_value = mock_fecha
        mock_dt.utcnow.return_value = mock_fecha
        mock_dt.strptime.side_effect = lambda s, f: __import__("datetime").datetime.strptime(s, f)

        cortes = self.pf.calcular_cortes()
        self.assertEqual(cortes, ["2026-06", "2026-07", "2026-08"])

    def test_cortes_con_base_explicito_avanza_un_mes(self):
        """
        corte_base='2026-05' → inicio en 2026-06 → ['2026-06', '2026-07', '2026-08']
        Bug anterior: devolvía ['2026-05', '2026-06', '2026-07'].
        """
        cortes = self.pf.calcular_cortes("2026-05")
        self.assertEqual(cortes, ["2026-06", "2026-07", "2026-08"])

    def test_cortes_cambio_de_anio(self):
        """corte_base='2026-11' → inicio en 2026-12 → ['2026-12', '2027-01', '2027-02']"""
        cortes = self.pf.calcular_cortes("2026-11")
        self.assertEqual(cortes, ["2026-12", "2027-01", "2027-02"])

    def test_cortes_diciembre_avanza_a_enero(self):
        """corte_base='2026-12' → inicio en 2027-01 → ['2027-01', '2027-02', '2027-03']"""
        cortes = self.pf.calcular_cortes("2026-12")
        self.assertEqual(cortes, ["2027-01", "2027-02", "2027-03"])

    def test_cortes_noviembre_incluye_cambio_de_anio(self):
        """corte_base='2026-10' → inicio en 2026-11 → ['2026-11', '2026-12', '2027-01']"""
        cortes = self.pf.calcular_cortes("2026-10")
        self.assertEqual(cortes, ["2026-11", "2026-12", "2027-01"])

    # ─── Tests de corte_ya_proyectado_automaticamente ───────────────────────
    # Bug corregido: sin Limit=1, pagina con LastEvaluatedKey

    def test_corte_ya_proyectado_retorna_true_en_primera_pagina(self):
        """Count > 0 en primera página → True sin necesidad de paginar"""
        self.mock_table_casa.query.return_value = make_gsi_response(1)
        resultado = self.pf.corte_ya_proyectado_automaticamente(
            self.mock_table_casa, "CASA", "2026-06"
        )
        self.assertTrue(resultado)
        self.assertEqual(self.mock_table_casa.query.call_count, 1)

    def test_corte_no_proyectado_retorna_false(self):
        """Count = 0 sin LastEvaluatedKey → False (una sola página)"""
        self.mock_table_casa.query.return_value = make_gsi_response(0)
        resultado = self.pf.corte_ya_proyectado_automaticamente(
            self.mock_table_casa, "CASA", "2026-08"
        )
        self.assertFalse(resultado)

    def test_corte_proyectado_encontrado_en_segunda_pagina(self):
        """
        Bug corregido: con Limit=1 el ítem con PROYECCION_AUTOMATICA podía quedar
        fuera de la evaluación. Ahora pagina hasta encontrarlo.
        Primera página: Count=0 con LastEvaluatedKey → continúa.
        Segunda página: Count=1 → retorna True.
        """
        self.mock_table_casa.query.side_effect = [
            make_gsi_response(0, last_key={"trx_id": "pagina1"}),  # primera página sin match
            make_gsi_response(1),                                    # segunda página con match
        ]
        resultado = self.pf.corte_ya_proyectado_automaticamente(
            self.mock_table_casa, "CASA", "2026-06"
        )
        self.assertTrue(resultado)
        self.assertEqual(self.mock_table_casa.query.call_count, 2)

    def test_corte_no_proyectado_con_multiples_paginas(self):
        """Varias páginas sin match → False al agotar la paginación"""
        self.mock_table_casa.query.side_effect = [
            make_gsi_response(0, last_key={"trx_id": "p1"}),
            make_gsi_response(0, last_key={"trx_id": "p2"}),
            make_gsi_response(0),  # última página sin LastEvaluatedKey
        ]
        resultado = self.pf.corte_ya_proyectado_automaticamente(
            self.mock_table_casa, "CASA", "2026-08"
        )
        self.assertFalse(resultado)
        self.assertEqual(self.mock_table_casa.query.call_count, 3)

    def test_segunda_pagina_pasa_exclusive_start_key(self):
        """Verifica que ExclusiveStartKey se pasa correctamente en la segunda llamada"""
        last_key = {"trx_id": "ultimo_item", "corte": "2026-06"}
        self.mock_table_casa.query.side_effect = [
            make_gsi_response(0, last_key=last_key),
            make_gsi_response(0),
        ]
        self.pf.corte_ya_proyectado_automaticamente(
            self.mock_table_casa, "CASA", "2026-06"
        )
        segunda_llamada = self.mock_table_casa.query.call_args_list[1]
        self.assertEqual(segunda_llamada.kwargs.get("ExclusiveStartKey"), last_key)

    # ─── Test principal: escenario 01/05/2026 ──────────────────────────────

    def _setup_gsi_side_effect(self):
        """
        Cortes evaluados con corte_base='2026-05': ['2026-06', '2026-07', '2026-08']
        2026-06 y 2026-07 ya proyectados para ambos dominios.
        2026-08 no proyectado para ninguno.
        """
        # CASA: 2026-06 y 2026-07 ya proyectados, 2026-08 no
        self.mock_table_casa.query.side_effect = [
            make_gsi_response(1),  # CASA / 2026-06 → ya proyectado
            make_gsi_response(1),  # CASA / 2026-07 → ya proyectado
            make_gsi_response(0),  # CASA / 2026-08 → no proyectado
        ]
        # PERSONAL: igual
        self.mock_table_personal.query.side_effect = [
            make_gsi_response(1),  # PERSONAL / 2026-06 → ya proyectado
            make_gsi_response(1),  # PERSONAL / 2026-07 → ya proyectado
            make_gsi_response(0),  # PERSONAL / 2026-08 → no proyectado
        ]

    def test_cortes_evaluados_son_los_tres_siguientes_al_base(self):
        """
        Con corte_base='2026-05', los cortes evaluados deben ser
        ['2026-06', '2026-07', '2026-08'], no ['2026-05', '2026-06', '2026-07'].
        """
        self._setup_gsi_side_effect()

        result = self.pf.lambda_handler({"Corte": "2026-05"}, {})
        body = json.loads(result["body"])

        self.assertEqual(body["cortes_evaluados"], ["2026-06", "2026-07", "2026-08"])

    def test_solo_inserta_corte_no_proyectado(self):
        """Solo 2026-08 debe generar put_item; 2026-06 y 2026-07 se omiten"""
        self._setup_gsi_side_effect()

        result = self.pf.lambda_handler({"Corte": "2026-05"}, {})
        body = json.loads(result["body"])

        # 2026-06 y 2026-07 omitidos para CASA y PERSONAL
        self.assertIn("CASA", body["resultado"]["2026-06"]["omitidos_por_duplicado"])
        self.assertIn("PERSONAL", body["resultado"]["2026-06"]["omitidos_por_duplicado"])
        self.assertIn("CASA", body["resultado"]["2026-07"]["omitidos_por_duplicado"])
        self.assertIn("PERSONAL", body["resultado"]["2026-07"]["omitidos_por_duplicado"])

        # 2026-08 no tiene omitidos
        self.assertEqual(body["resultado"]["2026-08"]["omitidos_por_duplicado"], [])

    def test_cantidad_inserciones_en_corte_nuevo(self):
        """2026-08: 3 conceptos CASA + 2 conceptos PERSONAL = 5 put_item"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        total_puts = (self.mock_table_casa.put_item.call_count +
                      self.mock_table_personal.put_item.call_count)
        self.assertEqual(total_puts, 5)

    def test_conceptos_casa_insertados_en_corte_nuevo(self):
        """SALUD, ADMINISTRACION y ALIMENTACION deben insertarse para CASA/2026-08"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        put_calls = self.mock_table_casa.put_item.call_args_list
        conceptos_insertados = {c.kwargs["Item"]["concepto"] for c in put_calls}
        cortes_insertados = {c.kwargs["Item"]["corte"] for c in put_calls}

        self.assertIn("SALUD", conceptos_insertados)
        self.assertIn("ADMINISTRACION", conceptos_insertados)
        self.assertIn("ALIMENTACION", conceptos_insertados)
        self.assertEqual(cortes_insertados, {"2026-08"})

    def test_conceptos_personal_insertados_en_corte_nuevo(self):
        """AHORRO PROYECTO FINCA y APORTE HOGAR deben insertarse para PERSONAL/2026-08"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        put_calls = self.mock_table_personal.put_item.call_args_list
        conceptos_insertados = {c.kwargs["Item"]["concepto"] for c in put_calls}
        cortes_insertados = {c.kwargs["Item"]["corte"] for c in put_calls}

        self.assertIn("AHORRO PROYECTO FINCA", conceptos_insertados)
        self.assertIn("APORTE HOGAR", conceptos_insertados)
        self.assertEqual(cortes_insertados, {"2026-08"})

    def test_origen_registro_es_automatico(self):
        """Todos los items insertados deben tener origen_registro = PROYECCION_AUTOMATICA"""
        self._setup_gsi_side_effect()

        self.pf.lambda_handler({"Corte": "2026-05"}, {})

        all_puts = (self.mock_table_casa.put_item.call_args_list +
                    self.mock_table_personal.put_item.call_args_list)
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
        """La respuesta debe incluir los 3 cortes evaluados (siguientes al base)"""
        self._setup_gsi_side_effect()

        result = self.pf.lambda_handler({"Corte": "2026-05"}, {})

        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body["cortes_evaluados"], ["2026-06", "2026-07", "2026-08"])

    def test_respuesta_incluye_insertados_en_corte_nuevo(self):
        """El resultado de 2026-08 debe listar los conceptos insertados"""
        self._setup_gsi_side_effect()

        result = self.pf.lambda_handler({"Corte": "2026-05"}, {})
        body = json.loads(result["body"])

        insertados_2026_08 = body["resultado"]["2026-08"]["insertados"]
        conceptos = {i["concepto"] for i in insertados_2026_08}

        self.assertIn("SALUD", conceptos)
        self.assertIn("ADMINISTRACION", conceptos)
        self.assertIn("ALIMENTACION", conceptos)
        self.assertIn("AHORRO PROYECTO FINCA", conceptos)
        self.assertIn("APORTE HOGAR", conceptos)


if __name__ == "__main__":
    unittest.main(verbosity=2)
