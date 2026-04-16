# Control Financiero Personal — Serverless AWS

Sistema de control financiero personal basado en eventos, desplegado completamente en AWS con Terraform. Permite registrar, consolidar y proyectar movimientos financieros (cuentas, tarjetas, inversiones y ahorros) con reglas de compensación automáticas. La interfaz principal es **Slack**, con un asistente IA integrado para consultas en lenguaje natural.

---

## Arquitectura

![Arquitectura del sistema](image.png)

El sistema está construido sobre una arquitectura **event-driven serverless** donde cada componente reacciona a eventos publicados en un bus central de EventBridge. Los datos fluyen desde Slack → API Gateway → Lambdas → DynamoDB → Consolidación → Reportes → IA.

---

## Componentes AWS

| Recurso | Uso |
|---|---|
| **Lambda (12 funciones)** | Procesamiento de eventos, consolidación, notificaciones e IA |
| **DynamoDB (5 tablas)** | Almacenamiento de movimientos, conceptos fijos y flujo de caja |
| **API Gateway** | Endpoints REST para ingesta de movimientos y webhook de Slack |
| **EventBridge** | Bus central `bus-financiero` + Pipes desde DynamoDB Streams |
| **Glue Job** | Exportación diaria de DynamoDB a S3 con transformaciones Spark |
| **S3 (3 buckets)** | Frontend estático, reportes CSV y datos RAG |
| **CloudFront** | CDN para el frontend con OAC |
| **Cognito** | Autenticación con grupos `admin` y `general` |
| **OpenSearch** | Búsqueda vectorial (preparado para RAG) |
| **SES** | Envío de reportes por email |
| **SSM Parameter Store** | Catálogos financieros, reglas de compensación y proyecciones |
| **Secrets Manager** | Credenciales de Slack (webhook y bot token) |

---

## Flujo de Datos

```
Usuario en Slack (/registrar)
        │
        ▼
WebhookHandler ──► Modal dinámico con catálogo
        │
        ▼
InterpretadorRouters ──► EventBridge bus-financiero
        │
        ▼
Lambda especializada (Cuentas / Tarjetas / Proyecciones)
        │  Valida contra catálogo (SSM)
        ▼
DynamoDB (HistoriaTarjetas / HistoriaCuentasAltoRendimiento / ConceptosFijos*)
        │
        ▼  DynamoDB Stream → EventBridge Pipe
ConsolidaMovimientosFinancieros
        │  Aplica reglas de compensación (SSM)
        ▼
FlujoDeCaja (tabla consolidada)
        │
        ├──► NotificadorSlack (confirmación en Slack)
        │
        ▼  Glue Job (diario 20:00)
CSV + JSONL en S3
        │
        ├──► EnvioEmail (SES con URL prefirmada)
        └──► EmbeddingLambda (vectores con Amazon Titan)
                │
                ▼
        S3 Vectors (índice rag-index)
                │
                ▼  /consulta en Slack
        QueryRagEmbedding ──► Claude 3 Sonnet ──► Respuesta en Slack
```

---

## Lambdas

### Ingesta de movimientos
| Lambda | Descripción |
|---|---|
| `MovimientosCuentasEInversiones` | Registra movimientos de cuentas de alto rendimiento e inversiones. Valida dominio, cuenta y concepto contra el catálogo. Publica `movimiento.cuenta.confirmado`. |
| `MovimientosTarjetas` | Registra movimientos de tarjetas de crédito. Valida franquicia. Publica `movimiento.tarjeta.confirmado`. |
| `ParametrizarConceptosAhorro` | Registra conceptos fijos (gastos/ingresos proyectados). Enruta a `ConceptosFijosObligaciones` o `ConceptosFijosPersonal` según dominio. |

### Consolidación y cierre
| Lambda | Descripción |
|---|---|
| `ConsolidaMovimientosFinancieros` | Motor central. Escucha DynamoDB Streams de 4 tablas vía EventBridge Pipes. Aplica reglas de compensación desde SSM y actualiza `FlujoDeCaja`. |
| `CierreMensual` | Cron el 1° de cada mes. Calcula saldos finales y crea `SALDO_INICIAL` para el mes siguiente. |
| `ProyeccionesFijas` | Cron el 1° de cada mes. Carga proyecciones automáticas desde SSM y proyecta 3 meses adelante (idempotente). |

