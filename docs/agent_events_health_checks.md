# Health checks — eventos de actividad de agente (Legacy y V2)

Documentación de los health checks para **reportes_app_actividadagentelog** (legacy) y **reportes_app_agentactivityeventv2** (V2), en contexto dual-write y con la regla de dominio: **SESSION_LOGIN implica READY implícito** (no se requiere STATE_READY posterior).

Todas las queries aceptan parámetros `:since` y `:until` (timestamptz). Índices recomendados:
- Legacy: `(agente_id, time)`
- V2: `(agente_id, ts)`

---

## A) Legacy — UNPAUSEALL con pausa_id no nulo (ERROR)

**Regla:** UNPAUSEALL debe persistirse siempre con `pausa_id` NULL o vacío.

**Resultado:** 0 filas → OK. \>0 filas → **CRIT**.

```sql
-- Check A: UNPAUSEALL con pausa_id no nulo
SELECT id, agente_id, time, event, pausa_id
FROM reportes_app_actividadagentelog
WHERE time >= %(since)s AND time < %(until)s
  AND event = 'UNPAUSEALL'
  AND (pausa_id IS NOT NULL AND pausa_id != '');
```

---

## B) Legacy — Logout duplicado consecutivo (ERROR)

**Regla:** No debe haber SESSION_LOGOUT o REMOVEMEMBER consecutivos sin un LOGIN intermedio.

**Resultado:** 0 filas → OK. \>0 filas → **WARN** (o CRIT si volumen alto).

```sql
-- Check B: Logout duplicado consecutivo (LAG por agente)
WITH ordered AS (
  SELECT id, agente_id, time, event,
    LAG(event) OVER (PARTITION BY agente_id ORDER BY time, id) AS prev_event
  FROM reportes_app_actividadagentelog
  WHERE time >= %(since)s AND time < %(until)s
)
SELECT id, agente_id, time, event, prev_event
FROM ordered
WHERE event IN ('SESSION_LOGOUT', 'REMOVEMEMBER')
  AND prev_event IN ('SESSION_LOGOUT', 'REMOVEMEMBER');
```

---

## C) Legacy — Login duplicado consecutivo (WARN)

**Regla:** SESSION_LOGIN/ADDMEMBER consecutivos sin logout intermedio suelen indicar flapping.

**Resultado:** Pocos casos → WARN. Muchos por agente → WARN elevado.

```sql
-- Check C: Login duplicado consecutivo
WITH ordered AS (
  SELECT id, agente_id, time, event,
    LAG(event) OVER (PARTITION BY agente_id ORDER BY time, id) AS prev_event
  FROM reportes_app_actividadagentelog
  WHERE time >= %(since)s AND time < %(until)s
)
SELECT id, agente_id, time, event, prev_event
FROM ordered
WHERE event IN ('SESSION_LOGIN', 'ADDMEMBER')
  AND prev_event IN ('SESSION_LOGIN', 'ADDMEMBER');
```

---

## D) Legacy — Eventos de estado fuera de sesión (WARN)

**Regla corregida:** PAUSEALL/UNPAUSEALL son válidos solo si existe una sesión abierta (último LOGIN sin LOGOUT posterior). READY implícito desde LOGIN es válido; no se requiere STATE_READY previo.

**Detectar como WARN:**
- PAUSEALL/UNPAUSEALL sin LOGIN previo en el rango.
- PAUSEALL/UNPAUSEALL después de LOGOUT sin nuevo LOGIN.

**No marcar como error:** LOGIN → PAUSEALL (sin READY explícito).

Se usa balance de sesión: +1 por LOGIN, -1 por LOGOUT; PAUSEALL/UNPAUSEALL inválidos cuando el balance previo es 0.

```sql
-- Check D: PAUSEALL/UNPAUSEALL fuera de sesión abierta
WITH session_balance AS (
  SELECT id, agente_id, time, event,
    SUM(CASE WHEN event IN ('SESSION_LOGIN', 'ADDMEMBER') THEN 1
             WHEN event IN ('SESSION_LOGOUT', 'REMOVEMEMBER') THEN -1
             ELSE 0 END)
      OVER (PARTITION BY agente_id ORDER BY time, id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS balance_before
  FROM reportes_app_actividadagentelog
  WHERE time >= %(since)s AND time < %(until)s
),
pause_unpause AS (
  SELECT id, agente_id, time, event, balance_before
  FROM session_balance
  WHERE event IN ('PAUSEALL', 'UNPAUSEALL')
)
SELECT id, agente_id, time, event, balance_before
FROM pause_unpause
WHERE balance_before IS NULL OR balance_before <= 0;
```

---

## E) Legacy — Pausas abiertas al logout (WARN)

**Regla:** Si el agente hace LOGOUT estando en PAUSEALL sin UNPAUSEALL previo, el sistema cierra la pausa implícitamente en logout. Comportamiento tolerado (p. ej. desconexiones abruptas).

