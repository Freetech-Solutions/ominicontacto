# Scheduling a Callback via the OMniLeads API

This guide describes how a **Voicebot integrator** (e.g. Verloop) schedules a
follow-up call on a contact using a **single** OMniLeads REST endpoint.

The voicebot platform is expected to do all natural-language interpretation on
its side (relative dates such as "llamame mañana después de las 3") and send
OMniLeads an already-normalized date and time.

---

## Overview

| Step | Endpoint | Purpose |
|------|----------|---------|
| 1 | `POST /api/v1/webhook/voicebot/agenda/` | Qualify the contact with the **Agenda** disposition **and** create/update the scheduled callback |

One request does both things:

1. Upserts the contact's disposition using the campaign's reserved **Agenda**
   disposition option (resolved internally by OMniLeads — you do not need to
   discover its ID).
2. If `callback_valid=true` and the date/time are valid, creates or updates the
   contact schedule. Repeating the same request updates the existing schedule
   (upsert by contact + campaign), so retries are idempotent.

The schedule is created as a **personal** schedule assigned to the campaign's
**voicebot agent** (`AgenteProfile.voicebot=True`, member of the campaign
queue). Supervisors can later reassign it to a human agent via
`POST /api/v1/supervision/reasignar_agenda_contacto/` or the schedules UI.

---

## Prerequisites

- **Base URL:** your OMniLeads instance (e.g. `https://omnileads.example.com`)
- **Authentication:** a static Bearer token of a service user (see below)
- **Campaign context:** the internal OMniLeads campaign ID (`CampID`)
- **Contact context:** the internal OMniLeads contact ID (`customerID`)
- **Call context:** the ACD `callid` of the active voicebot call
  (e.g. `1781910936.418884`)
- **Phone number:** one of the phone numbers associated with the contact record

### Authentication

The token belongs to a **service user** (it does not need an agent profile).
It is obtained once:

```http
POST /api/v1/login
Content-Type: application/json
```

```json
{
  "username": "voicebot_service",
  "password": "<password>"
}
```

Store the returned `token` in the voicebot platform configuration and send it
on every request:

```
Authorization: Bearer <token>
```

By default tokens do not expire (`TOKEN_EXPIRED_AFTER_SECONDS = None`). If the
instance configures an expiration, re-authenticate when the token is rejected.

### Server-side prerequisites (OMniLeads administrator)

- The campaign must have its **voicebot agent** assigned as a queue member
  (already the case when the voicebot answers the campaign calls).
- The voicebot agent's group must **not** enforce personal schedule limits
  (`limitar_agendas_personales` / `limitar_agendas_personales_en_dias`),
  otherwise requests start failing with `400` once the limit is reached.
- `callback_date`/`callback_time` are interpreted in the **OMniLeads server
  timezone**. Align it with the timezone the bot uses to normalize dates.

---

## Request

