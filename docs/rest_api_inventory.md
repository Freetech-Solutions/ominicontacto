# OMniLeads RESTful API - inventario y saneamiento de autenticacion

Este documento releva las APIs REST expuestas por el proyecto Django y propone la frontera de endpoints que deberian conservar autenticacion por token expirable (`Authorization: Bearer <token>`).

Fuente del formato: pagina publica "OMniLeads RESTful API (Pro)" de GitBook. El relevamiento de endpoints se hizo por analisis estatico de `api_app/urls.py`, routers DRF de WhatsApp/Facebook/Instagram y webhooks del orquestador. En este entorno no fue posible arrancar Django porque no esta instalado el paquete `django`.

## Criterio de autenticacion

Las formas de autenticacion para la API publica de clientes son:

| Metodo | Uso esperado |
| --- | --- |
| Sesion | Usuario logueado en la interfaz web. |
| Token expirable | Integraciones externas que obtienen token con `POST /api/v1/login` y envian `Authorization: Bearer <token>`. |

La autenticacion por `ExpiringTokenAuthentication` deberia quedar habilitada solo en endpoints documentados para clientes/integraciones externas. El resto de las APIs administrativas, de UI interna o de canalidad deberian usar sesion u otro mecanismo interno.

Resumen del inventario estatico:

| Clasificacion | Cantidad |
| --- | ---: |
| Publica para clientes | 26 |
| Interna admin/UI | 135 |
| Interna de canalidad WhatsApp/Facebook/Instagram | 150 |
| Webhooks publicos sin token de cliente | 4 |
| Ruta no REST/UI legacy | 1 |

Exposicion actual de `ExpiringTokenAuthentication`:

| Situacion | Cantidad |
| --- | ---: |
| Declarada explicitamente en la view/viewset | 272 |
| Heredada desde `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']` | 39 |
| Sin autenticacion requerida | 1 |
| No resuelta por analisis estatico | 4 |

Antes de quitar `ExpiringTokenAuthentication` de la configuracion global, agregarlo explicitamente a estas APIs publicas que hoy lo heredan:

| View | Endpoint |
| --- | --- |
| `api_app.views.agente.OpcionesCalificacionViewSet` | `/api/v1/campaign/<campaign>/dispositionOptions/` |
| `api_app.views.agente.ApiCalificacionClienteView` | `/api/v1/disposition/` |
| `api_app.views.agente.ApiCalificacionClienteCreateView` | `/api/v1/new_contact/disposition/` |
| `api_app.views.agente.ObtenerCredencialesSIPAgenteView` | `/api/v1/sip/credentials/agent/` |

## Endpoints publicos para clientes

### Endpoint de Login

Este metodo permite autenticarse como usuario del sistema para obtener un token de seguridad. El token debe enviarse en las siguientes peticiones como header:

| field | type | description |
| --- | --- | --- |
| Authorization | Bearer | `Bearer <token obtenido>` |

URL: `POST /<omnileads_addr>/api/v1/login`

#### Parametros

| field name | type | description |
| --- | --- | --- |
| username | string | Username del usuario generado en OML. |
| password | string | Password del usuario generado en OML. |

#### Response 200 OK

| field | type | description |
| --- | --- | --- |
| user | object | Datos del usuario autenticado. Si el usuario es agente incluye `agent_id`. |
| expires_in | duration | Tiempo restante de vida del token. |
| token | string | Token a enviar como `Authorization: Bearer <token>`. |

#### Error

Si las credenciales no son validas, la API responde con `detail: Invalid Credentials or activate account`.

### Endpoint obtener estructura de Base de Datos de Contactos

Permite obtener los campos de una base de datos de contactos de una campana. Con esta informacion se puede crear un contacto usando el endpoint de creacion de contacto.

