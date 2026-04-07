# OMniLeads API Documentation

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Base Endpoints](#base-endpoints)
4. [Administrator Endpoints](#administrator-endpoints)
5. [Supervisor Endpoints](#supervisor-endpoints)
6. [Agent Endpoints](#agent-endpoints)
7. [Campaign Management](#campaign-management)
8. [Contact Database](#contact-database)
9. [Call Dispositions](#call-dispositions)
10. [Pause Sets](#pause-sets)
11. [Pauses](#pauses)
12. [External Sites](#external-sites)
13. [External Site Authentication](#external-site-authentication)
14. [External Systems](#external-systems)
15. [Forms](#forms)
16. [Inbound Routes](#inbound-routes)
17. [Outbound Routes](#outbound-routes)
18. [Group of Hours](#group-of-hours)
19. [IVRs](#ivrs)
20. [Register Server](#register-server)
21. [Recordings](#recordings)
22. [Audit](#audit)
23. [Audio Files](#audio-files)
24. [Users](#users)
25. [Wombat Dialer](#wombat-dialer)
26. [Asterisk](#asterisk)
27. [Inbound Destinations](#inbound-destinations)
28. [Logging](#logging)
29. [Reports](#reports)
30. [Agent and Interaction Reports](#agent-and-interaction-reports)
31. [Transfers](#transfers)

---

## Overview

The OMniLeads API provides a comprehensive REST API for managing all aspects of the contact center system. The API supports authentication via session or expiring tokens and uses Django REST Framework for serialization and permissions.

### Base URL

All API endpoints are prefixed with `/api/v1/`

### Features

- **Token-based Authentication**: Expiring tokens with configurable expiration time
- **Session Authentication**: Support for Django session-based authentication
- **Permission System**: Role-based access control using OML permissions
- **RESTful Design**: Standard HTTP methods (GET, POST, PUT, DELETE)
- **JSON Responses**: All responses are in JSON format

### Configuration

The API can be configured using environment variables:

- `NODE_ID`: ACD node identifier (default: `acd01`)
- `TOKEN_EXPIRED_AFTER_SECONDS`: Token expiration time in seconds

---

## Authentication

### Login

Obtain an authentication token by logging in with your credentials.

#### `POST /api/v1/login`

**Request Body:**
```json
{
  "username": "your_username",
  "password": "your_password"
}
```

**Response (200 OK):**
```json
{
  "user": {
    "id": 1,
    "username": "user",
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "agent_id": 5
  },
  "expires_in": "23:59:59",
  "token": "your_token_here"
}
```

**Error Responses:**
- `400 Bad Request`: Invalid request data
- `404 Not Found`: Invalid credentials or inactive account

### Using the Token

Include the token in the `Authorization` header using the `Bearer` format:

```
Authorization: Bearer <your_token>
```

**Important**: Use `Bearer <token>`, not `Token <token>`.

### Token Expiration

Tokens expire after a configurable time period. When a token expires, you must obtain a new one by logging in again.

---

## Base Endpoints

### Login

See [Authentication](#authentication) section above.

---

## Administrator Endpoints

### Active Agents by Group

#### `GET /api/v1/grupo/{pk_grupo}/agentes_activos/`

Returns a list of active agents in a specific group.

**Path Parameters:**
- `pk_grupo` (integer): Group ID

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "sip_extension": "1001",
    "user": {
      "id": 1,
      "username": "agent1"
    }
  }
]
```

### Create Role

#### `POST /api/v1/permissions/new_role/`

Creates a new role in the system.

**Request Body:**
```json
{
  "name": "Custom Role"
}
```

**Response (200 OK):**
```json
{
  "status": "OK",
  "role": {
    "id": 1,
    "name": "Custom Role",
    "permissions": []
  }
}
```

**Error Responses:**
- `400 Bad Request`: Missing or invalid `name` field
- `400 Bad Request`: Role with that name already exists

### Delete Role

#### `POST /api/v1/permissions/delete_role/`

Deletes a role from the system.

**Request Body:**
```json
{
  "role_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

**Error Responses:**
- `400 Bad Request`: Role ID is missing or invalid
- `400 Bad Request`: Cannot delete role assigned to users
- `404 Not Found`: Role does not exist

### Update Role Permissions

#### `POST /api/v1/permissions/update_role_permissions/`

Updates the permissions assigned to a role.

**Request Body:**
```json
{
  "role_id": 1,
  "permissions": [1, 2, 3, 4]
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

**Error Responses:**
- `400 Bad Request`: Missing or invalid fields
- `404 Not Found`: Role does not exist

### Upload Contact Database

#### `POST /api/v1/crear_base_contactos/`

Uploads a contact database file (CSV, XLS, XLSX).

**Request:** Multipart form data with file upload

**Response (200 OK):**
```json
{
  "status": "OK",
  "message": "Database created successfully",
  "database_id": 1
}
```

### Resend Registration Key

#### `POST /api/v1/reenviar_key_registro/`

Resends the registration key to a user.

**Request Body:**
```json
{
  "user_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK",
  "message": "Key sent successfully"
}
```

---

## Supervisor Endpoints

### Active Campaigns

#### `GET /api/v1/supervision/campaigns/`

Returns active campaigns for the supervisor. Administrators see all campaigns.

**Query Parameters:**
- `type` (string or JSON array): Filter by campaign type
- `name` (string): Filter by campaign name
- `agent` (integer): Filter by agent ID
- `status` (string or JSON array): Filter by campaign status

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Campaign Name",
    "type": "ENTRANTE",
    "estado": "ACTIVA"
  }
]
```

### Agent Status

#### `GET /api/v1/supervision/agents/`

Returns status information for all agents.

**Response (200 OK):**
```json
{
  "online": [
    {
      "id": 1,
      "status": "READY",
      "campaign": "Campaign Name"
    }
  ],
  "offline": [],
  "paused": []
}
```

### Agent Users

#### `GET /api/v1/supervision/agents_users/`

Returns user information for all agents.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "username": "agent1",
    "agent_id": 1,
    "email": "agent1@example.com"
  }
]
```

### Inbound Campaigns Status

#### `GET /api/v1/supervision/status_campanas/entrantes/`

Returns status information for inbound campaigns.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Inbound Campaign",
    "estado": "ACTIVA",
    "llamadas_en_cola": 5
  }
]
```

### Outbound Campaigns Status

#### `GET /api/v1/supervision/status_campanas/salientes/`

Returns status information for outbound campaigns.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Outbound Campaign",
    "estado": "ACTIVA",
    "agentes_activos": 3
  }
]
```

### Action on Agent

#### `POST /api/v1/supervision/action_on_agent/{pk}/`

Performs an action on an agent (pause, unpause, etc.).

**Path Parameters:**
- `pk` (integer): Agent ID

**Request Body:**
```json
{
  "action": "pause",
  "pause_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Send Message to Agents

#### `POST /api/v1/supervision/enviar_mensaje_agentes/`

Sends a message to one or more agents.

**Request Body:**
```json
{
  "agent_ids": [1, 2, 3],
  "message": "Your message here"
}
```

**Response (200 OK):**
```json
{
  "status": "OK",
  "sent_to": 3
}
```

### Campaign Calls

#### `GET /api_supervision/llamadas_campana/{pk_campana}/`

Returns call logs for a specific campaign.

**Path Parameters:**
- `pk_campana` (integer): Campaign ID

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "callid": "1234567890.123",
    "telefono": "1234567890",
    "fecha": "2024-01-01T10:00:00Z"
  }
]
```

### Campaign Dispositions

#### `GET /api_supervision/calificaciones_campana/{pk_campana}/`

Returns disposition records for a specific campaign.

**Path Parameters:**
- `pk_campana` (integer): Campaign ID

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "contacto": 1,
    "opcion_calificacion": 1,
    "fecha": "2024-01-01T10:00:00Z"
  }
]
```

### Reassign Contact Schedule

#### `POST /api/v1/supervision/reasignar_agenda_contacto/`

Reassigns a contact schedule to a different agent.

**Request Body:**
```json
{
  "agenda_id": 1,
  "new_agent_id": 2
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Contact Schedule Data

#### `GET /api/v1/supervision/data_agenda_contacto/{agenda_id}/`

Returns data for a specific contact schedule.

**Path Parameters:**
- `agenda_id` (integer): Schedule ID

**Response (200 OK):**
```json
{
  "id": 1,
  "contacto": {
    "id": 1,
    "telefono": "1234567890"
  },
  "agente": {
    "id": 1,
    "username": "agent1"
  },
  "fecha": "2024-01-01T10:00:00Z"
}
```

### Export Contacted CSV

#### `GET /api/v1/exportar_csv_contactados/`

Exports contacted contacts as CSV.

**Query Parameters:**
- `campaign_id` (integer): Campaign ID
- `fecha_desde` (date): Start date
- `fecha_hasta` (date): End date

**Response:** CSV file download

### Export Dispositioned CSV

#### `GET /api/v1/exportar_csv_calificados/`

Exports dispositioned contacts as CSV.

**Query Parameters:**
- `campaign_id` (integer): Campaign ID
- `fecha_desde` (date): Start date
- `fecha_hasta` (date): End date

**Response:** CSV file download

### Export Not Answered CSV

#### `GET /api/v1/exportar_csv_no_atendidos/`

Exports not answered contacts as CSV.

**Query Parameters:**
- `campaign_id` (integer): Campaign ID
- `fecha_desde` (date): Start date
- `fecha_hasta` (date): End date

**Response:** CSV file download

### Assigned Contacts Preview

#### `GET /api/v1/supervision/contactos_asignados_preview/{pk_campana}/`

Returns a preview of contacts assigned to a campaign.

**Path Parameters:**
- `pk_campana` (integer): Campaign ID

**Response (200 OK):**
```json
{
  "total": 100,
  "assigned": 50,
  "pending": 50
}
```

### Export Campaign Dispositions CSV

#### `GET /api/v1/exportar_csv_calificaciones_campana/`

Exports campaign dispositions as CSV.

**Query Parameters:**
- `campaign_id` (integer): Campaign ID
- `fecha_desde` (date): Start date
- `fecha_hasta` (date): End date

**Response:** CSV file download

### Export Form Management CSV

#### `GET /api/v1/exportar_csv_formulario_gestion_campana/`

Exports form management data as CSV.

**Query Parameters:**
- `campaign_id` (integer): Campaign ID
- `fecha_desde` (date): Start date
- `fecha_hasta` (date): End date

**Response:** CSV file download

### Export Contacted Base Results CSV

#### `GET /api/v1/exportar_csv_resultados_base_contactados/`

Exports contacted base results as CSV.

**Query Parameters:**
- `campaign_id` (integer): Campaign ID
- `fecha_desde` (date): Start date
- `fecha_hasta` (date): End date

**Response:** CSV file download

### Supervision Dashboard

#### `GET /api/v1/dashboard_supervision/`

Returns dashboard data for supervision.

**Response (200 OK):**
```json
{
  "active_campaigns": 5,
  "active_agents": 10,
  "calls_today": 150,
  "avg_wait_time": "00:02:30"
}
```

### Supervisor Audit

#### `GET /api/v1/audit_supervisor/`

Returns audit logs for supervisor actions.

**Query Parameters:**
- `fecha_desde` (date): Start date
- `fecha_hasta` (date): End date
- `user_id` (integer, optional): Filter by user ID

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "user": "supervisor1",
    "action": "UPDATE",
    "model": "Campana",
    "timestamp": "2024-01-01T10:00:00Z"
  }
]
```

---

## Agent Endpoints

### Get SIP Credentials

#### `GET /api/v1/sip/credentials/agent/`

Returns SIP credentials for the authenticated agent.

**Response (200 OK):**
```json
{
  "status": "OK",
  "sip_user": "1001",
  "sip_password": "password123"
}
```

### Disposition Options

#### `GET /api/v1/campaign/{campaign}/dispositionOptions/`

Returns disposition options for a campaign.

**Path Parameters:**
- `campaign` (string or integer): Campaign ID or external ID

**Query Parameters:**
- `externalSystem` (integer, optional): External system ID

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Interested",
    "tipo": "GESTION"
  }
]
```

### Get Dispositions

#### `GET /api/v1/disposition/`

Returns dispositions for the authenticated agent.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "contacto": 1,
    "opcion_calificacion": 1,
    "fecha": "2024-01-01T10:00:00Z"
  }
]
```

### Create Disposition

#### `POST /api/v1/disposition/`

Creates a new disposition.

**Request Body:**
```json
{
  "contacto": 1,
  "opcion_calificacion": 1,
  "observaciones": "Customer interested"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "contacto": 1,
  "opcion_calificacion": 1,
  "fecha": "2024-01-01T10:00:00Z"
}
```

### Update Disposition

#### `PUT /api/v1/disposition/{id}/`

Updates an existing disposition.

**Path Parameters:**
- `id` (integer): Disposition ID

**Request Body:**
```json
{
  "opcion_calificacion": 2,
  "observaciones": "Updated notes"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "opcion_calificacion": 2,
  "observaciones": "Updated notes"
}
```

### Create Disposition for New Contact

#### `POST /api/v1/new_contact/disposition/`

Creates a disposition for a new contact.

**Request Body:**
```json
{
  "campana": 1,
  "telefono": "1234567890",
  "opcion_calificacion": 1,
  "observaciones": "New contact"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "contacto": 1,
  "opcion_calificacion": 1
}
```

### Get Campaign Contacts

#### `GET /api/v1/campaign/{pk_campana}/contacts/`

Returns contacts for a campaign (excluding already dispositioned).

**Path Parameters:**
- `pk_campana` (integer): Campaign ID

**Query Parameters:**
- `search[value]` (string, optional): Search term
- `start` (integer, optional): Pagination start
- `length` (integer, optional): Number of records

**Response (200 OK):**
```json
{
  "data": [
    {
      "id": 1,
      "telefono": "1234567890",
      "nombre": "John Doe"
    }
  ],
  "recordsTotal": 100,
  "recordsFiltered": 50
}
```

### Click to Call

#### `POST /api/v1/makeCall/`

Initiates a click-to-call.

**Request Body:**
```json
{
  "campana_id": 1,
  "contacto_id": 1,
  "phone_number": "1234567890"
}
```

**Response (200 OK):**
```json
{
  "status": "OK",
  "call_id": "1234567890.123"
}
```

### Click to Call Outside Campaign

#### `POST /api/v1/make_call_outside_campaign/`

Initiates a click-to-call outside of a campaign.

**Request Body:**
```json
{
  "phone_number": "1234567890",
  "agent_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK",
  "call_id": "1234567890.123"
}
```

### Hang Up Call

#### `POST /api/v1/hangupCall/`

Hangs up the current call of the authenticated agent.

The endpoint uses the agent profile of the authenticated user. It first checks Redis (`OML:AGENT:{agent_id}`) for the field **CALLID**. If the agent has an active call managed by the ACD (CALLID present) and Redis is available, the endpoint publishes a **HANGUP** command to Redis Pub/Sub on the channel `acd:commands:{NODE_ID}` (or the node where the agent is logged in). The ACD CommandListener receives the message and CommandDispatcher executes `_handle_hangup`: it hangs up the associated channels, destroys the bridge, and unregisters the call from the state store.

If there is no CALLID (call not managed by ACD) or Redis is unavailable, the endpoint returns `"status": "ERROR"` (no AMI fallback).

**Authentication:** Required (session or token). The user must have an agent profile.

**Request Body:** None required. The call to hang up is always the current call of the authenticated agent.

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

**Response (200 OK) when no CALLID or Redis unavailable:**
```json
{
  "status": "ERROR"
}
```

### Agent Login to Asterisk

#### `POST /api/v1/asterisk_login/`

Logs the agent into Asterisk.

**Request Body:**
```json
{
  "agent_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Agent Ready

#### `POST /api/v1/asterisk_ready/`

Sets the agent status to ready.

**Request Body:**
```json
{
  "agent_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Agent Logout from Asterisk

#### `POST /api/v1/asterisk_logout/`

Logs the agent out of Asterisk.

**Request Body:**
```json
{
  "agent_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Agent Logout

#### `POST /agente/logout/`

Logs the agent out of the system.

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Agent Pause

#### `POST /api/v1/asterisk_pause/`

Pauses the agent.

**Request Body:**
```json
{
  "agent_id": 1,
  "pause_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Agent Unpause

#### `POST /api/v1/asterisk_unpause/`

Unpauses the agent.

**Request Body:**
```json
{
  "agent_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Agent Ringing

#### `POST /api/v1/asterisk_ringing/`

Notifies that the agent phone is ringing.

**Request Body:**
```json
{
  "agent_id": 1,
  "call_id": "1234567890.123"
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Agent Reject Call

#### `POST /api/v1/asterisk_reject_call/`

Rejects an incoming call.

**Request Body:**
```json
{
  "agent_id": 1,
  "call_id": "1234567890.123"
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Agent Disabled

#### `POST /api/v1/asterisk_disabled/`

Notifies that the agent is disabled.

**Request Body:**
```json
{
  "agent_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Notify End Transferred Call

#### `POST /api/v1/notify_end_transferred_call/`

Notifies that a transferred call has ended.

**Request Body:**
```json
{
  "call_id": "1234567890.123"
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Set Audit Revision Status

#### `POST /api/v1/audit/set_revision_status/`

Sets the revision status for an audit record.

**Request Body:**
```json
{
  "audit_id": 1,
  "status": "APPROVED"
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Qualify Call

#### `POST /api/v1/calificar_llamada/`

Qualifies a call.

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "opcion_calificacion": 1,
  "observaciones": "Notes"
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Hold Event

#### `POST /api/v1/evento_hold/`

Notifies a hold event.

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "agent_id": 1,
  "action": "HOLD"
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Consultative Conference Hold

#### `POST /api/v1/agent/consultative_confer_hold`

Manages consultative conference hold.

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "agent_id": 1,
  "action": "HOLD"
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Transfer Options

#### `GET /api/v1/agent/transfer_options`

Returns available transfer options for an agent.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "name": "Agent Transfer",
    "type": "AGENT"
  }
]
```

---

## Campaign Management

### Campaign Agents

#### `GET /api/v1/campaign/{campaign_id}/agents/`

Returns agents assigned to a campaign.

**Path Parameters:**
- `campaign_id` (integer): Campaign ID

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "username": "agent1",
    "campaign_id": 1
  }
]
```

### Update Campaign Agents

#### `POST /api/v1/campaign/agents_update/`

Updates agents assigned to a campaign.

**Request Body:**
```json
{
  "campaign_id": 1,
  "agent_ids": [1, 2, 3]
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Update Agent Campaigns

#### `POST /api/v1/agent/campaigns_update/`

Updates campaigns assigned to an agent.

**Request Body:**
```json
{
  "agent_id": 1,
  "campaign_ids": [1, 2, 3]
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Active Agents

#### `GET /api/v1/active_agents/`

Returns all active agents.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "username": "agent1",
    "status": "READY"
  }
]
```

---

## Contact Database

### Create Contact Database

#### `POST /api/v1/contact_database/create/`

Creates a new contact database.

**Request Body:**
```json
{
  "nombre": "Database Name",
  "description": "Description"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "Database Name",
  "status": "OK"
}
```

### Create Contact

#### `POST /api/v1/contact_database/{db_pk}/contact/`

Creates a new contact in a database.

**Path Parameters:**
- `db_pk` (integer): Database ID

**Request Body:**
```json
{
  "telefono": "1234567890",
  "nombre": "John Doe",
  "email": "john@example.com"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "telefono": "1234567890",
  "nombre": "John Doe"
}
```

### Campaigns on Database

#### `GET /api/v1/contact_database/{pk}/campaings/`

Returns campaigns associated with a contact database.

**Path Parameters:**
- `pk` (integer): Database ID

**Response (200 OK):**
```json
{
  "status": "SUCCESS",
  "data": {
    "id": 1,
    "nombre": "Database Name",
    "campanas": [
      {
        "id": 1,
        "nombre": "Campaign Name"
      }
    ]
  }
}
```

### Create Contact for Campaign

#### `POST /api/v1/new_contact/`

Creates a new contact for a campaign.

**Request Body:**
```json
{
  "idCampaign": 1,
  "telefono": "1234567890",
  "nombre": "John Doe"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "telefono": "1234567890",
  "nombre": "John Doe"
}
```

### Campaign Database Metadata

#### `GET /api/v1/campaign/database_metadata/`

Returns metadata for a campaign's contact database.

**Query Parameters:**
- `campaign_id` (integer): Campaign ID

**Response (200 OK):**
```json
{
  "columns": [
    {
      "name": "telefono",
      "type": "string"
    }
  ],
  "total_contacts": 1000
}
```

### Database Metadata Columns and Fields

#### `GET /api/v1/campaign/database_metadata_columns_fields/{pk}/`

Returns column and field information for a database.

**Path Parameters:**
- `pk` (integer): Database ID

**Response (200 OK):**
```json
{
  "columns": ["telefono", "nombre", "email"],
  "address_fields": ["direccion", "ciudad", "provincia"]
}
```

---

## Call Dispositions

### List Dispositions

#### `GET /api/v1/call_dispositions/`

Returns a list of all call dispositions.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Interested",
    "tipo": "GESTION"
  }
]
```

### Get Disposition

#### `GET /api/v1/call_dispositions/{pk}/`

Returns details of a specific disposition.

**Path Parameters:**
- `pk` (integer): Disposition ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Interested",
  "tipo": "GESTION"
}
```

### Create Disposition

#### `POST /api/v1/call_dispositions/create/`

Creates a new call disposition.

**Request Body:**
```json
{
  "nombre": "Interested",
  "tipo": "GESTION"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "Interested",
  "tipo": "GESTION"
}
```

### Update Disposition

#### `POST /api/v1/call_dispositions/{pk}/update/`

Updates an existing call disposition.

**Path Parameters:**
- `pk` (integer): Disposition ID

**Request Body:**
```json
{
  "nombre": "Very Interested",
  "tipo": "GESTION"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Very Interested",
  "tipo": "GESTION"
}
```

### Delete Disposition

#### `POST /api/v1/call_dispositions/{pk}/delete/`

Deletes a call disposition.

**Path Parameters:**
- `pk` (integer): Disposition ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## Pause Sets

### Pause Options

#### `GET /api/v1/pause_sets/pause_options/`

Returns available pause options.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Lunch",
    "tipo": "PAUSA"
  }
]
```

### List Pause Sets

#### `GET /api/v1/pause_sets/`

Returns a list of all pause sets.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Default Pause Set"
  }
]
```

### Get Pause Set

#### `GET /api/v1/pause_sets/{pk}/`

Returns details of a specific pause set.

**Path Parameters:**
- `pk` (integer): Pause set ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Default Pause Set",
  "pauses": [
    {
      "id": 1,
      "nombre": "Lunch"
    }
  ]
}
```

### Create Pause Set

#### `POST /api/v1/pause_sets/create/`

Creates a new pause set.

**Request Body:**
```json
{
  "nombre": "New Pause Set"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "New Pause Set"
}
```

### Update Pause Set

#### `POST /api/v1/pause_sets/{pk}/update/`

Updates an existing pause set.

**Path Parameters:**
- `pk` (integer): Pause set ID

**Request Body:**
```json
{
  "nombre": "Updated Pause Set"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Updated Pause Set"
}
```

### Delete Pause Set

#### `POST /api/v1/pause_sets/{pk}/delete/`

Deletes a pause set.

**Path Parameters:**
- `pk` (integer): Pause set ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Create Pause Configuration

#### `POST /api/v1/pause_config/create/`

Creates a pause configuration.

**Request Body:**
```json
{
  "pause_set": 1,
  "pause": 1,
  "time_limit": 30
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "pause_set": 1,
  "pause": 1,
  "time_limit": 30
}
```

### Update Pause Configuration

#### `POST /api/v1/pause_config/{pk}/update/`

Updates a pause configuration.

**Path Parameters:**
- `pk` (integer): Configuration ID

**Request Body:**
```json
{
  "time_limit": 60
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "time_limit": 60
}
```

### Delete Pause Configuration

#### `POST /api/v1/pause_config/{pk}/delete/`

Deletes a pause configuration.

**Path Parameters:**
- `pk` (integer): Configuration ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## Pauses

### List Pauses

#### `GET /api/v1/pauses/`

Returns a list of all pauses.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Lunch",
    "tipo": "PAUSA"
  }
]
```

### Get Pause

#### `GET /api/v1/pauses/{pk}/`

Returns details of a specific pause.

**Path Parameters:**
- `pk` (integer): Pause ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Lunch",
  "tipo": "PAUSA"
}
```

### Create Pause

#### `POST /api/v1/pauses/create/`

Creates a new pause.

**Request Body:**
```json
{
  "nombre": "Break",
  "tipo": "PAUSA"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "Break",
  "tipo": "PAUSA"
}
```

### Update Pause

#### `POST /api/v1/pauses/{pk}/update/`

Updates an existing pause.

**Path Parameters:**
- `pk` (integer): Pause ID

**Request Body:**
```json
{
  "nombre": "Extended Break"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Extended Break"
}
```

### Delete Pause

#### `POST /api/v1/pauses/{pk}/delete/`

Deletes a pause.

**Path Parameters:**
- `pk` (integer): Pause ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Reactivate Pause

#### `POST /api/v1/pauses/{pk}/reactivate/`

Reactivates a deactivated pause.

**Path Parameters:**
- `pk` (integer): Pause ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## External Sites

### List External Sites

#### `GET /api/v1/external_sites/`

Returns a list of all external sites.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "External Site",
    "url": "https://example.com"
  }
]
```

### Get External Site

#### `GET /api/v1/external_sites/{pk}/`

Returns details of a specific external site.

**Path Parameters:**
- `pk` (integer): External site ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "External Site",
  "url": "https://example.com"
}
```

### Create External Site

#### `POST /api/v1/external_sites/create/`

Creates a new external site.

**Request Body:**
```json
{
  "nombre": "New External Site",
  "url": "https://newsite.com"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "New External Site",
  "url": "https://newsite.com"
}
```

### Update External Site

#### `POST /api/v1/external_sites/{pk}/update/`

Updates an existing external site.

**Path Parameters:**
- `pk` (integer): External site ID

**Request Body:**
```json
{
  "nombre": "Updated Site",
  "url": "https://updated.com"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Updated Site",
  "url": "https://updated.com"
}
```

### Delete External Site

#### `POST /api/v1/external_sites/{pk}/delete/`

Deletes an external site.

**Path Parameters:**
- `pk` (integer): External site ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Hide External Site

#### `POST /api/v1/external_sites/{pk}/hide/`

Hides an external site.

**Path Parameters:**
- `pk` (integer): External site ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Show External Site

#### `POST /api/v1/external_sites/{pk}/show/`

Shows a hidden external site.

**Path Parameters:**
- `pk` (integer): External site ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## External Site Authentication

### List External Site Authentications

#### `GET /api/v1/external_site_authentications/`

Returns a list of all external site authentications.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "external_site": 1,
    "auth_type": "BASIC"
  }
]
```

### Get External Site Authentication

#### `GET /api/v1/external_site_authentications/{pk}/`

Returns details of a specific external site authentication.

**Path Parameters:**
- `pk` (integer): Authentication ID

**Response (200 OK):**
```json
{
  "id": 1,
  "external_site": 1,
  "auth_type": "BASIC",
  "username": "user"
}
```

### Create External Site Authentication

#### `POST /api/v1/external_site_authentications/create/`

Creates a new external site authentication.

**Request Body:**
```json
{
  "external_site": 1,
  "auth_type": "BASIC",
  "username": "user",
  "password": "pass"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "external_site": 1,
  "auth_type": "BASIC"
}
```

### Test External Site Authentication

#### `POST /api/v1/external_site_authentications/test/`

Tests an external site authentication.

**Request Body:**
```json
{
  "external_site": 1,
  "auth_type": "BASIC",
  "username": "user",
  "password": "pass"
}
```

**Response (200 OK):**
```json
{
  "status": "OK",
  "message": "Authentication successful"
}
```

### Update External Site Authentication

#### `POST /api/v1/external_site_authentications/{pk}/update/`

Updates an existing external site authentication.

**Path Parameters:**
- `pk` (integer): Authentication ID

**Request Body:**
```json
{
  "username": "newuser",
  "password": "newpass"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "username": "newuser"
}
```

### Delete External Site Authentication

#### `POST /api/v1/external_site_authentications/{pk}/delete/`

Deletes an external site authentication.

**Path Parameters:**
- `pk` (integer): Authentication ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## External Systems

### List External Systems

#### `GET /api/v1/external_systems/`

Returns a list of all external systems.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "External System",
    "type": "CRM"
  }
]
```

### Get External System

#### `GET /api/v1/external_systems/{pk}/`

Returns details of a specific external system.

**Path Parameters:**
- `pk` (integer): External system ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "External System",
  "type": "CRM"
}
```

### Create External System

#### `POST /api/v1/external_systems/create/`

Creates a new external system.

**Request Body:**
```json
{
  "nombre": "New External System",
  "type": "CRM"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "New External System",
  "type": "CRM"
}
```

### Update External System

#### `POST /api/v1/external_systems/{pk}/update/`

Updates an existing external system.

**Path Parameters:**
- `pk` (integer): External system ID

**Request Body:**
```json
{
  "nombre": "Updated System"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Updated System"
}
```

### Agents in External System

#### `GET /api/v1/agents_external_system/`

Returns agents associated with external systems.

**Response (200 OK):**
```json
[
  {
    "agent_id": 1,
    "external_system_id": 1,
    "external_id": "EXT123"
  }
]
```

---

## Forms

### List Forms

#### `GET /api/v1/forms/`

Returns a list of all forms.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Contact Form",
    "campana": 1
  }
]
```

### Get Form

#### `GET /api/v1/forms/{pk}/`

Returns details of a specific form.

**Path Parameters:**
- `pk` (integer): Form ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Contact Form",
  "campana": 1,
  "fields": [
    {
      "name": "nombre",
      "type": "text"
    }
  ]
}
```

### Create Form

#### `POST /api/v1/forms/create/`

Creates a new form.

**Request Body:**
```json
{
  "nombre": "New Form",
  "campana": 1,
  "fields": [
    {
      "name": "nombre",
      "type": "text"
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "New Form",
  "campana": 1
}
```

### Update Form

#### `POST /api/v1/forms/{pk}/update/`

Updates an existing form.

**Path Parameters:**
- `pk` (integer): Form ID

**Request Body:**
```json
{
  "nombre": "Updated Form"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Updated Form"
}
```

### Delete Form

#### `POST /api/v1/forms/{pk}/delete/`

Deletes a form.

**Path Parameters:**
- `pk` (integer): Form ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Hide Form

#### `POST /api/v1/forms/{pk}/hide/`

Hides a form.

**Path Parameters:**
- `pk` (integer): Form ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Show Form

#### `POST /api/v1/forms/{pk}/show/`

Shows a hidden form.

**Path Parameters:**
- `pk` (integer): Form ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## Inbound Routes

### List Inbound Routes

#### `GET /api/v1/inbound_routes/`

Returns a list of all inbound routes.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Route 1",
    "telefono": "1234567890"
  }
]
```

### Get Inbound Route

#### `GET /api/v1/inbound_routes/{pk}/`

Returns details of a specific inbound route.

**Path Parameters:**
- `pk` (integer): Route ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Route 1",
  "telefono": "1234567890",
  "destinations": []
}
```

### Create Inbound Route

#### `POST /api/v1/inbound_routes/create/`

Creates a new inbound route.

**Request Body:**
```json
{
  "nombre": "New Route",
  "telefono": "1234567890"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "New Route",
  "telefono": "1234567890"
}
```

### Update Inbound Route

#### `POST /api/v1/inbound_routes/{pk}/update/`

Updates an existing inbound route.

**Path Parameters:**
- `pk` (integer): Route ID

**Request Body:**
```json
{
  "nombre": "Updated Route"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Updated Route"
}
```

### Delete Inbound Route

#### `POST /api/v1/inbound_routes/{pk}/delete/`

Deletes an inbound route.

**Path Parameters:**
- `pk` (integer): Route ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### Inbound Route Destinations

#### `GET /api/v1/inbound_routes/destinations_by_type/`

Returns available destinations by type for inbound routes.

**Query Parameters:**
- `type` (integer): Destination type

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Campaign 1",
    "type": "CAMPAIGN"
  }
]
```

---

## Outbound Routes

### List Outbound Routes

#### `GET /api/v1/outbound_routes/`

Returns a list of all outbound routes.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Route 1"
  }
]
```

### Get Outbound Route

#### `GET /api/v1/outbound_routes/{pk}/`

Returns details of a specific outbound route.

**Path Parameters:**
- `pk` (integer): Route ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Route 1",
  "trunks": []
}
```

### Create Outbound Route

#### `POST /api/v1/outbound_routes/create/`

Creates a new outbound route.

**Request Body:**
```json
{
  "nombre": "New Route"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "New Route"
}
```

### Update Outbound Route

#### `POST /api/v1/outbound_routes/{pk}/update/`

Updates an existing outbound route.

**Path Parameters:**
- `pk` (integer): Route ID

**Request Body:**
```json
{
  "nombre": "Updated Route"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Updated Route"
}
```

### Delete Outbound Route

#### `POST /api/v1/outbound_routes/{pk}/delete/`

Deletes an outbound route.

**Path Parameters:**
- `pk` (integer): Route ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### SIP Trunks

#### `GET /api/v1/outbound_routes/sip_trunks/`

Returns available SIP trunks.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Trunk 1"
  }
]
```

### Orphan Trunks

#### `GET /api/v1/outbound_routes/{pk}/orphan_trunks`

Returns orphan trunks for a route.

**Path Parameters:**
- `pk` (integer): Route ID

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Orphan Trunk"
  }
]
```

### Reorder Routes

#### `POST /api/v1/outbound_routes/reorder/`

Reorders outbound routes.

**Request Body:**
```json
{
  "route_ids": [2, 1, 3]
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## Group of Hours

### List Group of Hours

#### `GET /api/v1/group_of_hours/`

Returns a list of all group of hours.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Business Hours"
  }
]
```

### Get Group of Hours

#### `GET /api/v1/group_of_hours/{pk}/`

Returns details of a specific group of hours.

**Path Parameters:**
- `pk` (integer): Group ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Business Hours",
  "schedules": [
    {
      "day": "MONDAY",
      "start": "09:00",
      "end": "18:00"
    }
  ]
}
```

### Create Group of Hours

#### `POST /api/v1/group_of_hours/create/`

Creates a new group of hours.

**Request Body:**
```json
{
  "nombre": "New Hours",
  "schedules": [
    {
      "day": "MONDAY",
      "start": "09:00",
      "end": "18:00"
    }
  ]
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "New Hours"
}
```

### Update Group of Hours

#### `POST /api/v1/group_of_hours/{pk}/update/`

Updates an existing group of hours.

**Path Parameters:**
- `pk` (integer): Group ID

**Request Body:**
```json
{
  "nombre": "Updated Hours"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Updated Hours"
}
```

### Delete Group of Hours

#### `POST /api/v1/group_of_hours/{pk}/delete/`

Deletes a group of hours.

**Path Parameters:**
- `pk` (integer): Group ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## IVRs

### List IVRs

#### `GET /api/v1/ivrs/`

Returns a list of all IVRs.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Main IVR"
  }
]
```

### Get IVR

#### `GET /api/v1/ivrs/{pk}/`

Returns details of a specific IVR.

**Path Parameters:**
- `pk` (integer): IVR ID

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Main IVR",
  "audio": 1,
  "options": []
}
```

### Create IVR

#### `POST /api/v1/ivrs/create/`

Creates a new IVR.

**Request Body:**
```json
{
  "nombre": "New IVR",
  "audio": 1
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "nombre": "New IVR",
  "audio": 1
}
```

### Update IVR

#### `POST /api/v1/ivrs/{pk}/update/`

Updates an existing IVR.

**Path Parameters:**
- `pk` (integer): IVR ID

**Request Body:**
```json
{
  "nombre": "Updated IVR"
}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "nombre": "Updated IVR"
}
```

### Delete IVR

#### `POST /api/v1/ivrs/{pk}/delete/`

Deletes an IVR.

**Path Parameters:**
- `pk` (integer): IVR ID

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

### IVR Audio Options

#### `GET /api/v1/ivrs/audio_options/`

Returns available audio options for IVRs.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Welcome Message",
    "file": "welcome.wav"
  }
]
```

### IVR Destination Types

#### `GET /api/v1/ivrs/destination_types/`

Returns available destination types for IVRs.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Campaign",
    "type": "CAMPAIGN"
  }
]
```

---

## Register Server

### List Register Servers

#### `GET /api/v1/register_server/`

Returns a list of register servers.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "host": "sip.example.com",
    "port": 5060
  }
]
```

### Create Register Server

#### `POST /api/v1/register_server/create/`

Creates a new register server.

**Request Body:**
```json
{
  "host": "sip.example.com",
  "port": 5060,
  "username": "user",
  "password": "pass"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "host": "sip.example.com",
  "port": 5060
}
```

---

## Recordings

### Get Recording File

#### `GET /api/v1/grabacion/archivo/`

Returns a recording file.

**Query Parameters:**
- `callid` (string): Call ID

**Response:** Audio file download

### Bulk Download Recordings

#### `GET /api/v1/grabacion/descarga_masiva`

Downloads multiple recordings.

**Query Parameters:**
- `callids` (string, comma-separated): Call IDs

**Response:** ZIP file with recordings

### Get Recording URL

#### `GET /api/v1/call_record/{callid}/`

Returns a URL to access a recording.

**Path Parameters:**
- `callid` (string): Call ID

**Response (200 OK):**
```json
{
  "url": "https://example.com/recordings/1234567890.123.wav",
  "expires_in": 3600
}
```

---

## Audit

### Get Audit File

#### `GET /api/v1/auditoria/archivo`

Returns an audit file.

**Query Parameters:**
- `audit_id` (integer): Audit ID

**Response:** Audio file download

---

## Audio Files

### List Audio Files

#### `GET /api/v1/audio/list/`

Returns a list of available audio files.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Welcome",
    "file": "welcome.wav"
  }
]
```

### List Asterisk Audio Languages

#### `GET /api/v1/languages/list`

Returns a list of available audio languages.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "code": "en",
    "name": "English"
  }
]
```

---

## Users

### List Groups

#### `GET /api/v1/group/list/`

Returns a list of all groups.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "name": "Group 1"
  }
]
```

### List Agents

#### `GET /api/v1/agent/list/`

Returns a list of all agents.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "username": "agent1",
    "sip_extension": "1001"
  }
]
```

---

## Wombat Dialer

### Restart Wombat

#### `POST /api/v1/wombat_dialer/restart/`

Restarts the Wombat dialer service.

**Response (200 OK):**
```json
{
  "status": "OK",
  "message": "Wombat restarted"
}
```

### Wombat Status

#### `GET /api/v1/wombat_dialer/status/`

Returns the status of the Wombat dialer.

**Response (200 OK):**
```json
{
  "status": "RUNNING",
  "uptime": "2 days"
}
```

### Start Wombat

#### `POST /api/v1/wombat_dialer/start/`

Starts the Wombat dialer service.

**Response (200 OK):**
```json
{
  "status": "OK",
  "message": "Wombat started"
}
```

### Stop Wombat

#### `POST /api/v1/wombat_dialer/stop/`

Stops the Wombat dialer service.

**Response (200 OK):**
```json
{
  "status": "OK",
  "message": "Wombat stopped"
}
```

---

## Asterisk

### Asterisk Queues Data

#### `GET /api/v1/asterisk/queues_data/`

Returns data about Asterisk queues.

**Response (200 OK):**
```json
{
  "queues": [
    {
      "name": "queue1",
      "members": 5,
      "calls": 2
    }
  ]
}
```

### Notify Attended Multinum Call

#### `POST /api/v1/asterisk/notify_attended_multinum_call/`

Notifies that a multinum call was attended.

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "agent_id": 1
}
```

**Response (200 OK):**
```json
{
  "status": "OK"
}
```

---

## Inbound Destinations

### List Inbound Destinations

#### `GET /api/v1/inbound_destinations/{type}/list/`

Returns inbound destinations by type.

**Path Parameters:**
- `type` (integer): Destination type

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Campaign 1",
    "type": "CAMPAIGN"
  }
]
```

