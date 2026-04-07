# API: Agents KPIs V2

Endpoint unificado de KPIs de agentes: availability (AgentActivityEventV2), interactions (interactions_summary VOICE) y derived.

## Endpoint

```
GET /api/v1/reportes/agents_kpis_v2/
```

## Parámetros

| Parámetro | Obligatorio | Descripción |
|-----------|-------------|-------------|
| `date_start` | Sí | Fecha inicio (YYYY-MM-DD). |
| `date_end`   | Sí | Fecha fin (YYYY-MM-DD). |
| `agent_id`  | No | Filtrar por ID de agente (entero). |
| `group_by`  | No | `agent` (una fila por agente) o `day` (una fila por agente y día). Default: `day`. |
| `include_pause_breakdown` | No | Incluir desglose de pausas por pause_id/aux_code. Default: 1. |
| `include_interactions`    | No | Incluir bloque interactions. Default: 1. |
| `include_derived`         | No | Incluir bloque derived. Default: 1. |

### Ejemplos

```
GET /api/v1/reportes/agents_kpis_v2/?date_start=2025-02-01&date_end=2025-02-05
GET /api/v1/reportes/agents_kpis_v2/?date_start=2025-02-01&date_end=2025-02-05&group_by=agent&agent_id=42
```

## Unidades y tipos

- **Segundos**: todas las duraciones están en segundos.
- **Tipos**:
  - **availability.\*_seconds**: `int` (segundos enteros).
  - **interactions.\*_seconds**: `float` con 3 decimales (vienen de DB con decimales).
  - **derived.\*_seconds**: `float` con 3 decimales.
  - **Ratios** (ready_ratio, pause_ratio, acw_ratio, oncall_ratio) y **sales_per_hour**: `float` con 4 decimales.

## Definición de campos

### availability

| Campo | Tipo | Descripción |
|-------|------|-------------|
| session_seconds | int | Tiempo total de sesión en el rango (segundos). |
| ready_seconds   | int | Tiempo en estado READY. |
| pause_seconds  | int | Tiempo en estado PAUSED. |
| acw_seconds    | int | Tiempo en estado ACW. |
| ready_ratio, pause_ratio, acw_ratio | float | Ratios respecto a session_seconds (4 decimales). |
| sessions_count | int | Cantidad de sesiones. |
| pauses_count, acw_count | int | Cantidad de eventos. |
| pause_breakdown | array | Si se pide: lista de `{pause_id, aux_code, seconds}`. |

### interactions

Los campos de duración en segundos provienen de la tabla `interactions_summary`. En particular, `wait_conn_duration` y `avg_wait_conn_duration` provienen del campo **wait_conn_duration** (tiempo de espera hasta conexión con agente), no de un campo `queue_time` ni `queue_duration`.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| interactions_total, interactions_inbound, interactions_outbound | int | Conteos. |
| answered_count, cancel_count, sales_count | int | Conteos. |
| talk_seconds | float (3 dec) | Tiempo en llamada (agent_duration). |
| avg_talk_seconds_answered | float (3 dec) | Promedio de duración en contestadas. |
| wait_conn_duration | float (3 dec) | Tiempo de espera hasta conexión (wait_conn_duration). |
| avg_wait_conn_duration | float (3 dec) | Promedio tiempo de espera hasta conexión (wait_conn_duration). |

### derived

| Campo | Tipo | Descripción |
|-------|------|-------------|
| oncall_seconds   | float (3 dec) | Igual a interactions.talk_seconds. |
| oncall_ratio     | float (4 dec) | oncall_seconds / session_seconds. |
| idle_real_seconds| float (3 dec) | max(ready_seconds - oncall_seconds, 0). |
| sales_per_hour   | float (4 dec) | sales_count / (session_seconds/3600). |

## Invariantes (consistencia matemática)

1. **Availability**: `ready_seconds + pause_seconds + acw_seconds == session_seconds` (tolerancia ≤ 1 segundo por edge cases).
2. **Pause breakdown**: `SUM(pause_breakdown[].seconds) == pause_seconds` por (agent_id, date) (tolerancia ≤ 1 segundo).

Si se activa `REPORTES_KPIS_V2_STRICT_VALIDATION` (setting o env), el endpoint devuelve 500 cuando alguna invariante falla. Por defecto solo se registra un WARNING en logs.

## Origen de datos (interactions_summary)

El endpoint lee las interacciones desde la tabla/vista `interactions_summary`. Si un proceso externo (ETL, otro servicio) es el que alimenta esa tabla, debe escribir el tiempo de espera hasta conexión en la columna **wait_conn_duration**; Django no expone ni usa `queue_time` ni `queue_duration`.

## Limitaciones (V1)

- Con `group_by=day`, la fecha asignada es la del **inicio de sesión** (session_start en timezone del servidor), no la del día calendario de la interacción. Las interacciones se agrupan por día local según `start_time` en timezone configurado; la availability va por sesión, por lo que una sesión que cruza medianoche se asigna al día en que inició la sesión.