### Integración Slack
| Lambda | Descripción |
|---|---|
| `WebhookHandler` | Valida firma de Slack. Maneja slash commands `/registrar` y `/consulta`, construye modales dinámicos (incluyendo el tipo **Transferencia entre cuentas** con campo cuenta destino dinámico) y enruta submissions. |
| `InterpretadorRouters` | Transforma el state del modal al payload correcto y publica el evento en EventBridge. Soporta los tipos MOVIMIENTO_GENERAL, MOVIMIENTO_TARJETA, PROYECCION y TRANSFERENCIA. |
| `NotificadorSlack` | Escucha eventos confirmados en EventBridge y envía notificaciones al canal de Slack. |

### IA y reportes
| Lambda | Descripción |
|---|---|
| `EmbeddingLambda` | Disparada por S3 al crear archivos JSONL en `output/rag/`. Genera embeddings con Amazon Titan y los inserta en S3 Vectors. |
| `QueryRagEmbedding` | Recibe pregunta desde Slack, busca vectores similares y genera respuesta con Claude 3 Sonnet. |
| `EnvioEmail` | Disparada por S3 al crear CSV en `output/reports/`. Envía email con SES con URL prefirmada (válida 2 horas). |

---

## Tablas DynamoDB

| Tabla | PK | Streams | Propósito |
|---|---|---|---|
| `HistoriaTarjetas` | `trx_id` | ✅ | Movimientos de tarjetas de crédito |
| `HistoriaCuentasAltoRendimiento` | `trx_id` | ✅ | Movimientos de cuentas e inversiones |
| `ConceptosFijosObligaciones` | `trx_id` | ✅ | Gastos fijos del hogar (dominio CASA) |
| `ConceptosFijosPersonal` | `trx_id` | ✅ | Gastos fijos personales |
| `FlujoDeCaja` | `Dominio-Corte` / `Tipo-Concepto` | ❌ | Consolidación final por período |

---

## Reglas de Compensación

Las reglas se almacenan en SSM (`/flujo-caja/reglas-compensacion`, tier **Advanced** para soportar payloads mayores a 4 KB) y son evaluadas por `ConsolidaMovimientosFinancieros` en cada evento. Se cachean 5 minutos en memoria.

### Tipos de regla

- **Normal** — aplica sus acciones y marca el registro como procesado (bloquea el fallback default).
- **COMPLEMENTARIA** — aplica sus acciones pero no bloquea otras reglas ni el fallback. Usada para efectos secundarios como replicar saldos entre dominios sin duplicar escrituras.

### Operaciones disponibles en acciones

| Operación | Comportamiento |
|---|---|
| `DECREMENTAR` | Aplica el valor en negativo (abs del valor) |
| `INCREMENTAR` | Aplica el valor en positivo (abs del valor) |
| `REPLICAR` | Preserva el signo original del movimiento |

### Campos de acción avanzados

| Campo | Descripción |
|---|---|
| `dominio_destino` | Escribe en un dominio diferente al del registro origen |
| `concepto_destino` | Sobreescribe el concepto en el destino con un valor fijo |
| `origen_destino: USAR_ORIGEN` | Usa la cuenta origen del registro |
| `origen_destino: USAR_CUENTA_DESTINO` | Usa la cuenta destino (transferencias). Si es TARJETA, invierte el signo automáticamente |
| `origen_destino: USAR_CUENTA_AFECTADA` | Resuelve cuál de las dos cuentas (origen o destino) coincide con `incluir_origen` de la regla |

### Filtros de activación

| Filtro | Descripción |
|---|---|
| `incluir_conceptos` | Solo aplica si el concepto está en la lista |
| `excluir_conceptos` | No aplica si el concepto está en la lista |
| `incluir_dominio` | Solo aplica para los dominios indicados |
| `excluir_dominio` | No aplica para los dominios indicados |
| `incluir_origen` | Aplica si la cuenta origen **o** la cuenta destino está en la lista |
| `condicion_valor` | `POSITIVO`, `NEGATIVO` o `CUALQUIERA` |