### List Inbound Destination Types

#### `GET /api/v1/inbound_destinations_types/list/`

Returns available inbound destination types.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Campaign",
    "type": "CAMPAIGN"
  }
]
```

---

## Logging

### Create Survey Transfer Log

#### `POST /api/v1/reportes/survey_transfer/`

Creates a log entry for a survey transfer.

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "survey_id": 1
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "call_id": "1234567890.123",
  "survey_id": 1
}
```

---

## Reports

### Agent Status

#### `GET /api/v1/agent_status/campaign/{campaign_id}`

Returns agent status for a campaign.

**Path Parameters:**
- `campaign_id` (integer): Campaign ID

**Response (200 OK):**
```json
{
  "agents": [
    {
      "id": 1,
      "status": "READY",
      "calls": 5
    }
  ]
}
```

### Agent Status List

#### `GET /api/v1/agent_status_list/campaign/{campaign_id}`

Returns a list of agent statuses for a campaign.

**Path Parameters:**
- `campaign_id` (integer): Campaign ID

**Response (200 OK):**
```json
[
  {
    "agent_id": 1,
    "status": "READY",
    "timestamp": "2024-01-01T10:00:00Z"
  }
]
```

### Call Status

#### `GET /api/v1/call_status/campaign/{campaign_id}`

