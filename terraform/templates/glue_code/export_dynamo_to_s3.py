import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# =====================
# Parámetros
# =====================
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'DYNAMO_TABLE',
    'OUTPUT_S3_PATH'
])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

# =====================
# Lectura DynamoDB
# =====================
df = glueContext.create_dynamic_frame.from_options(
    connection_type="dynamodb",
    connection_options={
        "dynamodb.input.tableName": args["DYNAMO_TABLE"],
        "dynamodb.throughput.read.percent": "0.5"
    }
).toDF()

# =====================
# Normalizar columnas
# =====================
for c in df.columns:
    df = df.withColumnRenamed(c, c.replace("-", "_"))

# =====================
# Dominio y corte
# =====================
df = (
    df.withColumn("dominio", F.split("Dominio_Corte", "#").getItem(0))
      .withColumn("corte", F.split("Dominio_Corte", "#").getItem(1))
)

# =====================
# Reglas de signo
# =====================
df = df.withColumn(
    "valor_ajustado",
    F.when(
        (F.col("bloque") == "CAJA_ACTUAL") &
        (F.upper(F.col("origen")).contains("TARJETA")),
        -F.col("valor")
    ).when(
        (F.col("tipo") == "GASTO") &
        (~F.upper(F.col("concepto")).contains("INGRESO")),
        -F.col("valor")
    ).otherwise(F.col("valor"))
)

# =====================
# Detalle CAJA ACTUAL
# =====================
detalle_caja = (
    df.filter(F.col("bloque") == "CAJA_ACTUAL")
      .select(
          "dominio",
          F.lit("CAJA_ACTUAL").alias("seccion"),
          "concepto",
          "valor_ajustado"
      )
)

# =====================
# Total CAJA ACTUAL
# =====================
total_caja = (
    detalle_caja
        .groupBy("dominio")
        .agg(F.sum("valor_ajustado").alias("valor_ajustado"))
        .withColumn("seccion", F.lit("TOTAL_CAJA_ACTUAL"))
        .withColumn("concepto", F.lit(""))
)

# =====================
# PROYECCION por corte (detalle)
# =====================
detalle_proyeccion = (
    df.filter(F.col("bloque") == "PROYECCION")
      .select(
          "dominio",
          "corte",
          F.lit("PROYECCION").alias("seccion"),
          "concepto",
          "valor_ajustado"
      )
)

# =====================
# Total PROYECCION por corte
# =====================
total_proyeccion = (
    detalle_proyeccion
        .groupBy("dominio", "corte")
        .agg(F.sum("valor_ajustado").alias("valor_ajustado"))
        .withColumn(
            "seccion",
            F.concat(F.lit("CAJA_PROYECTADA_A_CORTE_"), F.col("corte"))
        )
        .withColumn("concepto", F.lit(""))
)

# =====================
# Unión completa (incluye AHORRO)
# =====================
resultado = (
    detalle_caja
        .unionByName(total_caja)
        .unionByName(
            detalle_proyeccion.select("dominio", "seccion", "concepto", "valor_ajustado"),
            allowMissingColumns=True
        )
        .unionByName(
            total_proyeccion.select("dominio", "seccion", "concepto", "valor_ajustado"),
            allowMissingColumns=True
        )
)

# =====================
# Orden contable
# =====================
resultado = resultado.orderBy(
    "dominio",
    F.when(F.col("seccion") == "CAJA_ACTUAL", 1)
     .when(F.col("seccion") == "TOTAL_CAJA_ACTUAL", 2)
     .when(F.col("seccion").startswith("PROYECCION"), 3)
     .otherwise(4),
    "concepto"
)

# =====================
# Escritura CSV
# =====================
(
    resultado
        .coalesce(1)
        .write
        .mode("overwrite")
        .option("header", "true")
        .csv(args["OUTPUT_S3_PATH"].rstrip("/") + "/flujo_caja_detallado")
)

print("Reporte CSV detallado generado correctamente")