URL: `POST /<omnileads_addr>/api/v1/campaign/database_metadata/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field name | type | description |
| --- | --- | --- |
| idExternalSystem | integer | Opcional. Si se envia, `idCampaign` se interpreta como identificador externo de la campana para ese sistema externo. |
| idCampaign | string | Identificador de la campana. Puede ser ID interno de OML o ID externo segun `idExternalSystem`. |

#### Response 200 OK

| field | type | description |
| --- | --- | --- |
| status | string | `OK` o `ERROR`. |
| fields | array | Lista de campos de la base de datos. |
| main_phone | string | Campo que representa el telefono principal. |
| external_id | string/null | Campo que representa el identificador externo del contacto. |

### Endpoint creacion de contacto

Permite agregar un contacto a una base de datos de contactos de una campana. Las credenciales deben pertenecer a un agente o supervisor asociado a la campana.

URL: `POST /<omnileads_addr>/api/v1/new_contact/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field name | type | description |
| --- | --- | --- |
| idExternalSystem | integer | Opcional. Si se envia, `idCampaign` se interpreta como identificador externo de la campana para ese sistema externo. |
| idCampaign | string | Identificador de la campana. |
| `<main_phone>` | string | Obligatorio. Nombre dinamico del campo telefonico devuelto por `database_metadata`. |
| `<external_id>` | string | Obligatorio si la base define identificador externo. Nombre dinamico devuelto por `database_metadata`. |
| `<optional_bd_field>` | string | Campos adicionales de la base de contactos. |

#### Response 200 OK

| field | type | description |
| --- | --- | --- |
| status | string | `OK`. |
| message | string | Mensaje de contacto agregado. |
| id | integer | ID interno del contacto en OML. |
| contacto | object | Datos del contacto creado. |

En caso de error responde `status: ERROR`, `message` y `errors`.

### Endpoint de Generacion de llamadas

Permite generar llamadas click-to-call desde un CRM externo. Soporta un numero unico o multiples numeros separados por guion bajo.

URL: `POST /<omnileads_addr>/api/v1/makeCall/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field name | type | description |
| --- | --- | --- |
| idExternalSystem | string | Opcional. Identifica el sistema externo. |
| idCampaign | string | Obligatorio. ID interno de campana o ID externo si se usa `idExternalSystem`. |
| idAgent | string | Obligatorio. ID interno de agente o ID externo si se usa `idExternalSystem`. |
| idContact | string | Opcional. ID interno de contacto o ID externo si se usa `idExternalSystem`. |
| phone | string | Obligatorio. Numero a marcar. Para multinum usar valores separados por `_`. |

#### Response

Si la llamada se dispara correctamente responde `{"status": "OK"}`. En caso de error responde `{"status": "ERROR", "message": "...", "errors": ...}`.

### Endpoint de llamada fuera de campana

Permite iniciar una llamada fuera del contexto de campana para agentes con permiso `call_off_camp`.

URL: `POST /<omnileads_addr>/api/v1/make_call_outside_campaign/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field name | type | description |
| --- | --- | --- |
| destination_type | string | Destino de la llamada. Valores soportados por el codigo: `AGENT` o `EXTERNAL`. |
| destination | string | ID de agente destino si `destination_type=AGENT`, o numero externo si `destination_type=EXTERNAL`. |

#### Response

Si la llamada se dispara correctamente responde `{"status": "OK", "message": "Llamada fuera de campaña iniciada"}`. Si el agente no tiene permiso o el destino es invalido responde `status: ERROR`.

### Endpoint para cortar llamada actual

Permite finalizar la llamada actual del agente autenticado.

URL: `POST /<omnileads_addr>/api/v1/hangupCall/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Response

Devuelve `{"status": "OK"}` si la llamada pudo finalizarse o `{"status": "ERROR"}` si fallo la operacion.

### Endpoint listado de opciones de calificacion

Permite obtener las opciones de calificacion disponibles para una campana.

URL: `GET /<omnileads_addr>/api/v1/campaign/<idc>/dispositionOptions/`

URL: `GET /<omnileads_addr>/api/v1/campaign/<idc>/dispositionOptions/<ids>/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros de URL

| field | type | description |
| --- | --- | --- |
| idc | integer/string | ID interno de campana en la primera variante; ID externo de campana en la segunda. |
| ids | integer | ID del sistema externo. |

#### Response 200 OK

Array de opciones de calificacion. Cada elemento incluye al menos `id`, `name` y `hidden`.

### Endpoint listado y gestion de calificaciones

Permite listar, crear y modificar calificaciones realizadas por un agente.

URL: `GET /<omnileads_addr>/api/v1/disposition/`

URL: `POST /<omnileads_addr>/api/v1/disposition/`