Returns call status for a campaign.

**Path Parameters:**
- `campaign_id` (integer): Campaign ID

**Response (200 OK):**
```json
{
  "active_calls": 10,
  "waiting_calls": 5,
  "completed_calls": 100
}
```

---

## Agent and Interaction Reports

These endpoints provide agent activity, availability, and interaction (voice) KPIs for reporting dashboards. Data comes from `AgentActivityEventV2` (availability) and `interactions_summary` (voice interactions). All require authentication (session or `Bearer` token) and `TienePermisoOML`.

### Agents Activity V2 Report

#### `GET /api/v1/reportes/agents_activity_v2/`

Returns agent activity data in a flat format for the Performance Report (one row per agent over the date range), **paginated**. Combines availability and interaction metrics. For this endpoint, `inbound_count` and `outbound_count` include VOICE + WhatsApp conversations assigned to the agent, while `total_interactions` keeps its current VOICE definition.

**Query Parameters:**
- `date_start` (string, required): Start date (YYYY-MM-DD)
- `date_end` (string, required): End date (YYYY-MM-DD). Range cannot exceed 31 days.
- `page` (integer, optional): Page number (1-based). Default: 1.
- `page_size` (integer, optional): Number of agents per page. Allowed values: 10, 20, 30, 40, 50. Default: 10. Invalid values fall back to 10.
- `agente` (list, optional): Agent IDs to filter (repeat for multiple, e.g. `agente=1&agente=2`). Omit or use `__all_agents__` for all visible agents.
- `grupo_agente` (list, optional): Group IDs to filter (repeat for multiple). Omit or use `__all_groups__` for all visible groups.