```http
POST /api/v1/webhook/voicebot/agenda/
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "X-OML-Campaign-ID": "78",
  "X-OML-Contact-ID": "418884",
  "X-OML-Call-ID": "1781910936.418884",
  "phone": "2664167431",
  "callback_valid": "true",
  "callback_date": "2026-08-11",
  "callback_time": "15:00:00",
  "callback_request": "Llamame mañana después de las 3",
  "callback_rule": "explicit_time"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `X-OML-Campaign-ID` | integer | Yes | Active OMniLeads campaign ID |
| `X-OML-Contact-ID` | integer | Yes | Contact ID belonging to the campaign's contact database |
| `X-OML-Call-ID` | string | Yes | ACD call ID of the voicebot interaction |
| `phone` | string | Yes | Phone number to call back; must be one of the contact's phone numbers |
| `callback_valid` | string/bool | No (default `false`) | Whether the bot obtained a valid normalized schedule |
| `callback_date` | string | If `callback_valid=true` | Schedule date, `YYYY-MM-DD` (server timezone) |
| `callback_time` | string | If `callback_valid=true` | Schedule time, `HH:MM:SS` or `HH:MM` |
| `callback_request` | string | No | Original customer request; stored as schedule notes |
| `callback_rule` | string | No | Normalization rule applied by the bot; stored as schedule notes |

> Every field may also be sent as an **HTTP header** with the same exact name
> (the body takes precedence). This is useful for webhook blocks that only
> allow custom headers.

### Mapping from Verloop variables

If your flow normalizes the scheduling request into variables such as
`callback_date`, `callback_time`, `callback_rule`, `callback_valid`,
`callback_request`, `CampID`, `callID`, `customerID` and `phone`, configure the
Webhook Block to send a **flat JSON body** like the example above (do not send
the nested `{"variables": {"name": {"value": ...}}}` envelope).

---

## Responses

**Scheduled (200 OK)**

```json
{
  "status": "OK",
  "calificacion_id": 501,
  "agenda_id": 99,
  "created": true,
  "warnings": []
}
```

- `created: true` — a new schedule was created.
- `created: false` — an existing schedule for the same contact and campaign was
  updated (upsert).

**Disposition recorded without scheduling (200 OK)**

When `callback_valid=false` (or the date/time cannot be parsed), OMniLeads
still records the **Agenda** disposition so the call outcome is not lost, but
no schedule is created:

```json
{
  "status": "OK",
  "calificacion_id": 501,
  "agenda_id": null,
  "created": false,
  "warnings": [
    "callback_valid=false: the disposition was recorded without scheduling"
  ]
}
```

**Errors**

| Status | Cause |
|--------|-------|
| `400` | Missing/invalid required field (`X-OML-Campaign-ID`, `X-OML-Contact-ID`, `X-OML-Call-ID`, `phone`) |
| `400` | `phone` is not one of the contact's phone numbers |
| `400` | Contact does not belong to the campaign database |
| `400` | Campaign has no voicebot agent assigned |
| `400` | Schedule business-rule validation (e.g. personal schedule limits of the voicebot agent). The whole request is rolled back, so retrying is safe. |
| `403` | Missing/invalid Bearer token |
| `404` | Campaign not found or inactive, or contact not found |
| `500` | Unexpected server error |

Error responses follow the format:

```json
{
  "status": "ERROR",
  "message": "Campaign has no voicebot agent",
  "errors": {
    "campaign": ["The campaign does not have a voicebot agent assigned"]
  }
}
```

---

## Complete Example (cURL)

```bash
BASE_URL="https://omnileads.example.com"
TOKEN="<service-user-token>"

curl -sS -X POST "${BASE_URL}/api/v1/webhook/voicebot/agenda/" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "X-OML-Campaign-ID": "78",
    "X-OML-Contact-ID": "418884",
    "X-OML-Call-ID": "1781910936.418884",
    "phone": "2664167431",
    "callback_valid": "true",
    "callback_date": "2026-08-11",
    "callback_time": "15:00:00",
    "callback_request": "Llamame mañana después de las 3",
    "callback_rule": "explicit_time"
  }'
```

---

## Integration Checklist

- [ ] Obtain a service-user token once and configure it in the voicebot platform.
- [ ] Send a flat JSON body (or headers) with the exact field names.
- [ ] Send `callback_date`/`callback_time` already normalized (server timezone).
- [ ] Use a `phone` value present in the contact record.
- [ ] Treat `200` with `agenda_id` as scheduled; `200` with `warnings` as
      "disposition recorded, not scheduled"; retry safely on `4xx/5xx`
      (the upsert makes retries idempotent).

---

## Legacy Flow (human agents)

Human agents still use the agent-oriented flow: qualify with the **Agenda**
disposition (`POST /api/v1/disposition/`) and then schedule via
`POST /api/v1/agenda_contacto/` (see
[Create Contact Schedule](./API.md#create-contact-schedule)). The voicebot
webhook above exists so bot integrations do not need agent credentials nor
multiple calls.

## Related Documentation

- [OMniLeads API — Authentication](./API.md#authentication)
- [OMniLeads API — Voicebot Webhooks](./API.md#voicebot-webhooks)
