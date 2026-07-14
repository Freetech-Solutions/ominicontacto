# Diseño — Canalidad de Email para Agente (espejo de WhatsApp)

> Estado: **PROPUESTA** (no implementado). Branch: `oml-3173-dev-emails`.
> Objetivo: que el agente pueda **asignarse** correos del inbox general de la
> campaña a su inbox personal, **escribir/responder**, **adjuntar archivos**, y
> **gestionar la canalidad**: calificar, guardar contacto en BD, y transferir a
> otro agente — replicando la arquitectura ya activa de WhatsApp/Facebook.

---

## ACTUALIZACIÓN — máquina de estados (Fase 3 implementada)

A pedido, la gestión NO usa transferencia (queda **diferida**, sin botón). En su
lugar la conversación lleva un `status` con esta máquina de estados:

| Evento | `status` |
|---|---|
| Llega email nuevo | `new` (Nuevo / En cola) |
| El sistema/agente lo toma | `assigned` (Asignado) |
| El agente lo abre | `in_progress` (En gestión) |
| Responde y **desasigna** | `answered` (Respondido / Pendiente cliente) → vuelve al inbox general |
| Cliente vuelve a escribir | `reopened` (Reabierto / En cola) |
| Finaliza con calificación | `closed` (Cerrado con calificación) |

**Reply con 3 modos** (`mode`): `unassign` (responde → `answered`, `agent=None`,
inbox general) · `keep` (responde → `in_progress`, sigue en inbox personal) ·
`dispose` (responde → `in_progress`; el front encadena la calificación que cierra).

**Inbox (tabs):** `assigned` (Asignado: `agent=yo`, no cerrado) · `general`
con subtabs `new` (`new`+`reopened`) y `waiting_client` (`answered`).
La respuesta de `GET conversations` es `{assigned, general:{new, waiting_client}}`.

**Transfer: diferido** — no se implementaron endpoints de transferencia ni botón.

### Performance / estabilidad (Fase 4)

Para soportar **miles de correos en cola** sin colgar la consola (mismo criterio
que WhatsApp resolvió sus N+1):

- **Referencias primero, thread al click.** `GET conversations` devuelve solo
  referencias livianas (asunto, remitente, contadores), **sin cuerpos**. El
  thread completo se trae recién al abrir (`GET conversations/{id}`).
- **Sin N+1 en el inbox.** Los contadores de mensajes/no-leídos se calculan con
  *subqueries correlacionadas* anotadas (`messages_count`/`unread_count`), no con
  un `COUNT` por fila. El costo es constante sin importar cuántas conversaciones
  haya en cola (hay un test que lo garantiza: `test_inbox_list_is_n_plus_1_free`).
- `only(...)` limita las columnas traídas a las referencias.

### Frontend (Fase 4 — entregado)

- **Consola legacy**: ícono gateado por `{% if tiene_email %}` + verde según
  permiso (`setEmailStatusIcon`), `#wrapperEmail` con `<iframe>` a
  `agent_email_index.html`, y `email_modals.js` (toggle del wrapper; **sin**
  transferencia).
- **App Vue de agente** (`omnileads_ui`): página `agent_email_index` (registrada
  en `vue.config.js`), ruta `/agent_email_index.html`, capa de datos
  (`api_urls/agent/email`, `services/agent/email/conversation_service.js`,
  `web_sockets/email_consumer.js`) y una vista SPA (`views/agent/email/Index.vue`)
  con tabs **Asignado / Nuevo·Reabierto / Esperando al cliente**, thread al click,
  y los 3 botones de respuesta (Desasignar / Seguir gestionando / Calificar).
- **Pendiente de UI**: formularios de calificación y de contacto embebidos (los
  endpoints `disposition`/`disposition_options`/`contact`/`contact_fields` ya
  existen; falta cablear los modales en `Index.vue`).

---

## 0. Cómo funciona hoy la referencia (WhatsApp) — validado

End-to-end, WhatsApp tiene 6 capas que **email_app no tiene**:

1. **Modelo de conversación** (`ConversacionWhatsapp`) que agrupa mensajes y lleva:
   `agent` (asignación), `campana`, `client`→`Contacto`, `atendida`, `is_disposition`,
   `conversation_disposition`→`HistoricalCalificacionCliente`. + `MensajeWhatsapp`
   (por mensaje: `content`, `type`, `status`, `file`, `sender`).