**Response (200 OK):**
```json
{
  "group_by": "agent",
  "date_start": "2025-02-01",
  "date_end": "2025-02-05",
  "data": [
    {
      "agent_id": 1,
      "agent_name": "John Doe",
      "session_seconds": 28800,
      "ready_seconds": 14400,
      "ready_pct": 50.0,
      "pause_seconds": 3600,
      "pause_pct": 12.5,
      "acw_seconds": 10800,
      "acw_pct": 37.5,
      "total_interactions": 45,
      "inbound_count": 30,
      "outbound_count": 15,
      "conversation_seconds": 7200.5,
      "tmo_avg": 160.0,
      "act_avg": 95.4,
      "transfer_count": 5,
      "transfer_pct": 11.1,
      "wait_conn_avg": 12.3
    }
  ],
  "total_count": 1,
  "page": 1,
  "page_size": 10,
  "num_pages": 1
}
```
- `total_count`: Total number of agents (before pagination).
- `page`: Current page number.
- `page_size`: Number of items per page.
- `num_pages`: Total number of pages.

**Flat row fields:**
- `agent_id`, `agent_name`: Agent identifier and display name
- `session_seconds`, `ready_seconds`, `pause_seconds`, `acw_seconds`: Availability times (seconds)
- `ready_pct`, `pause_pct`, `acw_pct`: Percentages of session time
- `total_interactions`: Interaction total (current VOICE definition)
- `inbound_count`, `outbound_count`: In/Out counts (VOICE + WhatsApp conversations by agent)
- `conversation_seconds`: Total talk time (seconds)
- `tmo_avg`: Average talk time for answered calls (seconds)
- `act_avg`: Average WhatsApp conversation time (seconds), computed from `ConversacionWhatsapp` as `date_last_interaction - timestamp` for valid attended conversations
- `transfer_count`: Successful transfers made by the agent (`interaction_transfers.status='OK'`)
- `transfer_pct`: Transfer KPI as percentage: `(transfer_count / total_interactions) * 100`
- `wait_conn_avg`: Average wait-to-connect time (seconds)

