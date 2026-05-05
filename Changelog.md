# Changelog Técnico y Arquitectónico - `oml-773-dev-oml-3`

Comparación analizada: `develop` -> `oml-773-dev-oml-3`.

---

## 1. Resumen Ejecutivo

La rama `oml-773-dev-oml-3` materializa una evolución profunda y fundacional en la arquitectura de la plataforma OMniLeads, allanando el camino definitivo hacia la versión OML 3.0. Esta actualización se enfoca en el desacoplamiento agresivo de la lógica de negocio respecto a la infraestructura telefónica subyacente (Asterisk), migrando de un paradigma fuertemente acoplado (basado en escritura de archivos locales e interacción síncrona vía AMI) hacia un **ecosistema asíncrono, distribuido y orientado a eventos**.

El valor principal para el producto y la operación radica en la entrega de métricas de interacciones absolutamente consistentes mediante una **trazabilidad omnicanal unificada**, la disponibilidad de dashboards de supervisión verdaderamente en tiempo real (gracias al motor Redis Gears y WebSockets), soporte estructural para Inteligencia Artificial (VoiceBots) y agentes remotos, así como la modernización completa del stack (Django 6.0, ASGI, Python 3.12). 

---

## 2. Nuevas Funcionalidades (Features)

A nivel funcional, se introducen capacidades expansivas que mejoran la gestión diaria del contact center:

- **Reporte Centro de Contacto / Interacciones**: Nuevo reporte omnicanal integral. Consolida y presenta las métricas operativas de Voz, WhatsApp y otras canalidades. Permite desglosar llamadas atendidas/no atendidas, volumen de tráfico por hora/día/mes, gestión de egresos, conversaciones de chat respondidas/no respondidas, y provee un detalle sin precedentes sobre la trazabilidad de transferencias cruzadas entre múltiples campañas.
- **Exportaciones CSV Ampliadas y Optimizadas**: Se crearon múltiples endpoints diseñados para el manejo de altos volúmenes de datos asincrónicos, proveyendo al cliente de progreso en vivo vía WebSockets. Estas exportaciones cubren canalidades, reportes de voz, chats de WhatsApp y todo el registro de actividad de agentes.
- **Actividad de Agentes V2**: Se consolida un nuevo modelo de *event sourcing* (`AgentActivityEventV2`) para trazar milimétricamente la vida operativa del agente: login, logout, ready, pausas, trabajo post-llamada (ACW) y estados de hold/unhold. Esto está respaldado por una nueva API de KPIs V2 y la vista `agents-activity-v2`.
- **Dashboard de Agente V2**: El propio agente gana una nueva pantalla de métricas de rendimiento personal, dotada de gráficos interactivos, detalle del historial de sus pausas y la lista detallada de sus últimas llamadas gestionadas.
- **Supervisión de Contact Center y Dashboards en Tiempo Real**: Se agregó la aplicación `dashboard_camp_app`. Proporciona nuevas vistas gerenciales y operativas de la salud del contact center que se hidratan y refrescan de forma continua (push-based) sin requerir acciones del usuario, consumiendo métricas instantáneas directamente desde Redis.
- **Motor de Transferencias Avanzado sobre ACD**: Un set de nuevas APIs permite gestionar transferencias (ciegas a un agente, endpoint o campaña), transferir a un agente específicamente disponible, establecer transferencias consultativas (flujos start/complete/cancel), así como ejecutar comandos de hold/unhold, spy (escucha sigilosa), conferencias de 3 vías y finalizaciones de llamadas nativamente gestionadas por el worker del ACD.
- **Agentes Remotos y VoiceBots**: Se introducen banderas (`flags`) en el perfil del agente (`sip_remote`, `voicebot`) junto con campos para definir su troncal y extensión. La interfaz gráfica permite ahora rutear destinos entrantes directamente hacia un "Agente Remoto" y asignar bots a campañas convencionales, validando estos estados desde la interfaz.
- **Integración Nativa Verloop / Webhooks para Bots**: Creación de un webhook especializado que recibe eventos asíncronos de sistemas como Verloop, creando o actualizando calificaciones de la interacción. Cuando un bot finaliza su `GESTION_BOT`, se publica el comando `voicebot_transfer_proceed` a Redis para instruir al ACD a que asigne el cliente a un humano de segunda línea.
- **Grabaciones Directas y Speech Analysis**: La obtención y reproducción de la URL de grabación ahora descansa orgánicamente sobre el nuevo `InteractionsSummary`. Se agrega además el modelo `SpeechAnalysis`, encargado de disparar tareas asíncronas a *Gearman* para la transcripción automática del audio y la posterior puntuación del sentimiento (QA de la interacción).
- **Herramientas para Desarrolladores**: Introducción de entornos contenedorizados (`docker-compose.test.yml`, `run_tests.sh`, `run_linter.sh`) para una ejecución determinista de las baterías de pruebas y la corrección de formato.