2. **Asignación**: inbound crea conversación con `agent=NULL`; endpoint
   `attend_chat` la asigna al agente (`otorgar_conversacion`).
3. **Transfer**: `transfer/to_agent` y `transfer/to_campaign` + un `MensajeWhatsapp`
   `type='transfer_event'`.
4. **Disposition**: `disposition_chat/` crea/actualiza `CalificacionCliente`
   (con `canalidad`) y cierra la conversación.
5. **Contacto**: `create_contact_from_conversation` crea `Contacto` en
   `campana.bd_contacto` y lo linkea.
6. **Realtime**: consumer Channels `AgentConsoleWhatsapp` (grupos
   `agent-console-whatsapp[-{user_id}]`) + `AgentNotifier` (eventos
   `whatsapp_new_chat`, `new_message`, `chat_attended`, `chat_transfered`).
   El frontend Vue (multipage, `agent_whatsapp_*`) se embebe como `<iframe>` en
   `base_agente.html` y habla con la consola legacy por `CustomEvent`
   (`onWhatsapp*Event`) — ver `whatsapp_modals.js`.

email_app hoy: solo `Account`/`Message`/`CampaignAccount`, sync IMAP entrante,
y UI **solo de supervisor** (gestión de cuentas + ver mensajes). **Sin** agente,
hilo, asignación, envío SMTP (el adapter no tiene `send()`), ni realtime.

---

## 1. Equivalencias de dominio WhatsApp → Email

| Concepto WhatsApp | Equivalente Email | Nota |
|---|---|---|
| `Linea` (proveedor) | `Account` (cuenta IMAP/SMTP) | ya existe |
| `ConfiguracionWhatsappCampana` | `CampaignAccount` | ya existe (OneToOne campaña→cuenta) |
| `ConversacionWhatsapp` | **`ConversacionEmail`** (NUEVO) | hilo de correo |
| `MensajeWhatsapp` | `Message` (EXTENDER) | ya existe; falta `conversation`, dirección, estado |
| `destination` (teléfono) | dirección de correo del cliente | |
| `expire` (ventana 24h) | **no aplica** | el email no expira; usar `service_level` solo para UI/SLA |
| `attend_chat` | `attend` | asignar al agente |
| `send_message_text/attachment` | `reply` (multipart) | enviar por SMTP |
| `transfer_event` message | mismo patrón | mensaje de sistema en el hilo |
| `CANALIDAD_WHATSAPP` | **`CANALIDAD_EMAIL`** (NUEVO) | en `CalificacionCliente` |

**Hilado (threading):** el email ya trae lo necesario — `Message` guarda
`message_id`, `in_reply_to`, `references`. La conversación se agrupa por la raíz
del hilo (`references[0]` o `in_reply_to`, fallback `message_id`), acotado por
`account` + dirección del cliente. Esto reemplaza el `whatsapp_id`.

---

## 2. Cambios de modelo (con migraciones)

### 2.1 NUEVO — `ConversacionEmail` (`email_app/models/conversation.py`)

```
account            FK Account (PROTECT)
campana            FK ominicontacto_app.Campana (PROTECT, null)   # vía CampaignAccount
thread_key         CharField(254, db_index)   # raíz de hilo normalizada
subject            CharField(254)
client_mail        CharField(254)             # from del cliente
client_name        CharField(100, blank)
contacto           FK Contacto (SET_NULL, null)        # análogo a client
agent              FK AgenteProfile (SET_NULL, null)   # asignación (NULL = inbox general)
atendida           BooleanField(default=False)
is_active          BooleanField(default=True)
is_disposition     BooleanField(default=False)
conversation_disposition  FK HistoricalCalificacionCliente (SET_NULL, null)
timestamp          DateTimeField(default=now, db_index)
date_last_interaction     DateTimeField(null)
  método: otorgar_conversacion(agent, attended=True)   # idéntico a WhatsApp
```

Estados (igual que WhatsApp):
- **Inbox general / "Nuevos"**: `agent=NULL, is_disposition=False`
- **Inbox personal / "Contestados"**: `agent=<yo>, atendida=True`
- **Cerrada**: `is_disposition=True`

### 2.2 EXTENDER — `Message` (`email_app/models/message.py`)