**Error Responses:**
- `400 Bad Request`: Missing or invalid `date_start`/`date_end`, or range &gt; 31 days

---

### Export CSV Agents Activity V2 (Listado)

#### `POST /api/v1/exportar_csv_agents_activity_v2_listado/`

Inicia la exportación asíncrona a CSV del tab `Listado` de `agents_activity_v2`.  
El CSV respeta el subconjunto visible según filtros de pantalla (`desde/hasta`, `agente`, `grupo_agente`) aplicando intersección entre agente y grupo cuando ambos se informan.

**Request Body (JSON):**
```json
{
  "task_id": "abc123xyz",
  "desde": "01/02/2025",
  "hasta": "01/02/2025",
  "agente": ["__all_agents__"],
  "grupo_agente": ["__all_groups__"]
}
```

**Notas de request:**
- `task_id` (string, required): identificador de tarea para progreso y descarga
- `desde`, `hasta` (string, required): formato `DD/MM/YYYY`
- Rango máximo: 31 días
- `agente` (array/string, optional): IDs de agentes o `__all_agents__`
- `grupo_agente` (array/string, optional): IDs de grupos o `__all_groups__`

**Response (200 OK):**
```json
{
  "status": "OK",
  "msg": "Exportación de Listado de Agentes (Performance) a CSV en proceso.",
  "id": "abc123xyz"
}
```