---

## 3. Análisis de Cambios Arquitectónicos / Técnicos (Deep Dive)

La reingeniería llevada a cabo en esta rama responde a las necesidades críticas de escalabilidad de OML 3.0. A continuación, se detalla la especificación de los mayores cambios arquitectónicos:

### 3.1. Upgrade de Stack y el Nuevo Versionado
Para asegurar un ciclo de vida prolongado y soporte de las últimas funcionalidades de rendimiento asíncrono, se ejecutó un recambio fundacional del ecosistema:
- **Base e Intérprete**: Migración de la imagen a `Python 3.12-slim-trixie`. 
- **Framework Web (Django 6)**: Se concretó el salto abismal desde Django `3.2.19` hasta **`6.0.4`**. Este cambio requirió un exhaustivo esfuerzo de refactorización que abarcó:
  - Transición del middleware legacy (`MIDDLEWARE_CLASSES` a `MIDDLEWARE`).
  - Deprecación total de `ugettext` en favor de `gettext/gettext_lazy` para la internacionalización.
  - La consolidación de estructuras anidadas reemplazando módulos externos por el nativo `models.JSONField`.
  - Reemplazo del deprecado `NullBooleanField` en el historial de migraciones.
- **Capa Asíncrona (ASGI)**: Se subió Channels a `4.3.2`, Daphne a `4.1.2`, y `channels-redis` a `4.3.0`, garantizando que el manejo de miles de WebSockets simultáneos sea tolerante a la carga gracias a las integraciones modernas con Python asíncrono.
- **Dependencias Complementarias**: Se actualizó el cliente de Redis (de 5.0.1 a 7.1.0), uWSGI a 2.0.31, se introdujeron los manejadores de background `apscheduler` y `gearman3`, y se modernizaron las interfaces con AWS S3 (`boto/botocore`).

### 3.2. Optimizaciones Generales de Rendimiento
Para evitar el estrangulamiento de la base de datos y la caché bajo cargas altas (situación común en implementaciones de múltiples tenants o alto tráfico telefónico):
- **Acceso a Redis No Bloqueante**: Se erradicó el uso de comandos altamente perjudiciales como `KEYS *`, reemplazándolos con la iteración controlada vía **`SCAN`** apoyada por ejecuciones en **pipelines**. Esto previene el bloqueo del single-thread de Redis.
- **Sincronización en Memoria Eficiente**: Procesos pesados como la asignación, remoción o agregación de decenas de agentes a campañas ahora impactan la jerarquía relacional de Redis (`OML:CAMPAIGN-AGENTS`) reduciendo la dependencia en costosos commits SQL transaccionales.

### 3.3. Transición a una Arquitectura Más *Stateless* (Sin Estado Local)
OMniLeads fue diseñado originalmente asumiendo que los contenedores de telefonía y web compartían volúmenes. Con `oml-773-dev-oml-3`, Django se desprende permanentemente de las responsabilidades de bajo nivel que le impedían escalar horizontalmente:
- **Fin de la Escritura de Archivos**: Se dejen de escribir localmente configuraciones de Asterisk (`oml_queues.conf`, `oml_extensions_outr.conf`). 
- **Gestión Descentralizada**: Los agentes dinámicos ya no se añaden a las colas de la PBX emitiendo reloads o interfaces AMI pesadas. En su lugar, el sistema centraliza todo mandato operativo en un clúster de **Redis**. Esto permite levantar *N* réplicas del frontend Django de manera totalmente *stateless*; si uno falla, no arrastra el estado de telefonía porque el puente de interacción web/pbx ahora es efímero.
- **Fin de la Duplicación de Estados (Login/Pausas sin AMI)**: Históricamente, las acciones de `login`, `logout`, `pause` y `unpause` dependían de la emisión de comandos a través del protocolo AMI de Asterisk. Esto generaba un problema de sincronismo y una "duplicación del estado": la condición del agente existía simultáneamente a nivel de aplicación (Redis) y a nivel interno del motor telefónico (visible nativamente al ejecutar un comando como `Queue Show`). Al abandonar el uso de AMI para gestionar estas transiciones de presencia, el único y verdadero estado del agente (`STATUS`) pasa a vivir de forma unificada en **Redis** (`OML:AGENT:{id}`). El motor ACD ahora consulta exclusivamente esta fuente de verdad para tomar decisiones de ruteo, eliminando de raíz las históricas inconsistencias entre el motor SIP y la interfaz web.

