import json
import boto3
import time
from botocore.exceptions import ClientError

ssm = boto3.client("ssm")

CATALOGO_PARAM = "/flujo-caja/catalogo_financiero"

_CACHE = None
_CACHE_TS = 0
TTL_SECONDS = 600


def cargar_catalogo():
    global _CACHE, _CACHE_TS
    now = time.time()

    if _CACHE and (now - _CACHE_TS) < TTL_SECONDS:
        return _CACHE

    try:
        response = ssm.get_parameter(
            Name=CATALOGO_PARAM,
            WithDecryption=False
        )

        _CACHE = json.loads(response["Parameter"]["Value"])
        _CACHE_TS = now
        return _CACHE

    except ClientError as e:
        raise Exception(f"No se pudo cargar catálogo financiero: {str(e)}")
    
def validar_dominio(catalogo, dominio):
    if dominio not in catalogo:
        raise ValueError(f"Dominio inválido: {dominio}")
    
def obtener_origenes_validos(catalogo, dominio):
    dominio_cfg = catalogo[dominio]
    caja = dominio_cfg.get("CAJA_ACTUAL", {})

    origenes = []

    for valor in caja.values():
        if isinstance(valor, list):
            origenes.extend(valor)

    return origenes

def obtener_conceptos_validos(catalogo, dominio, bloque):
    """
    Retorna todos los conceptos válidos dentro de un bloque específico.
    """

    try:
        dominio_data = catalogo[dominio]
    except KeyError:
        raise ValueError(f"Dominio '{dominio}' no existe en el catálogo")

    try:
        bloque_data = dominio_data[bloque]
    except KeyError:
        raise ValueError(
            f"Bloque '{bloque}' no configurado para dominio '{dominio}'"
        )

    conceptos = []

    for value in bloque_data.values():
        if isinstance(value, list):
            conceptos.extend(value)

    return conceptos


def obtener_cuentas_validas(catalogo, dominio, bloque="CAJA_ACTUAL", tipo=None):
    """
    Retorna cuentas válidas según:
    - dominio (CASA, PERSONAL, etc.)
    - bloque (CAJA_ACTUAL, PROYECCION, etc.)
    - tipo (CUENTA, TARJETA, INGRESO, etc.)
    """

    try:
        dominio_data = catalogo[dominio]
    except KeyError:
        raise ValueError(f"Dominio '{dominio}' no existe en el catálogo")

    try:
        bloque_data = dominio_data[bloque]
    except KeyError:
        raise ValueError(
            f"Bloque '{bloque}' no configurado para dominio '{dominio}'"
        )

    if tipo:
        try:
            return bloque_data[tipo]
        except KeyError:
            raise ValueError(
                f"Tipo '{tipo}' no configurado en '{bloque}' para dominio '{dominio}'"
            )

    # Si no se especifica tipo, combinar todos los arrays del bloque
    cuentas = []
    for key, value in bloque_data.items():
        if isinstance(value, list):
            cuentas.extend(value)

    return cuentas