**Flujo de descarga:**
- Progreso vía WebSocket:
  - `/consumers/reporte_grafico_campana/agents_activity_listado/cc/<task_id>`
- URL de descarga del archivo generado:
  - `/reportes/agents-activity-v2/exportar_listado_csv/<task_id>/`

**Error Responses:**
- `400 Bad Request`: falta `task_id`, fechas inválidas, rango &gt; 31 días, agente/grupo inválido o fuera de visibilidad

---

### Agents KPIs V2 Report

#### `GET /api/v1/reportes/agents_kpis_v2/`

Returns unified agent KPIs: availability (session, ready, pause, ACW), interactions (voice from `interactions_summary`), and derived metrics (oncall ratio, sales per hour). Can be grouped by agent (one row per agent) or by day (one row per agent per day).

**Query Parameters:**
- `date_start` (string, required): Start date (YYYY-MM-DD)
- `date_end` (string, required): End date (YYYY-MM-DD). Range cannot exceed 31 days
- `agent_id` (integer, optional): Filter by agent ID
- `group_by` (string, optional): `agent` (one row per agent) or `day` (one row per agent and day). Default: `day`
- `include_pause_breakdown` (optional): Include pause breakdown by pause_id/aux_code. Default: 1 (true). Accepts 1/0, true/false, yes/no
- `include_interactions` (optional): Include interactions block. Default: 1 (true)
- `include_derived` (optional): Include derived block. Default: 1 (true)