URL: `PUT /<omnileads_addr>/api/v1/disposition/<idDisposition>/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros para crear/modificar

| field name | type | description |
| --- | --- | --- |
| idExternalSystem | integer | Opcional. Si se envia, `idContact` se interpreta como identificador externo del contacto. |
| idContact | string | ID interno o externo del contacto a calificar. |
| idDispositionOption | integer | ID de la opcion de calificacion. No debe estar oculta. |
| callid | string | Opcional. ID de la llamada. |
| comments | string | Observaciones del agente. |

#### Response

En listado devuelve las calificaciones del agente. En creacion/modificacion devuelve los datos de la calificacion o un JSON de errores por contacto/opcion inexistente, opcion oculta o duplicidad.

### Endpoint crear nuevo contacto y asignarle calificacion

Permite crear un contacto y asociarle una calificacion en la misma operacion.

URL: `POST /<omnileads_addr>/api/v1/new_contact/disposition/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field name | type | description |
| --- | --- | --- |
| phone | string | Numero telefonico del contacto. |
| idExternalContact | string | Opcional. ID del contacto en un CRM externo. |
| idDispositionOption | integer | ID de la opcion de calificacion. |
| comments | string | Observaciones del agente. |
| callid | string | Opcional. ID de la llamada. |
| `<optional_bd_field>` | string | Campos adicionales de la base de contactos. |

### Endpoint para consultar estado de agentes y llamadas

Estos endpoints permiten consultar en tiempo real estados de agentes y llamadas de una campana.

URL: `GET /<omnileads_addr>/api/v1/agent_status/campaign/<campaign_id>`

URL: `GET /<omnileads_addr>/api/v1/call_status/campaign/<campaign_id>`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field | type | description |
| --- | --- | --- |
| campaign_id | number | ID unico de campana. |
| date_start | date | Opcional para `call_status`. Formato `%Y-%m-%d`. |
| date_end | date | Opcional para `call_status`. Formato `%Y-%m-%d`. |

#### Response `agent_status`

| field | type | description |
| --- | --- | --- |
| ready | number | Cantidad de agentes disponibles. |
| oncall | number | Cantidad de agentes en llamada. |
| pause | number | Cantidad de agentes en pausa. |

Ejemplo:

```json
{"ready": 2, "oncall": 0, "pause": 2}
```

#### Response `call_status`

| field | type | description |
| --- | --- | --- |
| attended | number | Cantidad de llamadas atendidas. |
| abandoned | number | Cantidad de llamadas abandonadas. |
| expired | number | Cantidad de llamadas expiradas/no contactadas. |

Ejemplo:

```json
{"attended": 2, "abandoned": 0, "expired": 2}
```

### Endpoint para consultar estado de agentes en modo lista

Permite consultar en tiempo real el estado individual de los agentes de una campana.

URL: `GET /<omnileads_addr>/api/v1/agent_status_list/campaign/<campaign_id>`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field | type | description |
| --- | --- | --- |
| campaign_id | number | ID unico de campana. |

#### Response 200 OK

Array de objetos:

| field | type | description |
| --- | --- | --- |
| name | string | Nombre del agente. |
| status | string | Estado del agente: `READY`, `ONCALL`, `PAUSE`, `OFFLINE`, etc. |

Ejemplo:

```json
[{"name": "Kirk Mccall", "status": "OFFLINE"}, {"name": "Kimberly Leonard", "status": "PAUSE"}]
```

### Endpoint para consulta de campanas de agente

Permite consultar campanas visibles para el usuario autenticado. Si el usuario es administrador devuelve todas; si es supervisor devuelve las asignadas. Puede filtrarse por agente, tipo, nombre o estado.

URL: `GET /<omnileads_addr>/api/v1/supervision/campaigns/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Query params

| field | type | description |
| --- | --- | --- |
| agent | integer | Opcional. ID de agente para filtrar campanas asociadas. |
| type | integer/list | Opcional. Tipo de campana o lista JSON de tipos. |
| name | string | Opcional. Filtro por nombre. |
| status | integer/list | Opcional. Estado o lista JSON de estados. |

### Endpoint para reasignar campanas a agente

Permite modificar las campanas asignadas a un agente. Si el usuario es supervisor, solo trabaja sobre campanas asignadas a ese supervisor.

URL: `POST /<omnileads_addr>/api/v1/agent/campaigns_update/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field | type | description |
| --- | --- | --- |
| agent_id | integer | ID del agente. |
| campaigns | array | Lista de IDs de campana que deben quedar asignadas. |