```
conversation   FK ConversacionEmail (CASCADE, null, related_name="mensajes")
direction      CharField(choices=[("inbound","inbound"),("outbound","outbound")], default="inbound")
is_read        BooleanField(default=False)
status         CharField(20, default="received")  # received|sending|sent|failed
fail_reason    CharField(254, blank, default="")
sender         JSONField(default=dict)   # outbound: {name, agent_id}; system: transfer_event
type           CharField(20, default="email")  # email | transfer_event
```

Los campos parseados actuales (`from_mail`, `subject`, `body_html`, etc.) quedan.
Outbound: se crea un `Message` con `direction="outbound"`, `content_bytes` = MIME
enviado, parseado igual.

### 2.3 `CalificacionCliente` (ominicontacto_app)

Agregar constante `CANALIDAD_EMAIL` (junto a `CANALIDAD_WHATSAPP`) + migración.

> **Regla ABM/tests:** cada modelo nuevo y endpoint create/edit/delete lleva tests
> (crear/editar/eliminar + casos de error). **Regla i18n:** todo string `_()`
> nuevo de email_app va con su `.po` (es/en/pt_BR) en la rama.

---

## 3. Backend — servicios y endpoints

### 3.1 Inbound: agrupar en conversación + notificar (sync service)

En `service/consumer/account.py::fetch()`, después de `message.hydrate()`:
1. Resolver `campana` vía `account.campaign_accounts` → `CampaignAccount`.
2. `ConversacionEmail` find-or-create por `thread_key` (raíz de hilo) + account +
   client_mail; linkear el `Message` (`conversation`, `direction="inbound"`).
3. Si la conversación es nueva o estaba sin agente → emitir evento realtime a los
   agentes de la campaña (igual que `notify_whatsapp_new_chat`).

### 3.2 Adapter SMTP — implementar `send()` (FALTA hoy)

`adapter/smtplib.py` hoy solo tiene `client/login/verify`. Agregar:

```python
def send(client, config, *, to, subject, body_text, body_html,
         in_reply_to=None, references=None, attachments=()):
    msg = EmailMessage()
    msg["From"] = config["from_addr"]; msg["To"] = to; msg["Subject"] = subject
    if in_reply_to: msg["In-Reply-To"] = in_reply_to
    if references:  msg["References"] = " ".join(references)
    msg.set_content(body_text); msg.add_alternative(body_html, subtype="html")
    for att in attachments: msg.add_attachment(att.read(), maintype=..., subtype=..., filename=att.name)
    client.send_message(msg)
    return msg["Message-ID"], bytes(msg)   # para persistir el Message outbound
```

### 3.3 Endpoints de AGENTE (`email_app/api/v1/`) — nuevos, espejo de WhatsApp

| Método | Endpoint | Acción |
|---|---|---|
| GET  | `/api/v1/email/conversations` | inbox del agente: `{nuevos[], asignados[]}` (filtra por campañas del agente) |
| GET  | `/api/v1/email/conversations/{id}` | hilo completo + mensajes |
| POST | `/api/v1/email/conversations/{id}/attend` | asignarme la conversación (inbox general→personal) |
| POST | `/api/v1/email/conversations/{id}/reply` | responder (multipart: cuerpo + adjuntos) → SMTP + Message outbound |
| POST | `/api/v1/email/conversations/{id}/mark_as_read` | marcar leído |
| POST | `/api/v1/email/transfer/to_agent` | transferir a otro agente (+ transfer_event) |
| GET  | `/api/v1/email/transfer/{campaign_pk}/agents` | agentes elegibles |
| POST | `/api/v1/email/disposition` | calificar (CalificacionCliente, `CANALIDAD_EMAIL`) + cerrar |
| GET  | `/api/v1/email/disposition/options/{campaign_id}` | opciones de calificación |
| POST | `/api/v1/email/contact/{campaign_pk}/create_from_conversation/{conv_pk}` | crear `Contacto` y linkear |
| GET  | `/api/v1/email/contact/{campaign_pk}/db_fields` | esquema de campos de la BD |

Permisos: nuevo `AgentPermission` que valida `email_habilitado` (Grupo/User, ya
existen) + pertenencia a la campaña. Las rutas de supervisor (`accounts`,
`messages`) quedan como están.

### 3.4 Realtime (notification_app)

- Nuevo consumer `AgentConsoleEmail` (`channels/agent-console-email`, grupos
  `agent-console-email[-{user_id}]`) — copia de `AgentConsoleWhatsapp`.
- `AgentNotifier`: métodos `notify_email_new_conversation`, `notify_email_new_message`,
  `notify_email_conversation_attended`, `notify_email_transfered`.