**Response (200 OK):**
```json
{
  "date_start": "2025-02-01",
  "date_end": "2025-02-05",
  "since": "2025-02-01T00:00:00",
  "until": "2025-02-05T23:59:59.999999",
  "group_by": "day",
  "data": [
    {
      "agent_id": 1,
      "agent_name": "John Doe",
      "date": "2025-02-01",
      "availability": {
        "session_seconds": 28800,
        "ready_seconds": 14400,
        "pause_seconds": 3600,
        "acw_seconds": 10800,
        "ready_ratio": 0.5,
        "pause_ratio": 0.125,
        "acw_ratio": 0.375,
        "sessions_count": 1,
        "pauses_count": 4,
        "acw_count": 45,
        "pause_breakdown": [
          { "pause_id": 1, "aux_code": "LUNCH", "seconds": 1800 }
        ]
      },
      "interactions": {
        "interactions_total": 45,
        "interactions_inbound": 30,
        "interactions_outbound": 15,
        "answered_count": 42,
        "cancel_count": 3,
        "sales_count": 10,
        "talk_seconds": 7200.5,
        "avg_talk_seconds_answered": 171.44,
        "wait_conn_duration": 520.0,
        "avg_wait_conn_duration": 12.38
      },
      "derived": {
        "oncall_seconds": 7200.5,
        "oncall_ratio": 0.25,
        "idle_real_seconds": 7199.5,
        "sales_per_hour": 1.25
      }
    }
  ]
}
```

**Availability block:** `*_seconds` are integers; ratios are float (4 decimals). `pause_breakdown` is present only when `include_pause_breakdown` is true.

**Interactions block:** Duration fields in seconds (float, 3 decimals). `wait_conn_duration` and `avg_wait_conn_duration` are from `interactions_summary.wait_conn_duration` (wait to agent connection).

**Derived block:** `oncall_seconds` = interactions.talk_seconds; `oncall_ratio` = oncall_seconds/session_seconds; `idle_real_seconds` = max(ready_seconds - oncall_seconds, 0); `sales_per_hour` = sales_count / (session_seconds/3600).

**Error Responses:**
- `400 Bad Request`: Missing/invalid `date_start` or `date_end`, invalid `agent_id`, or date range &gt; 31 days
- `500 Internal Server Error`: Server/validation error (optional strict validation may return 500 on invariant failures)

---

## Transfers

The transfer endpoints act as a side-car to publish call transfer commands to Redis Streams. These commands are consumed by the `acd.py` process which executes transfers in real-time.

### Architecture

- **Asynchronous**: Commands are queued in Redis Streams and processed asynchronously
- **Multi-node**: Supports multiple ACD instances identified by `NODE_ID`
- **Authentication**: Requires authentication via session or expiring token
- **Parameter Validation**: Validates required parameters before queuing commands

### Configuration

The API is configured via environment variables:

- `NODE_ID`: ACD node identifier (default: `acd01`)

The `NODE_ID` must match the one configured in `acd.py` for commands to be processed correctly.

### Authentication

All transfer endpoints require authentication using one of the following methods:

- **SessionAuthentication**: Django session-based authentication
- **ExpiringTokenAuthentication**: Token-based authentication with expiration using the format `Bearer <token>`

**Important**: The authentication header format must be:
```
Authorization: Bearer <your_token>
```

Do not use `Token <token>`, it must be `Bearer <token>`.

Additionally, the `TienePermisoOML` permission is required to access these endpoints.

### Response Format

All successful transfers return HTTP status code 202 (Accepted) with the following format:

```json
{
  "status": "queued",
  "message": "Command received",
  "stream_id": "<message_id>",
  "stream": "acd:stream:commands:<node_id>",
  "node_id": "<node_id>"
}
```

**Note**: Status code 202 indicates that the command was accepted and queued, but does not guarantee that the transfer has completed. Real processing occurs asynchronously in `acd.py`.

### Blind Transfer to Agent

#### `POST /api/v1/transfer/blind-agent/`

