import sys
import boto3
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

s3 = boto3.client("s3")

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
# Mes actual
# =====================
mes_actual = F.date_format(F.current_date(), "yyyy-MM")

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
# CAJA ACTUAL
# =====================
detalle_caja = (
    df.filter(F.col("bloque") == "CAJA_ACTUAL")
      .groupBy("dominio", F.lit(mes_actual).alias("corte"), "origen")
      .agg(F.sum("valor_ajustado").alias("valor_ajustado"))
      .select(
          "dominio",
          "corte",
          F.lit("CAJA_ACTUAL").alias("seccion"),
          F.col("origen").alias("concepto"),
          "valor_ajustado"
      )
)

total_caja = (
    detalle_caja
        .groupBy("dominio", "corte")
        .agg(F.sum("valor_ajustado").alias("valor_ajustado"))
        .withColumn("seccion", F.lit("TOTAL_CAJA_ACTUAL"))
        .withColumn("concepto", F.lit(""))
)

# =====================
# PROYECCIÓN
# =====================
detalle_proyeccion = (
    df.filter(F.col("bloque") == "PROYECCION")
      .filter(F.col("corte") >= mes_actual)
      .select(
          "dominio",
          "corte",
          F.lit("PROYECCION").alias("seccion"),
          "concepto",
          "valor_ajustado"
      )
)

proyeccion_total = (
    detalle_proyeccion
        .groupBy("dominio", "corte")
        .agg(F.sum("valor_ajustado").alias("total_proyeccion"))
)

window_cortes = (
    Window.partitionBy("dominio")
          .orderBy("corte")
          .rowsBetween(Window.unboundedPreceding, 0)
)

proyeccion_acumulada = (
    proyeccion_total
        .join(
            total_caja.select(
                "dominio",
                F.col("valor_ajustado").alias("total_caja_actual")
            ),
            "dominio",
            "left"
        )
        .withColumn(
            "acumulado_proyeccion",
            F.sum("total_proyeccion").over(window_cortes)
        )
        .withColumn(
            "valor_ajustado",
            F.col("total_caja_actual") + F.col("acumulado_proyeccion")
        )
        .select(
            "dominio",
            "corte",
            F.concat(
                F.lit("CAJA_PROYECTADA_A_CORTE_"),
                F.col("corte")
            ).alias("seccion"),
            F.lit("").alias("concepto"),
            "valor_ajustado"
        )
)

# =====================
# Unión final
# =====================
resultado = (
    detalle_caja
        .unionByName(total_caja)
        .unionByName(detalle_proyeccion)
        .unionByName(proyeccion_acumulada)
)

# =====================
# Orden final
# =====================
resultado = resultado.orderBy(
    "dominio",
    "corte",
    F.when(F.col("seccion") == "CAJA_ACTUAL", 1)
     .when(F.col("seccion") == "TOTAL_CAJA_ACTUAL", 2)
     .when(F.col("seccion") == "PROYECCION", 3)
     .otherwise(4),
    "concepto"
)

# ============================================================
# =============== SALIDA 1: CSV FLUJO DE CAJA =================
# ============================================================
tmp_path = args["OUTPUT_S3_PATH"].rstrip("/") + "/reports"

resultado.coalesce(1).write.mode("overwrite").option("header", "true").csv(tmp_path)

fecha = spark.sql(
    "SELECT date_format(current_date(), 'dd-MM-yy') AS f"
).collect()[0]["f"]

bucket = tmp_path.replace("s3://", "").split("/")[0]
prefix = "/".join(tmp_path.replace("s3://", "").split("/")[1:])

objects = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
csv_file = [o["Key"] for o in objects["Contents"] if o["Key"].endswith(".csv")][0]

base_prefix = "/".join(tmp_path.replace("s3://", "").split("/")[1:])

final_key = f"{base_prefix}/reporte_flujo_caja_{fecha}.csv"

s3.copy_object(
    Bucket=bucket,
    CopySource={"Bucket": bucket, "Key": csv_file},
    Key=final_key
)

s3.delete_object(Bucket=bucket, Key=csv_file)

print(f"CSV generado: s3://{bucket}/{final_key}")

# ============================================================
# ================= SALIDA 2: JSONL PARA RAG ==================
# ============================================================

mes_actual_str = spark.sql(
    "SELECT date_format(current_date(), 'yyyy-MM') AS f"
).collect()[0]["f"]

rag_df = (
    resultado
        # ---------------------------
        # Clasificación semántica
        # ---------------------------
        .withColumn(
            "tipo_registro",
            F.when(F.col("concepto") == "", "TOTAL")
             .otherwise("DETALLE")
        )
        .withColumn(
            "categoria_bloque",
            F.when(F.col("seccion").like("%CAJA_ACTUAL%"), "CAJA_ACTUAL")
             .when(F.col("seccion").like("%PROYECCION%"), "PROYECCION")
             .otherwise("OTRO")
        )
        .withColumn(
            "es_futuro",
            F.when(F.col("corte") >= mes_actual_str, True)
             .otherwise(False)
        )

        # ---------------------------
        # Texto optimizado para RAG
        # ---------------------------
        .withColumn(
            "texto",
            F.concat(
                F.lit("Dominio financiero: "),
                F.col("dominio"),
                F.lit(". Periodo: "),
                F.col("corte"),
                F.lit(". Sección: "),
                F.col("seccion"),
                F.lit(". "),
                F.when(F.col("concepto") != "", 
                       F.concat(F.lit("Concepto: "), F.col("concepto"), F.lit(". "))
                ).otherwise(F.lit("")),
                F.lit("Tipo registro: "),
                F.col("tipo_registro"),
                F.lit(". Valor calculado: "),
                F.format_number(F.col("valor_ajustado"), 0)
            )
        )

        # ---------------------------
        # ID estable
        # ---------------------------
        .withColumn(
            "id",
            F.concat_ws("_", "dominio", "corte", "seccion", "concepto")
        )

        # ---------------------------
        # Selección final estructurada
        # ---------------------------
        .select(
            "id",
            "dominio",
            "corte",
            "categoria_bloque",
            "tipo_registro",
            "es_futuro",
            "seccion",
            "concepto",
            F.col("valor_ajustado").alias("valor"),
            "texto"
        )
)

# ============================================================
# Escritura en ruta independiente definida por parámetro
# ============================================================

rag_path = args["OUTPUT_S3_PATH"].rstrip("/") + "/rag"

rag_df.coalesce(1).write.mode("overwrite").json(rag_path)

print(f"RAG JSONL generado en: {rag_path}")