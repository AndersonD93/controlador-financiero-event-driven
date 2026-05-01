"""
Tests unitarios para CierreMensual.py
Escenario: ejecución el 01/05/2026 (primer día de mayo)

El cierre liquida el mes que acaba de cerrar:
  Corte liquidado  → 2026-04 (abril, mes anterior)
  Corte siguiente  → 2026-05 (mayo, mes actual = destino del SALDO_INICIAL)

Datos simulados en FlujoDeCaja para el corte 2026-04:

PERSONAL#2026-04:
  CUENTA#INGRESO SALARIO#KUBO       valor=6.934.140  (saldo acumulado KUBO)
  CUENTA#APORTE HOGAR#KUBO          valor=-2.492.820
  CUENTA#SALDO_INICIAL#KUBO         valor=500.000
  GASTO#INGRESO SALARIO             valor=-6.934.140 (proyección consumida)
  GASTO#DEUDA A CASA                valor=-800.000   (persistente → se traslada)
  GASTO#APORTE HOGAR                valor=-2.492.820 (no persistente)
  GASTO#AHORRO PROYECTO FINCA       valor=-3.323.760 (no persistente)

CASA#2026-04:
  CUENTA#INGRESO HOGAR#BDO          valor=2.492.820
  CUENTA#SERVICIOS#BDO              valor=-210.000
  TARJETA#ALIMENTACION#TARJETA VISA BDO  valor=940.000
  GASTO#SERVICIOS                   valor=-210.000   (no persistente)
  GASTO#ALIMENTACION                valor=-940.000   (no persistente)

Resultados esperados en 2026-05:
  PERSONAL#2026-05:
    CUENTA#SALDO_INICIAL#KUBO  → 6.934.140 - 2.492.820 + 500.000 = 4.941.320
    GASTO#DEUDA A CASA         → trasladado con valor -800.000

  CASA#2026-05:
    CUENTA#SALDO_INICIAL#BDO              → 2.492.820 - 210.000 = 2.282.820
    TARJETA#SALDO_INICIAL#TARJETA VISA BDO → 940.000

Cambios respecto a versión anterior:
  - cerrar_proyecciones ya NO hace delete_item individual.
    La eliminación de todos los registros del corte cerrado la realiza
    eliminar_registros_corte usando batch_writer al final del procesamiento.
  - Se agrega test_eliminar_registros_corte_* para verificar la limpieza total.
  - El mock de query para eliminar_registros_corte debe retornar todos los ítems
    del PK (sin prefijo SK) y sin LastEvaluatedKey para terminar la paginación.
"""

import sys
import os
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

# Añadir el layer al path para importar catalogo_financiero
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../layer/python"))

# Mock de catalogo_financiero antes de importar CierreMensual
CATALOGO_MOCK = {
    "PERSONAL": {
        "CAJA_ACTUAL": {
            "CUENTA": ["BDO", "KUBO", "NEQUI", "EFECTIVO"],
            "TARJETA": ["TARJETA VISA BDO", "TARJETA MASTERCARD BDO", "TARJETA MASTERCARD NU"]
        },
        "PROYECCION": {
            "CONCEPTOS": ["AHORRO PROYECTO FINCA", "APORTE HOGAR", "DEUDA A CASA",
                          "INGRESO SALARIO", "SALDO_INICIAL"]
        }
    },
    "CASA": {
        "CAJA_ACTUAL": {
            "CUENTA": ["BDO", "KUBO", "NEQUI", "EFECTIVO"],
            "TARJETA": ["TARJETA VISA BDO", "TARJETA MASTERCARD BDO"]
        },
        "PROYECCION": {
            "CONCEPTOS": ["SERVICIOS", "ALIMENTACION", "INGRESO HOGAR", "SALDO_INICIAL"]
        }
    }
}

CONCEPTOS_PERSISTENTES_MOCK = {
    "PERSONAL": ["DEUDA A CASA"]
}