### Reglas activas

| Regla | Tipo | Condición | Efecto |
|---|---|---|---|
| `CUENTA_DISMINUYE_GASTO` | Normal | Cuenta negativa, excluye AHORRO/INVERSIONES | Disminuye gasto proyectado y saldo de cuenta |
| `MOV_TARJETA_REDUCE_PROYECCION` | Normal | Tarjeta positiva | Disminuye gasto proyectado e incrementa saldo de tarjeta |
| `INGRESO_HOGAR_DISMINUYE_PROYECCION` | Normal | Concepto INGRESO HOGAR/SALARIO positivo | Disminuye proyección del mismo concepto e incrementa saldo |
| `TRANSFERENCIA_ENTRE_CUENTAS` | Normal | Concepto TRANSFERENCIA, cualquier valor | Decrementa cuenta origen e incrementa cuenta destino. Si destino es TARJETA, ambas decrementan |
| `KUBO_CASA_REPLICA_AHORRO_SALDO_APTO` | Complementaria | KUBO en dominio CASA (origen o destino) | Replica el movimiento en `AHORRO / SALDO APTO` preservando signo |
| `KUBO_PERSONAL_REPLICA_AHORRO_JOHAO` | Complementaria | KUBO en dominio PERSONAL (origen o destino) | Replica el movimiento en `AHORRO / AHORRO JOHAO` preservando signo |

---

## Transferencias entre cuentas

El slash command `/registrar` incluye el tipo **"Transferencia entre cuentas"**. Al seleccionarlo:

- Aparece el campo **Cuenta origen** con las cuentas del dominio seleccionado.
- Aparece el campo **Cuenta destino** con todas las cuentas y tarjetas del mismo dominio.
- Si la cuenta destino es una **tarjeta**, el sistema interpreta el movimiento como pago de deuda y decrementa ambos saldos.
- Si KUBO es origen o destino, las reglas complementarias replican el impacto en el dominio AHORRO.

---

## Glue Job

El job `export_dynamo_to_s3.py` se ejecuta diariamente a las 20:00 y realiza:

1. Lee `FlujoDeCaja` desde DynamoDB con Spark
2. Extrae dominio y corte de la clave compuesta `Dominio#Corte`
3. Ajusta signos (tarjetas en CAJA_ACTUAL → negativo, gastos en PROYECCION → negativo)
4. Genera tres salidas:
   - **CSV** en `s3://.../reports/` → dispara `EnvioEmail`
   - **JSONL** en `s3://.../rag/` → dispara `EmbeddingLambda`
   - **CSV** en bucket del frontend → disponible en CloudFront

---

## Dominios Financieros

El catálogo (`/flujo-caja/catalogo`) define los dominios válidos:

- **CASA** — Cuentas del hogar (BDO, KUBO, NEQUI, EFECTIVO), tarjetas y conceptos compartidos
- **PERSONAL** — Cuentas personales, conceptos de ahorro e ingresos individuales
- **AHORRO** — Cuentas de ahorro con metas específicas
- **INVERSIONES** — CDTs, acciones, monedas y cuentas de inversión

---

## Despliegue

### Prerrequisitos

- Terraform >= 1.5
- AWS CLI configurado con permisos suficientes
- Python 3.12 (para empaquetar layers)

### Inicializar estado remoto

```bash
cd terraform/modules/tf-state
terraform init
terraform apply
```

### Desplegar infraestructura

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### Variables principales

| Variable | Descripción |
|---|---|
| `project` | Nombre del proyecto (tag en todos los recursos) |
| `aws_region` | Región de despliegue |
| `ses_email` | Email verificado en SES para envío de reportes |

---

## Seguridad

- Roles IAM con permisos mínimos por Lambda
- Slack webhook validado por firma HMAC en cada request
- Credenciales de Slack en Secrets Manager (nunca en variables de entorno directas)
- API Gateway con autorización Cognito en todos los endpoints (excepto webhook público)
- CloudFront con OAC — el bucket S3 del frontend no es público
- Catálogos y reglas en SSM con cache en memoria para reducir latencia y costos