### 3.4. Nuevos Modelos Analíticos y Trazabilidad (El Fin de los Logs Disgregados)
Se cambió la heurística del armado de reportes. En lugar de ejecutar minería de datos pesada sobre logs dispares en cada solicitud de reporte, se materializan resúmenes concretos y viajes unificados (*journeys*):
- `interactions_summary`: Funcionan como un registro consolidado de cada punto de contacto de un lead. Centralizan los saltos entre bots, campañas entrantes y agentes humanos para la canalidad Telefonica.
- `interaction_transfers` : Crean una trazabilidad de auditoría sobre el enrutamiento intra-PBX.
- `AgentActivityEventV2`: Reemplaza la lógica de adivinar el estado de conexión del agente leyendo eventos SIP/Llamada. V2 es un almacén de eventos (Event Store) explícito. Soluciona de raíz el molesto fenómeno de "flapping" en las métricas de conexión/horas trabajadas.

### 3.5. La Integración Estructural de VoiceBots en el Contact Center
Los Voicebots dejan de ser un desarrollo *ad-hoc* para integrarse como entidades dentro del core.
Al ampliar `AgenteProfile` con flags (`sip_remote`, `voicebot`) e identificar troncales (`voicebot_trunk`), el motor del ACD ahora puede rutear llamadas a una IA exactamente igual que a un agente humano. Esto otorga una ventaja inmensa: **los bots figuran en la reportería**. Es posible comparar el AHT (Average Handle Time), la tasa de resolución, o los tiempos de abandono del Voicebot en la misma pantalla en la que se evalúa a un supervisor humano. Adicionalmente, el bot puede utilizar webhooks (ej. integraciones con NLP/NLU externo) para instruir al ACD telefónico la transferencia asíncrona hacia un operador vivo de segundo nivel en el momento apropiado de la conversación.

### 3.6. Reemplazo de CRON y Tareas Programadas por Schedulers y Eventos
Las tareas programadas tipo CRON, si bien sencillas, causan picos de consumo de CPU/I-O impredecibles ("Thundering Herd") y su granularidad por minuto introducía alta latencia.
El esquema *legacy* ha sido barrido y reemplazado por demonios residentes de alta disponibilidad gestionados por **APScheduler**:
- Procesos como `actualizar_reporte_dia_actual_agentes_scheduler` o `clean_dashboard_redis` mantienen una sincronía precisa sin abrumar la base PostgreSQL.
- **Heartbeats y Cierre de Sesiones Inteligentes**: La presencia del agente no es validada mediante CRON, sino mediante pulsos (`heartbeats`) en Redis con un *Time-to-Live* (TTL). Si el navegador del agente falla abruptamente o hay un corte de red de internet, el servicio residente `presence_heartbeat_scheduler` detecta la evaporación de la clave en Redis, y escribe sintéticamente en el motor V2 un evento de desconexión "UNAVAILABLE", estabilizando automáticamente los tableros.

### 3.7. El Cambio de Paradigma: PhoneJS, Django y las TASKs al Motor ACD
Históricamente, cuando un agente en la interfaz web (`PhoneJS`) deseaba hacer una transferencia o colgar, enviaba una solicitud al backend Django. Django, actuando como un monolito bloqueante, abría una conexión de red (AMI) hacia la PBX y negociaba la instrucción.
En OML 3.0, el flujo fue re-arquitectado para ser reactivo y de alta velocidad:
1. **Frontend**: El PhoneJS emite la solicitud REST/WebSocket al backend.
2. **Backend**: Django valida el permiso, pero ya no interactúa con Asterisk directamente. En su lugar, empaqueta una tarea estructurada (TASK).
3. **Bus de Mensajes**: Django publica esta TASK en un canal seguro de **Redis Pub/Sub** (por ejemplo, `acd:commands:{NODE_ID}`).
4. **Ejecución ACD**: Un worker subyacente independiente (el nuevo *OMniDialer/ACD Service*) que está suscrito al canal recoge la TASK asíncronamente y la aplica físicamente en el núcleo telefónico, regresando el evento de confirmación.
Este patrón desacoplado es lo que permite que OML escale, resista fallos de red y procese comandos de cientos de agentes al unísono.
Un coomportamiento similar sucede cuando se genera una llamada saliente manual.