# Items simulados en FlujoDeCaja para 2026-04
ITEMS_PERSONAL_2026_04 = {
    "CUENTA": [
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#INGRESO SALARIO#KUBO",
         "tipo": "CUENTA", "bloque": "CAJA_ACTUAL", "concepto": "INGRESO SALARIO",
         "origen": "KUBO", "valor": Decimal("6934140")},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#APORTE HOGAR#KUBO",
         "tipo": "CUENTA", "bloque": "CAJA_ACTUAL", "concepto": "APORTE HOGAR",
         "origen": "KUBO", "valor": Decimal("-2492820")},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#SALDO_INICIAL#KUBO",
         "tipo": "CUENTA", "bloque": "CAJA_ACTUAL", "concepto": "SALDO_INICIAL",
         "origen": "KUBO", "valor": Decimal("500000")},
    ],
    "GASTO": [
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#INGRESO SALARIO",
         "tipo": "GASTO", "bloque": "PROYECCION", "concepto": "INGRESO SALARIO",
         "valor": Decimal("-6934140")},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#DEUDA A CASA",
         "tipo": "GASTO", "bloque": "PROYECCION", "concepto": "DEUDA A CASA",
         "valor": Decimal("-800000")},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#APORTE HOGAR",
         "tipo": "GASTO", "bloque": "PROYECCION", "concepto": "APORTE HOGAR",
         "valor": Decimal("-2492820")},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#AHORRO PROYECTO FINCA",
         "tipo": "GASTO", "bloque": "PROYECCION", "concepto": "AHORRO PROYECTO FINCA",
         "valor": Decimal("-3323760")},
    ],
    # Todos los ítems del PK para la limpieza final (sin filtro de SK)
    "ALL": [
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#INGRESO SALARIO#KUBO"},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#APORTE HOGAR#KUBO"},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#SALDO_INICIAL#KUBO"},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#INGRESO SALARIO"},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#DEUDA A CASA"},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#APORTE HOGAR"},
        {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#AHORRO PROYECTO FINCA"},
    ]
}

ITEMS_CASA_2026_04 = {
    "CUENTA": [
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "CUENTA#INGRESO HOGAR#BDO",
         "tipo": "CUENTA", "bloque": "CAJA_ACTUAL", "concepto": "INGRESO HOGAR",
         "origen": "BDO", "valor": Decimal("2492820")},
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "CUENTA#SERVICIOS#BDO",
         "tipo": "CUENTA", "bloque": "CAJA_ACTUAL", "concepto": "SERVICIOS",
         "origen": "BDO", "valor": Decimal("-210000")},
    ],
    "TARJETA": [
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "TARJETA#ALIMENTACION#TARJETA VISA BDO",
         "tipo": "TARJETA", "bloque": "CAJA_ACTUAL", "concepto": "ALIMENTACION",
         "origen": "TARJETA VISA BDO", "valor": Decimal("940000")},
    ],
    "GASTO": [
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "GASTO#SERVICIOS",
         "tipo": "GASTO", "bloque": "PROYECCION", "concepto": "SERVICIOS",
         "valor": Decimal("-210000")},
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "GASTO#ALIMENTACION",
         "tipo": "GASTO", "bloque": "PROYECCION", "concepto": "ALIMENTACION",
         "valor": Decimal("-940000")},
    ],
    # Todos los ítems del PK para la limpieza final
    "ALL": [
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "CUENTA#INGRESO HOGAR#BDO"},
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "CUENTA#SERVICIOS#BDO"},
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "TARJETA#ALIMENTACION#TARJETA VISA BDO"},
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "GASTO#SERVICIOS"},
        {"Dominio-Corte": "CASA#2026-04", "Tipo-Concepto": "GASTO#ALIMENTACION"},
    ]
}


def make_query_response(items, last_key=None):
    resp = {"Items": items}
    if last_key:
        resp["LastEvaluatedKey"] = last_key
    return resp


