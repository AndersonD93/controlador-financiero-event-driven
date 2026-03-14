{
  "functions": [
    {
      "name": "ContabilizarProyecciones",
      "intent": "contabilizar_proyeccion",
      "description": "Registrar una proyección de gasto o ingreso",
      "lambda": "${lambda_contabilizar_proyecciones}",
      "payload": {
        "Corte": "string",
        "Valor": "number",
        "FechaMovimiento": "date",
        "DominioFinanciero": "string",
        "Concepto": "string",
        "Subconcepto": "string"
      },
      "examples": [
        "registrar gasto administracion marzo",
        "agregar proyeccion de administracion",
        "agregar proyeccion de ingreso para dominio casa",
        "registrar proyeccion de gasto de administracion",
        "anotar gasto proyectado de administracion",
        "agregar gasto de administracion para marzo",
        "registrar ingreso proyectado en dominio casa",
        "registrar proyeccion de servicios"
      ],
      "keywords": ["proyeccion", "gasto futuro", "ingreso futuro", "flujo de caja"]
    },
    {
      "name": "MovimientosCuentasEInversiones",
      "intent": "movimiento_cuenta",
      "description": "Registrar movimientos de cuentas o inversiones",
      "lambda": "${lambda_movimiento_cuentas_inversiones}",
      "payload": {
        "Cuenta": "string",
        "Descripcion": "string",
        "Subconcepto": "string",
        "Valor": "number",
        "FechaMovimiento": "date",
        "Corte": "string",
        "DominioFinanciero": "string"
      },
      "examples": [
        "registrar pago con cuenta kubo correspondiente a servicio",
        "registrar pago con cuenta bdo para alimentación",
        "registrar inversion en cdt",
        "registrar movimiento en cuenta kubo",
        "agregar gasto pagado desde cuenta bdo",
        "transferencia desde cuenta kubo",
        "registrar ahorro en cuenta",
        "agregar dinero a inversion cdt"
      ],
      "keywords": ["ingresa", "pago con cuenta", "inversiones", "cuenta"]
    },
    {
      "name": "MovimientosTarjetas",
      "intent": "movimiento_tarjeta",
      "description": "Registrar gasto de tarjeta de credito",
      "lambda": "${lambda_movimiento_tarjetas}",
      "payload": {
        "Franquicia": "string",
        "Corte": "string",
        "Valor": "number",
        "FechaMovimiento": "date",
        "DominioFinanciero": "string",
        "Descripcion": "string",
        "Subconcepto": "string"
      },
      "examples": [
        "registrar pago con tarjeta mastercard correspondiente a servicio",
        "registrar pago con tarjeta visa para alimentación",
        "registrar pago con tarjeta nu para hipotecario",
        "registrar compra con tarjeta mastercard",
        "gasto realizado con tarjeta visa",
        "pago hecho con tarjeta de credito",
        "compra con tarjeta nu",
        "registrar gasto en tarjeta"
      ],
      "keywords": ["tarjeta", "pago con tarjeta"]
    },
    {
      "name": "ConsultasLenguajeNatural",
      "intent": "consulta_financiera",
      "description": "Responder preguntas financieras",
      "lambda": "${lambda_consulta_lenguaje}",
      "payload": {
        "question": "string"
      },
      "examples": [
        "¿Cual es valor de la caja actual del dominio personal?",
        "¿Cual es el valor de mis inversiones y ahorro?",
        "cuanto dinero tengo en inversiones",
        "cuanto dinero tengo ahorrado",
        "cual es mi saldo actual",
        "cuanto tengo en caja",
        "valor total de inversiones",
        "cuanto dinero tengo disponible"
      ],
      "keywords": ["consulta", "cual es el valor", "saldos"]
    }
  ]
}