### 3.8. Supervisión Real-time Sub-milisegundo (Redis Streams, Gears y Pub/Sub)
El antiguo flujo que nutría los paneles de supervisores padecía latencias inherentes debido a que dependía de que un CRON hiciera polling a la SQL cada 60 segundos y promediara los resultados.
La nueva arquitectura implementada en esta rama invierte ese proceso para ser "Push-Based":
- **Ingesta por Streams**: Cada estado interno de Asterisk y cada click de un agente dispara un evento inmutable registrado en **Redis Streams** de manera instantánea.
- **Procesamiento de Reglas en Borde**: Haciendo uso del poderoso motor distribuido de **Redis Gears** (y de los listeners locales `supervision_events_listener`), OML evalúa estos deltas de evento tan pronto ingresan. Se incrementan los contadores, się cambian los *status* lógicos y se consolidan en las estructuras in-memory (`OML:CALLDATA:CAMP:{id}`).
- **Propagación ASGI**: Inmediatamente, la infraestructura ASGI de Channels empaqueta este payload y lo despacha vía **WebSockets** al navegador de todos los supervisores suscritos (`SupervisionConsumer`), repintando las métricas en la interfaz reactiva sin refrescar la página.

### 3.9. Nuevo Dashboard de Agente V2 (Autogestión y Transparencia Operativa)
Con el objetivo de empoderar al operador telefónico y reducir la dependencia exclusiva de los paneles de supervisión, se introdujo una vista dedicada puramente al agente (Dashboard de Agente V2). 
Técnicamente, esta nueva interfaz se alimenta de la nueva API de KPIs V2 que consume directamente los almacenes de eventos `AgentActivityEventV2` y `interactions_summary`. 
- **Transparencia en Tiempo Real**: El agente puede visualizar sus propias métricas (como tiempo de login, tiempo total en pausa, tiempo efectivo en llamada y ACW).
- **Trazabilidad Personal**: Permite al operador auditar sus pausas históricas del día y visualizar el detalle de las últimas llamadas gestionadas, mejorando el control de calidad propio.
- **Desacople Visual**: Al estar construido sobre los nuevos endpoints asíncronos y modelos de resumen unificados, la carga de este dashboard personal es sumamente liviana y no impacta en las consultas pesadas que anteriormente bloqueaban el servidor al intentar calcular estos tiempos directamente desde el log de Asterisk.

### 3.10. Mejoras en la Implementación de Storage (S3)
El manejo de grabaciones y descarga de audios fue refactorizado para ser agnóstico del proveedor de la nube y mucho más robusto:
- **Desacople de S3 Exclusivo**: El sistema `StorageService` ya no asume estrictamente a AWS S3. Se adoptó una nomenclatura neutra (`BUCKET_*`) que soporta nativamente MinIO, DigitalOcean Spaces, GCP y cualquier proveedor S3-Compatible sin requerir bifurcaciones lógicas complejas.
- **Doble Endpoint (Público/Interno)**: Se resuelve un problema histórico de enrutamiento al introducir la separación explícita entre `BUCKET_ENDPOINT` y `BUCKET_ENDPOINT_INTERNAL`. Esto permite que el backend de Django consuma el storage de forma ultra-rápida por la red local (interna a Docker/K8s) para procesar grabaciones, pero que a su vez genere y firme las URLs (Pre-Signed) usando el endpoint público para que el navegador del supervisor (cliente final) pueda reproducir el audio sin problemas de CORS ni VPNs.
- **Obtención Transparente**: Se elimina la bandera `S3_STORAGE_ENABLED`. Ahora el motor intenta resolver la ubicación del archivo a nivel de storage unificado de forma transparente.

---

## 4. Correcciones (Bugfixes)

- **Prevención de Flapping**: Se corrige la duplicidad de estados de presencia (logins/logouts rebotantes). Ahora las acciones de entrada/salida son de naturaleza idempotente y poseen un *cooldown* de seguridad configurable por entorno.
- **Normalización de Pausas (`UNPAUSEALL`)**: Se elimina la persistencia errónea del `pausa_id` en flujos de despausado masivo, salvaguardando la santidad de los reportes laborales del agente.
- **Abandono Inteligente**: Los timeouts de heartbeat ahora insertan cierres de sesión controlados (eventos sintéticos V2) mitigando el problema de los "agentes fantasma" clavados eternamente en el sistema.
- **Independencia Operativa del Agente**: Los procesos de `hold` y `unhold` ya no están encadenados a los inestables eventos legacy de Asterisk. Al ser manejados en `AgentActivityEventV2`, el estado mental y operativo del recurso humano queda blindado contra irregularidades en la señalización telefónica (SIP).
- **Desvinculación Legacy**: Se corrige y neutraliza la exposición de reportes legacy confusos cuando el clúster es parametrizado explícitamente para trabajar con el motor `OML_DIALER_ENGINE=omnidialer`.