class TestCierreMensual(unittest.TestCase):

    def setUp(self):
        self.mock_table = MagicMock()
        self.mock_ssm = MagicMock()

        self.patches = [
            patch.dict("os.environ", {"flujo_caja_table": "FlujoDeCaja_test"}),
            patch("boto3.resource"),
            patch("boto3.client"),
            patch("catalogo_financiero.cargar_catalogo", return_value=CATALOGO_MOCK),
        ]

        for p in self.patches:
            p.start()

        import boto3
        boto3.resource.return_value.Table.return_value = self.mock_table
        boto3.client.return_value = self.mock_ssm

        self.mock_ssm.get_parameter.return_value = {
            "Parameter": {"Value": json.dumps(CONCEPTOS_PERSISTENTES_MOCK)}
        }

        # batch_writer como context manager
        mock_batch = MagicMock()
        self.mock_table.batch_writer.return_value.__enter__ = MagicMock(return_value=mock_batch)
        self.mock_table.batch_writer.return_value.__exit__ = MagicMock(return_value=False)
        self.mock_batch = mock_batch

        import importlib
        import terraform.templates.lambdas_code.CierreMensual as cm_module
        importlib.reload(cm_module)
        self.cm = cm_module

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _setup_query_side_effect(self):
        """
        Configura mock de table.query para devolver los items correctos según:
        - PK + prefijo SK → para liquidación de CAJA_ACTUAL y cerrar_proyecciones
        - PK sin prefijo SK → para eliminar_registros_corte (limpieza final)
        """
        def query_side_effect(**kwargs):
            values = kwargs["ExpressionAttributeValues"]
            pk = values[":pk"]
            sk_prefix = values.get(":sk")

            # ── Limpieza final: query sin prefijo SK ──
            if sk_prefix is None:
                if pk == "PERSONAL#2026-04":
                    return make_query_response(ITEMS_PERSONAL_2026_04["ALL"])
                if pk == "CASA#2026-04":
                    return make_query_response(ITEMS_CASA_2026_04["ALL"])
                return make_query_response([])

            # ── Liquidación CAJA_ACTUAL y proyecciones ──
            if pk == "PERSONAL#2026-04":
                if sk_prefix == "CUENTA#":
                    return make_query_response(ITEMS_PERSONAL_2026_04["CUENTA"])
                if sk_prefix == "TARJETA#":
                    return make_query_response([])
                if sk_prefix == "GASTO#":
                    return make_query_response(ITEMS_PERSONAL_2026_04["GASTO"])

            if pk == "CASA#2026-04":
                if sk_prefix == "CUENTA#":
                    return make_query_response(ITEMS_CASA_2026_04["CUENTA"])
                if sk_prefix == "TARJETA#":
                    return make_query_response(ITEMS_CASA_2026_04["TARJETA"])
                if sk_prefix == "GASTO#":
                    return make_query_response(ITEMS_CASA_2026_04["GASTO"])

            return make_query_response([])

        self.mock_table.query.side_effect = query_side_effect

    # ─── Tests de obtener_cortes ────────────────────────────────────────────

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_cortes_calculados_correctamente(self, mock_dt):
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        corte_actual, corte_siguiente = self.cm.obtener_cortes()
        self.assertEqual(corte_actual, "2026-04")
        self.assertEqual(corte_siguiente, "2026-05")

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_cortes_enero_liquida_diciembre_anterior(self, mock_dt):
        """El 01/01/2027 debe liquidar 2026-12 y generar saldo en 2027-01"""
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2027-01",
            month=1, year=2027
        )
        corte_actual, corte_siguiente = self.cm.obtener_cortes()
        self.assertEqual(corte_actual, "2026-12")
        self.assertEqual(corte_siguiente, "2027-01")

    # ─── Tests de construir_sk ──────────────────────────────────────────────

    def test_construir_sk_cuenta_con_origen(self):
        sk = self.cm.construir_sk("CUENTA", "SALDO_INICIAL", "KUBO")
        self.assertEqual(sk, "CUENTA#SALDO_INICIAL#KUBO")

    def test_construir_sk_gasto_sin_origen(self):
        sk = self.cm.construir_sk("GASTO", "DEUDA A CASA", None)
        self.assertEqual(sk, "GASTO#DEUDA A CASA")

    def test_construir_sk_tarjeta_con_origen(self):
        sk = self.cm.construir_sk("TARJETA", "SALDO_INICIAL", "TARJETA VISA BDO")
        self.assertEqual(sk, "TARJETA#SALDO_INICIAL#TARJETA VISA BDO")

    # ─── Tests de liquidación CAJA_ACTUAL ──────────────────────────────────

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_saldo_inicial_kubo_personal(self, mock_dt):
        """KUBO en PERSONAL: 6.934.140 - 2.492.820 + 500.000 = 4.941.320"""
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        self._setup_query_side_effect()

        self.cm.lambda_handler({}, {})

        put_calls = self.mock_table.put_item.call_args_list
        kubo_call = next(
            (c for c in put_calls
             if c.kwargs["Item"].get("origen") == "KUBO"
             and "PERSONAL" in c.kwargs["Item"].get("Dominio-Corte", "")),
            None
        )
        self.assertIsNotNone(kubo_call, "Debe crearse SALDO_INICIAL para KUBO en PERSONAL")
        self.assertEqual(kubo_call.kwargs["Item"]["valor"], Decimal("4941320"))
        self.assertEqual(kubo_call.kwargs["Item"]["Dominio-Corte"], "PERSONAL#2026-05")
        self.assertEqual(kubo_call.kwargs["Item"]["concepto"], "SALDO_INICIAL")

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_saldo_inicial_bdo_casa(self, mock_dt):
        """BDO en CASA: 2.492.820 - 210.000 = 2.282.820"""
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        self._setup_query_side_effect()

        self.cm.lambda_handler({}, {})

        put_calls = self.mock_table.put_item.call_args_list
        bdo_call = next(
            (c for c in put_calls
             if c.kwargs["Item"].get("origen") == "BDO"
             and "CASA" in c.kwargs["Item"].get("Dominio-Corte", "")),
            None
        )
        self.assertIsNotNone(bdo_call, "Debe crearse SALDO_INICIAL para BDO en CASA")
        self.assertEqual(bdo_call.kwargs["Item"]["valor"], Decimal("2282820"))
        self.assertEqual(bdo_call.kwargs["Item"]["Dominio-Corte"], "CASA#2026-05")

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_saldo_inicial_tarjeta_visa_casa(self, mock_dt):
        """TARJETA VISA BDO en CASA: 940.000"""
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        self._setup_query_side_effect()

        self.cm.lambda_handler({}, {})

        put_calls = self.mock_table.put_item.call_args_list
        visa_call = next(
            (c for c in put_calls
             if c.kwargs["Item"].get("origen") == "TARJETA VISA BDO"
             and "CASA" in c.kwargs["Item"].get("Dominio-Corte", "")),
            None
        )
        self.assertIsNotNone(visa_call, "Debe crearse SALDO_INICIAL para TARJETA VISA BDO en CASA")
        self.assertEqual(visa_call.kwargs["Item"]["valor"], Decimal("940000"))

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_cuenta_con_saldo_cero_no_genera_saldo_inicial(self, mock_dt):
        """Si el total de una cuenta es 0, no se crea SALDO_INICIAL"""
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )

        def query_side_effect(**kwargs):
            values = kwargs["ExpressionAttributeValues"]
            pk = values[":pk"]
            sk_prefix = values.get(":sk")
            if sk_prefix is None:
                return make_query_response([])
            if pk == "PERSONAL#2026-04" and sk_prefix == "CUENTA#":
                return make_query_response([
                    {"Dominio-Corte": "PERSONAL#2026-04",
                     "Tipo-Concepto": "CUENTA#INGRESO#NEQUI",
                     "origen": "NEQUI", "valor": Decimal("0")}
                ])
            return make_query_response([])

        self.mock_table.query.side_effect = query_side_effect

        self.cm.lambda_handler({}, {})

        put_calls = self.mock_table.put_item.call_args_list
        nequi_call = next(
            (c for c in put_calls if c.kwargs["Item"].get("origen") == "NEQUI"),
            None
        )
        self.assertIsNone(nequi_call, "No debe crearse SALDO_INICIAL para cuenta con saldo cero")

    # ─── Tests de cerrar_proyecciones ──────────────────────────────────────

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_concepto_persistente_deuda_a_casa_se_traslada(self, mock_dt):
        """DEUDA A CASA en PERSONAL es persistente → update_item en 2026-05 con valor -800.000"""
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        self._setup_query_side_effect()

        self.cm.lambda_handler({}, {})

        update_calls = self.mock_table.update_item.call_args_list
        deuda_call = next(
            (c for c in update_calls
             if c.kwargs["Key"].get("Dominio-Corte") == "PERSONAL#2026-05"
             and c.kwargs["Key"].get("Tipo-Concepto") == "GASTO#DEUDA A CASA"),
            None
        )
        self.assertIsNotNone(deuda_call, "DEUDA A CASA debe trasladarse a 2026-05")
        self.assertEqual(
            deuda_call.kwargs["ExpressionAttributeValues"][":inc"],
            Decimal("-800000")
        )

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_cerrar_proyecciones_no_hace_delete_individual(self, mock_dt):
        """
        Bug corregido: cerrar_proyecciones ya NO llama delete_item por cada
        proyección no persistente. La eliminación la centraliza eliminar_registros_corte.
        Verificamos que delete_item nunca se llama directamente.
        """
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        self._setup_query_side_effect()

        self.cm.lambda_handler({}, {})

        # delete_item no debe llamarse en ningún momento
        self.mock_table.delete_item.assert_not_called()

    # ─── Tests de eliminar_registros_corte ─────────────────────────────────

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_eliminar_registros_corte_usa_batch_writer(self, mock_dt):
        """
        Después del cierre, eliminar_registros_corte debe llamar batch_writer
        para cada dominio procesado (PERSONAL y CASA).
        """
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        self._setup_query_side_effect()

        self.cm.lambda_handler({}, {})

        # batch_writer debe haberse invocado al menos una vez por dominio
        self.assertGreaterEqual(
            self.mock_table.batch_writer.call_count, 1,
            "batch_writer debe usarse para la limpieza del corte cerrado"
        )

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_eliminar_registros_corte_borra_todos_los_items(self, mock_dt):
        """
        eliminar_registros_corte debe enviar al batch todos los ítems del PK,
        incluyendo CUENTA, TARJETA y GASTO del corte cerrado.
        """
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        self._setup_query_side_effect()

        self.cm.lambda_handler({}, {})

        delete_calls = self.mock_batch.delete_item.call_args_list
        sks_eliminados = {c.kwargs["Key"]["Tipo-Concepto"] for c in delete_calls}

        # PERSONAL#2026-04: todos sus ítems deben estar en el batch
        for item in ITEMS_PERSONAL_2026_04["ALL"]:
            self.assertIn(
                item["Tipo-Concepto"], sks_eliminados,
                f"Falta en batch: {item['Tipo-Concepto']}"
            )

        # CASA#2026-04: todos sus ítems deben estar en el batch
        for item in ITEMS_CASA_2026_04["ALL"]:
            self.assertIn(
                item["Tipo-Concepto"], sks_eliminados,
                f"Falta en batch: {item['Tipo-Concepto']}"
            )

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_eliminar_registros_corte_pagina_correctamente(self, mock_dt):
        """
        Si DynamoDB devuelve LastEvaluatedKey, eliminar_registros_corte debe
        continuar paginando hasta agotar todos los ítems.
        """
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )

        pagina_1 = [
            {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#A#KUBO"},
            {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#B#KUBO"},
        ]
        pagina_2 = [
            {"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "GASTO#C"},
        ]

        call_count = {"n": 0}

        def query_side_effect(**kwargs):
            values = kwargs["ExpressionAttributeValues"]
            pk = values[":pk"]
            sk_prefix = values.get(":sk")

            if sk_prefix is None and pk == "PERSONAL#2026-04":
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return make_query_response(pagina_1, last_key={"Dominio-Corte": "PERSONAL#2026-04", "Tipo-Concepto": "CUENTA#B#KUBO"})
                else:
                    return make_query_response(pagina_2)

            return make_query_response([])

        self.mock_table.query.side_effect = query_side_effect

        self.cm.eliminar_registros_corte("PERSONAL#2026-04", "PERSONAL")

        delete_calls = self.mock_batch.delete_item.call_args_list
        sks = {c.kwargs["Key"]["Tipo-Concepto"] for c in delete_calls}

        self.assertIn("CUENTA#A#KUBO", sks)
        self.assertIn("CUENTA#B#KUBO", sks)
        self.assertIn("GASTO#C", sks)
        self.assertEqual(call_count["n"], 2, "Debe haber realizado 2 páginas de query")

    @patch("terraform.templates.lambdas_code.CierreMensual.datetime")
    def test_corte_sin_registros_no_llama_batch(self, mock_dt):
        """Si el corte no tiene ítems, batch_writer no debe llamarse"""
        mock_dt.utcnow.return_value = MagicMock(
            strftime=lambda fmt: "2026-05",
            month=5, year=2026
        )
        self.mock_table.query.return_value = make_query_response([])

        self.cm.eliminar_registros_corte("PERSONAL#2026-04", "PERSONAL")

        self.mock_table.batch_writer.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