Ejemplo:

```json
{"agent_id": 3, "campaigns": [12, 17, 19]}
```

### Endpoint para pausar/despausar/desloguear agente

Permite que un supervisor ejecute una accion sobre un agente.

URL: `POST /<omnileads_addr>/api/v1/supervision/action_on_agent/<agent_id>/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Parametros

| field | type | description |
| --- | --- | --- |
| accion | string | Accion a ejecutar. Valores esperados por el servicio: `AGENTLOGOUT`, `AGENTPAUSE`, `AGENTUNPAUSE`. |

Nota de compatibilidad: la documentacion publica previa menciona el parametro `action`, pero la implementacion actual en `InteraccionDeSupervisorSobreAgenteView` lee `accion`.

### API de sesion de Agente en Asterisk

Endpoints usados por el WebPhone para controlar la sesion del agente en Asterisk.

#### Inicio de sesion de agente en Asterisk

Establece la sesion del agente en Asterisk como iniciada.

URL: `POST /<omnileads_addr>/api/v1/asterisk_login/`

No requiere parametros adicionales.

#### Cierre de sesion de agente en Asterisk

Establece la sesion del agente en Asterisk como finalizada.

URL: `POST /<omnileads_addr>/api/v1/asterisk_logout/`

No requiere parametros adicionales.

#### Ingreso en pausa de agente

Establece la sesion del agente en Asterisk como pausada.

URL: `POST /<omnileads_addr>/api/v1/asterisk_pause/`

| field name | type | description |
| --- | --- | --- |
| pause_id | string | ID de la pausa en la que entra el agente. |

#### Salida de pausa de agente

Establece la sesion del agente en Asterisk como disponible.

URL: `POST /<omnileads_addr>/api/v1/asterisk_unpause/`

| field name | type | description |
| --- | --- | --- |
| pause_id | string | ID de la pausa de la que sale el agente. |

### Endpoint para obtener credenciales SIP de agente

Provee credenciales SIP temporales para autenticar al agente en el servidor SIP mediante WebPhone.

URL: `GET /<omnileads_addr>/api/v1/sip/credentials/agent/`

#### Headers

| field | type | description |
| --- | --- | --- |
| Authorization required | Bearer | `Bearer <token>` |

#### Response 200 OK

| field | type | description |
| --- | --- | --- |
| status | string | `OK` o `ERROR`. |
| sip_user | string | Usuario SIP generado. |
| sip_password | string | Password SIP generado. |

## Endpoints candidatos a mantener fuera de la API publica

Estos endpoints aparecen con `ExpiringTokenAuthentication` explicita o heredada, pero por su naturaleza parecen internos de administracion/UI o de canalidad. Requieren validacion de producto antes de remover token.

### `api_app` administrativo/UI

| Familia | Endpoints |
| --- | --- |
| Permisos y roles | `/api/v1/permissions/new_role/`, `/delete_role/`, `/update_role_permissions/` |
| Bases de contacto administrativas | `/api/v1/crear_base_contactos/`, `/api/v1/contact_database/create/`, `/api/v1/contact_database/<db_pk>/contact/`, `/api/v1/contact_database/<pk>/campaings/` |
| Supervision UI | `/api/v1/supervision/agents/`, `/agents_users/`, `/status_campanas/*`, `/reasignar_agenda_contacto/`, `/data_agenda_contacto/<agenda_id>/`, exportaciones CSV, dashboard y audit supervisor |
| Campanas/agentes | `/api/v1/campaign/<pk_campana>/agents/`, `/api/v1/campaign/agents_update/`, `/api/v1/active_agents/` |
| Pausas | `/api/v1/pause_sets/*`, `/api/v1/pause_config/*`, `/api/v1/pauses/*` |
| Sitios externos | `/api/v1/external_sites/*`, `/api/v1/external_site_authentications/*` |
| Calificaciones admin | `/api/v1/call_dispositions/*` |
| Sistemas externos | `/api/v1/external_systems/*`, `/api/v1/agents_external_system/` |
| Formularios | `/api/v1/forms/*` |
| Telefonia | `/api/v1/inbound_routes/*`, `/api/v1/outbound_routes/*`, `/api/v1/group_of_hours/*`, `/api/v1/ivrs/*`, `/api/v1/inbound_destinations*` |
| Sistema/dialer | `/api/v1/register_server/*`, `/api/v1/wombat_dialer/*`, `/api/v1/asterisk/queues_data/`, `/api/v1/asterisk/notify_attended_multinum_call/` |
| Agente UI | `/api/v1/campaign/<pk_campana>/contacts/`, `/api/v1/asterisk_ringing/`, `/api/v1/asterisk_reject_call/`, `/api/v1/asterisk_disabled/`, `/api/v1/notify_end_transferred_call/`, `/api/v1/audit/set_revision_status/`, `/api/v1/calificar_llamada/`, `/api/v1/evento_hold/`, `/api/v1/agent/consultative_confer_hold`, `/api/v1/agent/transfer_options` |
| Archivos y reportes | `/api/v1/auditoria/archivo`, `/api/v1/grabacion/*`, `/api/v1/call_record/<callid>/`, `/api/v1/audio/list/`, `/api/v1/group/list/`, `/api/v1/agent/list/`, `/api/v1/reportes/survey_transfer/`, `/api/v1/languages/list` |
| Legacy supervision | `/api_supervision/llamadas_campana/<pk_campana>/`, `/api_supervision/calificaciones_campana/<pk_campana>/` |

### APIs internas de canalidad

| Canal | Base path | Familias |
| --- | --- | --- |
| WhatsApp | `/api/v1/whatsapp/` | `provider`, `line`, `destination`, `templates_message`, `templates_whatsapp`, `campaing`, `group_plantilla_whatsapp`, `configuration_whatsapp`, `chat`, `transfer`, `contact/<campana_pk>`, `disposition_chat`, `templates/<campana_pk>`, `reports/` |
| Facebook | `/api/v1/facebook/` | `page`, `destination`, `campaigns`, `chat`, `contact/<campana_pk>`, `disposition_chat`, `transfer`, `templates_messenger`, `group_template_messenger`, `templates/<campana_pk>`, `reports/`, `chat/<campaing_id>/filter_chats` |
| Instagram | `/api/v1/instagram/` | `account`, `campaigns`, `schedules`, `chat`, `contact/<campana_pk>`, `disposition_chat`, `transfer`, `templates/<campana_pk>`, `templates_instagram`, `reports/`, `chat/<campaing_id>/filter_chats`, `chat/<pk>/report_detail` |

### Webhooks publicos

Estos endpoints son publicos por diseno pero no deberian depender de `ExpiringTokenAuthentication`; validan el origen mediante el flujo propio del proveedor o datos de la ruta.

| Metodo | URL |
| --- | --- |
| GET/POST | `/webhookmeta/<app_id>/` |
| GET/POST | `/webhook/<identificador>/` |
| GET/POST | `/webhook/facebook_messenger/<app_id>/` |
| GET/POST | `/webhook/instagram/<app_id>/` |

## Plan sugerido para saneamiento

1. Confirmar la lista de endpoints publicos de clientes de este documento.
2. Agregar `authentication_classes = (SessionAuthentication, ExpiringTokenAuthentication,)` explicitamente a las cuatro views publicas que hoy heredan token desde settings.
3. Cambiar `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']` para quitar `api_app.authentication.ExpiringTokenAuthentication` del default global.
4. Remover `ExpiringTokenAuthentication` de APIs internas y dejarlas con `SessionAuthentication` cuando sean consumidas desde UI.
5. Actualizar tests que hoy usan `HTTP_AUTHORIZATION='Bearer ...'` contra APIs internas para que usen login de sesion o `force_authenticate`.
6. Mantener tests con Bearer token solo para los endpoints publicos documentados.

## Archivos fuente relevantes

| Archivo | Uso |
| --- | --- |
| `api_app/urls.py` | Rutas REST principales y router DRF. |
| `whatsapp_app/api/urls.py` | Router REST de WhatsApp. |
| `facebook_meta_app/api/urls.py` | Router REST de Facebook/Messenger. |
| `instagram_app/api/urls.py` | Router REST de Instagram. |
| `orquestador_app/urls.py` | Webhooks entrantes. |
| `ominicontacto/settings/defaults.py` | Configuracion global DRF que hoy habilita `ExpiringTokenAuthentication`. |
| `api_app/authentication.py` | Implementacion de token expirable y keyword `Bearer`. |