Performs a blind transfer to a specific agent identified by their logical ID. The SIP/PJSIP endpoint will be resolved on the ACD side using Redis (`OML:AGENT:STATUS:<target_agent_id>`).

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "target_agent_id": "15",
  "agent_id": "10"
}
```

**Parameters:**
- `call_id` (string, required): OMLUNIQUEID of the call to transfer
- `target_agent_id` (string, required): Logical ID of the destination agent
- `agent_id` (string, optional): ID of the agent initiating the transfer

**Response (202 Accepted):**
```json
{
  "status": "queued",
  "message": "Command received",
  "stream_id": "1234567890-0",
  "stream": "acd:stream:commands:acd01",
  "node_id": "acd01"
}
```

**Error Responses:**
- `400 Bad Request`: Missing required parameters (`call_id` or `target_agent_id`)
- `403 Forbidden`: Authentication error or insufficient permissions
- `500 Internal Server Error`: Internal server error or Redis not initialized

### Blind Transfer to Endpoint

#### `POST /api/v1/transfer/blind-endpoint/`

Performs a blind transfer to a generic SIP/PJSIP endpoint (internal extension, external trunk, etc.). This endpoint always publishes to the local `NODE_ID` stream.

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "endpoint": "PJSIP/1001",
  "agent_id": "10"
}
```

**Parameters:**
- `call_id` (string, required): OMLUNIQUEID of the call to transfer
- `endpoint` (string, required): SIP/PJSIP endpoint (e.g., `PJSIP/1001` or `PJSIP/trunk_name/1234567890`)
- `agent_id` (string, optional): ID of the agent initiating the transfer

**Response (202 Accepted):**
```json
{
  "status": "queued",
  "message": "Command received",
  "stream_id": "1234567890-0",
  "stream": "acd:stream:commands:acd01",
  "node_id": "acd01"
}
```

**Error Responses:**
- `400 Bad Request`: Missing required parameters (`call_id` or `endpoint`)
- `403 Forbidden`: Authentication error or insufficient permissions
- `500 Internal Server Error`: Internal server error or Redis not initialized

### Blind Transfer to Campaign

#### `POST /api/v1/transfer/blind-campaign/`

Performs a blind transfer to another campaign (re-queue the call). The call will be re-queued in the destination campaign.

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "target_campaign_id": "5",
  "agent_id": "10"
}
```

**Parameters:**
- `call_id` (string, required): OMLUNIQUEID of the call to transfer
- `target_campaign_id` (string, required): ID of the destination campaign
- `agent_id` (string, optional): ID of the agent initiating the transfer

**Response (202 Accepted):**
```json
{
  "status": "queued",
  "stream_id": "1234567890-0",
  "stream": "acd:stream:commands:acd01",
  "node_id": "acd01"
}
```

**Error Responses:**
- `400 Bad Request`: Missing required parameters (`call_id` or `target_campaign_id`)
- `403 Forbidden`: Authentication error or insufficient permissions
- `500 Internal Server Error`: Internal server error or Redis not initialized

### Blind Transfer to Campaign Agent

#### `POST /api/v1/transfer/blind-campaign-agent/`

Performs a blind transfer to any READY agent available in the same campaign. Automatically searches for an available agent using the strategy configured in the campaign (random, fewestcalls, leastrecent, rrmemory).

**Features:**
- Automatically searches for a READY agent in the specified campaign
- Excludes the agent initiating the transfer (if `agent_id` is provided)
- Uses the distribution strategy configured in the campaign
- Returns error 404 if no agents are available

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "campaign_id": "5",
  "agent_id": "10"
}
```

**Parameters:**
- `call_id` (string, required): OMLUNIQUEID of the call to transfer
- `campaign_id` (string, required): ID of the campaign where to search for the agent
- `agent_id` (string, optional): ID of the agent initiating the transfer (will be excluded from search)

**Supported Distribution Strategies:**
- `random`: Random agent selection
- `ringall`: Similar to random
- `fewestcalls`: Agent with fewest calls
- `leastrecent`: Agent with most recent status change
- `rrmemory`: Round-robin with memory

**Response (202 Accepted):**
```json
{
  "status": "queued",
  "message": "Command received",
  "stream_id": "1234567890-0",
  "stream": "acd:stream:commands:acd01",
  "node_id": "acd01",
  "target_agent_id": "15",
  "campaign_id": "5"
}
```

**Error Responses:**
- `400 Bad Request`: Missing required parameters (`call_id` or `campaign_id`)
- `403 Forbidden`: Authentication error or insufficient permissions
- `404 Not Found`: No READY agents available in the specified campaign
- `500 Internal Server Error`: Internal server error or Redis not initialized

### 3-Way Transfer (Conference)

#### `POST /api/v1/transfer/3way/`

Adds a third participant to an existing call, creating a 3-way conference. The original participant and the new participant join in a conference.

**Request Body:**
```json
{
  "call_id": "1234567890.123",
  "endpoint": "PJSIP/1001"
}
```

**Parameters:**
- `call_id` (string, required): OMLUNIQUEID of the existing call
- `endpoint` (string, required): SIP/PJSIP endpoint of the third participant (e.g., `PJSIP/1001`)

**Response (202 Accepted):**
```json
{
  "status": "queued",
  "stream_id": "1234567890-0",
  "stream": "acd:stream:commands:acd01",
  "node_id": "acd01"
}
```

**Error Responses:**
- `400 Bad Request`: Missing required parameters (`call_id` or `endpoint`)
- `403 Forbidden`: Authentication error or insufficient permissions
- `500 Internal Server Error`: Internal server error or Redis not initialized

### Error Responses

#### Error 400 (Bad Request)
```json
{
  "error": "Missing parameters: call_id, target_agent_id"
}
```

#### Error 403 (Forbidden)
```json
{
  "detail": "Authentication credentials were not provided."
}
```

or

```json
{
  "detail": "Invalid Token"
}
```

**Note**: Error 403 can occur due to:
- Token not provided or incorrect format (must be `Bearer <token>`, not `Token <token>`)
- Invalid or expired token
- Inactive user
- Insufficient permissions

#### Error 404 (Not Found)
```json
{
  "error": "No READY agents available in campaign 5",
  "campaign_id": "5"
}
```

#### Error 500 (Internal Server Error)
```json
{
  "error": "Redis not initialized"
}
```

or

```json
{
  "error": "<error description>"
}
```

---

## Technical Notes

### Redis Streams

Commands are published to Redis Streams with the following structure:

- **Stream Key**: `acd:stream:commands:<NODE_ID>`
- **Max Length**: 5000 messages (maintains a circular buffer)
- **Payload Format**: All values are converted to strings

### Published Actions

Each endpoint publishes a different action in the stream:

- `blind-agent`: `action: "blind_to_agent"`
- `blind-endpoint`: `action: "blind_to_endpoint"`
- `blind-campaign`: `action: "blind_to_campaign"`
- `blind-campaign-agent`: `action: "blind_to_agent"` (with automatically selected agent)
- `3way`: `action: "add_third_party"`

### Asynchronous Processing

Commands are processed asynchronously by the `acd.py` process which consumes messages from the Redis Stream. Status code 202 only indicates that the command was accepted and queued, not that the transfer has completed.

---

## Troubleshooting

### Error: "Authentication credentials were not provided"

**Cause**: The Authorization header format is incorrect.

**Solution**: Make sure to use the correct format:
```bash
Authorization: Bearer <token>
```

**Do not use**:
```bash
Authorization: Token <token>  # ❌ Incorrect
```

### Error: "Invalid Token"

**Cause**: The provided token does not exist or is invalid.

**Solution**: 
1. Verify that the token is correct
2. Obtain a new token using the login endpoint
3. Verify that the token has not expired

### Error: "The Token is expired"

**Cause**: The token has expired.

**Solution**: Obtain a new token using the login endpoint.

### Error: 403 Forbidden

**Cause**: The user does not have the necessary permissions (`TienePermisoOML`).

**Solution**: Verify that the user has the appropriate permissions in the system.

---

## Version

This documentation corresponds to the current version of the OMniLeads API.