---

## 5. Impacto y Consideraciones para Despliegue

### Para el Equipo de DevOps e Infraestructura
- **Migraciones Prioritarias**: Es imperativo ejecutar las migraciones de Django (`configuracion_telefonia_app`, `ominicontacto_app` y `reportes_app`). La ausencia de las mismas impedirá que el sistema levante dado el acoplamiento crítico a los nuevos modelos de reporting `interactions_summary` y `AgentActivityEventV2`.
- **Topología de Redis Extendida**: La dependencia hacia Redis es ahora la espina dorsal del sistema. Asegurar que las políticas de persistencia, sizing de memoria RAM, y bases lógicas (DB 0, 2 y 4 para Channels) estén provisionadas correctamente. 
- **Despliegue de Tareas en Background**: Se debe proveer supervisión y auto-restart de los demonios críticos que sustituyen al CRON (`supervision_events_listener`, `presence_heartbeat_scheduler`, `actualizar_reporte_dia_actual_agentes_scheduler`).
- **Nuevas Variables de Entorno y Secretos**:
  - Topología Telefónica: `NODE_ID` (vital para el consumo del ACD), `OML_DIALER_ENGINE`, `OMNIDIALER_HOST`.
  - Integración asíncrona: Parametrizar la red de procesamiento hacia Gearman (`GEARMAN_HOST`, `GEARMAN_JOB_SERVERS`, `GEARMAN_QUEUE_CALL`).
  - Storage Modernizado: Todo el ecosistema de grabaciones responde ahora a la jerarquía unificada y estructurada `BUCKET_*` (`BUCKET_NAME`, `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY`, `BUCKET_ENDPOINT`, `BUCKET_ENDPOINT_INTERNAL`, `BUCKET_DEFAULT_REGION`).
  - Configuración de Tiempos de Presencia: Configurar ajustadamente `PRESENCE_HEARTBEAT_INTERVAL_SEC`, `PRESENCE_HEARTBEAT_TIMEOUT_SEC`, y `PRESENCE_LOG_RECONNECT_COOLDOWN_MS` según la capacidad de la red local o remota de la empresa instaladora.
- **Variables de Entorno Deprecadas (Ya NO son necesarias)**:
  - **`AWS_ACCESS_KEY_ID`** y **`AWS_SECRET_ACCESS_KEY`**: Deprecadas a favor de `BUCKET_ACCESS_KEY_ID` y `BUCKET_SECRET_ACCESS_KEY`.
  - **`S3_BUCKET_NAME`**: Deprecada a favor de `BUCKET_NAME`.
  - **`S3_ENDPOINT`** y **`S3_ENDPOINT_MINIO`**: Absorbidas por el nuevo paradigma de doble vía `BUCKET_ENDPOINT` y `BUCKET_ENDPOINT_INTERNAL`.
  - **`S3_STORAGE_ENABLED`**: Eliminada. El motor decide la fuente del archivo por defecto sin requerir banderas globales pre-acondicionadas.

### Para el Equipo de QA / Control de Calidad
- **Stress-Test del Corazón Operativo**: Ejecutar simulaciones rigurosas sobre el comportamiento de red del agente. Probar cierres de pestaña del navegador agresivos (Ctrl+W) y caídas de conectividad de internet simuladas para asegurar que el `presence_heartbeat_scheduler` dispare el cierre sintético en V2 correctamente tras los umbrales de tiempo límite.
- **Escenarios Complejos de Telefonía (El Nuevo ACD)**: Comprobar el ecosistema de transferencias. Probar transferencias de agente a agente, transferencias a cola de espera externa y la nueva transferencia consultiva; confirmar que cada acción fluya sin demora a través del bus de `Redis Pub/Sub` hacia la PBX.
- **Conectividad a Storage Externo**: Analizar el ciclo completo de recuperación de grabaciones desde el *bucket* interno y público, asegurando que las URLs firmadas de Django apunten y descarguen sin bloqueos CORS. 
- **Pruebas de VoiceBots de Larga Duración**: Parametrizar una campaña asignando flujos de agentes y perfiles de VoiceBots. Confirmar que el journey unificado en `InteractionsSummary` recoja la secuencia lógica entre la IA inicial y la transferencia subsiguiente al humano de atención final.
- **Rendimiento de la Nube Analítica**: Emular la ejecución en caliente de las descargas y exportaciones en CSV masivas (más de un millón de registros) para atestiguar que el progreso mediante WebSocket notifica al cliente sanamente, sin congelar o reiniciar los workers de uWSGI/Daphne.