**Detección:** PAUSEALL seguido directamente por SESSION_LOGOUT (o REMOVEMEMBER) sin UNPAUSEALL intermedio.

**Resultado:** WARN informativo.

```sql
-- Check E: PAUSEALL seguido de LOGOUT sin UNPAUSEALL (pausa abierta al logout)
WITH ordered AS (
  SELECT id, agente_id, time, event,
    LAG(event) OVER (PARTITION BY agente_id ORDER BY time, id) AS prev_event
  FROM reportes_app_actividadagentelog
  WHERE time >= %(since)s AND time < %(until)s
)
SELECT id, agente_id, time, event, prev_event
FROM ordered
WHERE event IN ('SESSION_LOGOUT', 'REMOVEMEMBER')
  AND prev_event = 'PAUSEALL';
```

---

## F) V2 — Consistencia lógica por schema (ERROR)

**Reglas estrictas:**
- `event_type = 'STATE_READY'` con `pause_id` o `aux_code` → ERROR
- `event_type = 'STATE_ACW'` con `pause_id` o `aux_code` → ERROR
- `event_type = 'STATE_PAUSED'` sin `pause_id` y sin `aux_code` → ERROR
- SESSION_* nunca deben tener `pause_id` ni `aux_code`

**Resultado:** 0 filas → OK. \>0 filas → **CRIT**.

```sql
-- Check F: V2 inconsistencias de schema
SELECT id, agente_id, ts, event_type, pause_id, aux_code
FROM reportes_app_agentactivityeventv2
WHERE ts >= %(since)s AND ts < %(until)s
  AND (
    (event_type = 'STATE_READY' AND (pause_id IS NOT NULL OR (aux_code IS NOT NULL AND aux_code != '')))
    OR (event_type = 'STATE_ACW'  AND (pause_id IS NOT NULL OR (aux_code IS NOT NULL AND aux_code != '')))
    OR (event_type = 'STATE_PAUSED' AND (pause_id IS NULL AND (aux_code IS NULL OR aux_code = '')))
    OR (event_type IN ('SESSION_LOGIN', 'SESSION_LOGOUT') AND (pause_id IS NOT NULL OR (aux_code IS NOT NULL AND aux_code != '')))
  );
```

---

## G) V2 — Estado implícito READY validado (INFO)

**Check informativo (no error):** SESSION_LOGIN seguido directamente por STATE_PAUSED, STATE_ACW o SESSION_LOGOUT es **válido** (READY implícito).

Cuenta estos casos y repórtalos solo como **INFO** para análisis.

```sql
-- Check G (INFO): Login seguido de PAUSED/ACW/LOGOUT sin STATE_READY explícito
WITH ordered AS (
  SELECT id, agente_id, ts, event_type,
    LAG(event_type) OVER (PARTITION BY agente_id ORDER BY ts, id) AS prev_event_type
  FROM reportes_app_agentactivityeventv2
  WHERE ts >= %(since)s AND ts < %(until)s
)
SELECT id, agente_id, ts, event_type, prev_event_type
FROM ordered
WHERE event_type IN ('STATE_PAUSED', 'STATE_ACW', 'SESSION_LOGOUT')
  AND prev_event_type = 'SESSION_LOGIN';
```

---

## H) Dual-write parity (Legacy vs V2)

Comparar por rango temporal:
- Legacy SESSION_LOGIN vs V2 SESSION_LOGIN
- Legacy SESSION_LOGOUT vs V2 SESSION_LOGOUT
- Legacy PAUSEALL vs V2 (STATE_PAUSED + STATE_ACW)
- Legacy UNPAUSEALL vs V2 STATE_READY

**No comparar:** READY implícito (no existe como evento en legacy ni siempre en V2).

**Resultado:** Diferencias \> umbral → WARN. Diferencias grandes → CRIT.

```sql
-- Check H: Conteos legacy vs V2 (ejecutar y comparar en aplicación)
-- Legacy conteos
SELECT event, COUNT(*) AS cnt
FROM reportes_app_actividadagentelog
WHERE time >= %(since)s AND time < %(until)s
  AND event IN ('SESSION_LOGIN', 'SESSION_LOGOUT', 'PAUSEALL', 'UNPAUSEALL')
GROUP BY event;

-- V2 conteos (PAUSEALL legacy = STATE_PAUSED + STATE_ACW en V2)
SELECT
  CASE event_type
    WHEN 'SESSION_LOGIN' THEN 'SESSION_LOGIN'
    WHEN 'SESSION_LOGOUT' THEN 'SESSION_LOGOUT'
    WHEN 'STATE_PAUSED' THEN 'PAUSEALL'
    WHEN 'STATE_ACW' THEN 'PAUSEALL'
    WHEN 'STATE_READY' THEN 'UNPAUSEALL'
  END AS event_legacy,
  COUNT(*) AS cnt
FROM reportes_app_agentactivityeventv2
WHERE ts >= %(since)s AND ts < %(until)s
  AND event_type IN ('SESSION_LOGIN', 'SESSION_LOGOUT', 'STATE_PAUSED', 'STATE_ACW', 'STATE_READY')
GROUP BY CASE event_type
    WHEN 'SESSION_LOGIN' THEN 'SESSION_LOGIN'
    WHEN 'SESSION_LOGOUT' THEN 'SESSION_LOGOUT'
    WHEN 'STATE_PAUSED' THEN 'PAUSEALL'
    WHEN 'STATE_ACW' THEN 'PAUSEALL'
    WHEN 'STATE_READY' THEN 'UNPAUSEALL'
  END;
```