- Emisión desde el sync (inbound) y desde `reply`/`transfer`/`disposition`.

---

## 4. Frontend Vue de agente (`omnileads_ui/`)

Espejo 1:1 de la estructura WhatsApp:

| WhatsApp | Email (nuevo) |
|---|---|
| `router/agent/whatsapp/` | `router/agent/email/` |
| `views/agent/whatsapp/` | `views/agent/email/` (Index/inbox con tabs **Nuevos/Contestados**, conversation/detail con hilo, compose/reply, file uploader, transfer, disposition, contact) |
| `components/agent/whatsapp/` | `components/agent/email/` |
| `store/agent/whatsapp/` | `store/agent/email/` |
| `services/agent/whatsapp/` | `services/agent/email/` |
| `api_urls/agent/whatsapp/` | `api_urls/agent/email/` |
| `web_sockets/whatsapp_consumer.js` | `web_sockets/email_consumer.js` |
| `globals/agent/whatsapp/index.js` | `globals/agent/email/index.js` |
| `vue.config.js` páginas `agent_whatsapp_*` | agregar páginas `agent_email_*` |

Diferencia de UX vs WhatsApp: el compose de email tiene **asunto**, cuerpo
**HTML enriquecido**, y el hilo se muestra como cadena de mensajes (no chat 1:1).

---

## 5. Consola legacy (`ominicontacto_app`)

1. **Ícono** en `templates/agente/base_agente.html`: envolver `#emailMessages`
   en `{% if tiene_email %}` (hoy se renderiza siempre) — `tiene_email` ya llega
   del backend (`views/base.py:291`).
2. **Wrapper + iframe**: agregar `<div id="wrapperEmail">` con
   `<iframe src="{% static 'omnileads-frontend/agent_email_index.html' %}">`
   (hoy no existe — por eso clickear no abre nada).
3. **`JS/agente/email_modals.js`** (nuevo, copia de `whatsapp_modals.js`):
   `setEmailStatusIcon()` (verde `#52C159` / gris `#6A716A`), handler de click que
   togglea `#wrapperEmail`, y listeners `onEmail*Event` (transfer/disposition/
   contact/attach) — incluir el `<script>` y la llamada de init junto a las de
   whatsapp/facebook (líneas ~1166-1169).
4. **`templates/agente/modals/email/`**: modales espejo (transfer, disposition,
   contact, uploader).

---

## 6. Fases de implementación propuestas

- **Fase 1 — Recibir + asignar + ver** (núcleo): modelos `ConversacionEmail` +
  extensión `Message` + migraciones; agrupado de hilo en el sync; realtime
  (consumer + notifier); endpoints `conversations` (list/detail/attend/mark_as_read).
- **Fase 2 — Responder**: `send()` en SMTP adapter; endpoint `reply` + adjuntos;
  Message outbound; threading headers.
- **Fase 3 — Gestionar**: `disposition` (+`CANALIDAD_EMAIL`), `contact`, `transfer`.
- **Fase 4 — UI**: app Vue de agente (todas las páginas) + cableado consola legacy
  (ícono, wrapper, `email_modals.js`, modales).

Cada fase: tests ABM + `.po` es/en/pt_BR de los strings nuevos.

---

## 7. Decisiones que requieren tu confirmación

1. **Hilo (`ConversacionEmail`) vs. plano**: ¿modelamos conversación/hilo
   (recomendado, habilita asignar/cerrar/transferir como WhatsApp) o preferís
   asignar a nivel de `Message` individual? (El hilo es el que permite "atender"
   de verdad.)
2. **¿Reusar `CalificacionCliente`** con `CANALIDAD_EMAIL` (consistente con
   WhatsApp) o un modelo de disposición propio de email?
3. **Sent/IMAP**: al responder, ¿además de enviar por SMTP querés **appendear** la
   copia a la carpeta "Sent" vía IMAP, o alcanza con persistir el `Message`
   outbound en la BD de OMniLeads?
4. **Outbound nuevo (no-reply)**: ¿el agente podrá iniciar un correo nuevo a un
   contacto (como `send_initing_conversation` de WhatsApp), o solo responder
   correos entrantes en esta primera versión?
5. **Orden de fases**: ¿arranco por Fase 1 (modelo+recibir+asignar) o preferís que
   primero deje el **ícono/wrapper cableado** (Fase 4 parcial) aunque el panel esté
   vacío, para validar el embed?