La aplicación debe restar conteos legacy vs V2 (agrupando STATE_PAUSED+STATE_ACW como PAUSEALL) y aplicar umbrales.

---

## I) Flapping detection (WARN)

**Regla:** SESSION_LOGOUT seguido de SESSION_LOGIN dentro de una ventana corta (ej. 2 segundos).

**Clasificación:** Casos aislados → WARN. Frecuente por agente → WARN elevado.

```sql
-- Check I: Logout → Login en ventana corta (ej. 2 s)
WITH ordered AS (
  SELECT id, agente_id, time, event,
    LAG(event) OVER (PARTITION BY agente_id ORDER BY time, id) AS prev_event,
    LAG(time) OVER (PARTITION BY agente_id ORDER BY time, id) AS prev_time
  FROM reportes_app_actividadagentelog
  WHERE time >= %(since)s AND time < %(until)s
)
SELECT id, agente_id, time, event, prev_event, prev_time,
  EXTRACT(EPOCH FROM (time - prev_time)) AS gap_seconds
FROM ordered
WHERE event IN ('SESSION_LOGIN', 'ADDMEMBER')
  AND prev_event IN ('SESSION_LOGOUT', 'REMOVEMEMBER')
  AND (time - prev_time) BETWEEN INTERVAL '0' AND INTERVAL '2 seconds';
```

---

## Resumen de severidad por check

| Check | Descripción                         | 0 filas / OK     | \>0 o desvío   |
|-------|-------------------------------------|------------------|----------------|
| A     | UNPAUSEALL con pausa_id             | OK               | CRIT           |
| B     | Logout duplicado consecutivo        | OK               | WARN (CRIT si volumen alto) |
| C     | Login duplicado consecutivo         | OK               | WARN           |
| D     | PAUSE/UNPAUSE fuera de sesión       | OK               | WARN           |
| E     | Pausa abierta al logout             | OK               | WARN (tolerado)|
| F     | V2 schema (READY/ACW/PAUSED/SESSION)| OK               | CRIT           |
| G     | Login → PAUSED/ACW/LOGOUT sin READY | —                | INFO           |
| H     | Paridad legacy vs V2                | Dentro umbral    | WARN / CRIT    |
| I     | Flapping logout→login \<2s          | OK               | WARN           |

---

## Recomendaciones operativas

### Qué checks correr diariamente

- **Críticos (todos los días):** A, F, H.  
  A y F detectan errores de datos; H detecta desvíos de dual-write.
- **Advertencias (diarios):** B, D, I.  
  B y D detectan secuencias anómalas; I detecta flapping.
- **Opcional diario:** C, E.  
  C para flapping de logins; E para documentar pausas cerradas en logout.
- **Informativo (según necesidad):** G.  
  Para análisis de uso de READY implícito.

### Umbrales sugeridos

- **H (paridad):**  
  - WARN si diferencia absoluta legacy vs V2 para cualquier evento \> 1% del total de eventos en el rango o \> 10 eventos.  
  - CRIT si \> 5% o \> 100 eventos.
- **B (logout duplicado):**  
  - CRIT si \> 50 filas en la ventana o si un agente tiene \> 5 ocurrencias.
- **I (flapping):**  
  - WARN por cada fila; CRIT si un agente tiene \> 20 en el rango.

### Filtro por agente

Todas las queries pueden restringirse añadiendo `AND agente_id = %(agent_id)s` cuando se desee auditar un agente concreto.

---

## Eventos sintéticos V2 (heartbeat/session expiry)

Con heartbeat de presencia habilitado:

- `event_type='SESSION_LOGOUT'` puede escribirse como evento sintético solo en V2.
- `source='HB_TIMEOUT'` representa cierre por timeout de heartbeat.
- `source='SESS_EXPIRED'` representa cierre por expiración de sesión HTTP detectado en login.
- `metadata.reason` permite distinguir `timeout` y `session_expired`.

Reglas operativas:

1. No duplicar `HB_TIMEOUT` para el mismo agente en la ventana corta de idempotencia.
2. Si existe `HB_TIMEOUT` reciente, Redis debe converger a `STATUS='UNAVAILABLE'`.
3. Legacy puede divergir históricamente en cierres sintéticos; la fuente para presencia abierta/cerrada es V2.

---

*Documento generado para monitoreo operativo y validación de paridad legacy vs V2. No modifica lógica de escritura, migraciones ni reportes.*
