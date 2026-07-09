# Scheduling a Callback via the OMniLeads API

This guide describes the procedure for a **Voicebot integrator** to schedule a follow-up call on a contact using the OMniLeads REST API.

The workflow mirrors what a human agent does in the OMniLeads UI: first qualify the interaction with the **Agenda** disposition, then create the contact schedule.

---

## Overview

| Step | Endpoint | Purpose |
|------|----------|---------|
| 1 | `POST /api/v1/login` | Obtain an authentication token |
| 2 | `GET /api/v1/campaign/{campaign_id}/dispositionOptions/` | Resolve the **Agenda** disposition ID for the campaign |
| 3 | `POST /api/v1/disposition/` | Qualify the contact with the **Agenda** disposition |
| 4 | `POST /api/v1/agenda_contacto/` | Create or update the scheduled callback |

> **Important:** Step 3 is mandatory. You must submit the **Agenda** disposition before calling `agenda_contacto`. This links the qualification to the scheduling action and keeps OMniLeads reporting and agent state consistent.

---

## Prerequisites

- **Base URL:** your OMniLeads instance (e.g. `https://omnileads.example.com`)
- **API prefix:** all endpoints are under `/api/v1/`
- **Credentials:** a valid OMniLeads **agent** username and password
- **Campaign context:** the internal OMniLeads campaign ID
- **Contact context:** the internal OMniLeads contact ID
- **Call context:** the Asterisk `callid` of the active Voicebot call (e.g. `1781961848.10`)
- **Phone number:** one of the phone numbers associated with the contact record

The authenticated agent must be assigned to the campaign queue. The agent role must include the `api_agenda_contacto_create` permission (assigned by default after running `actualizar_permisos`).

---

## Step 1 — Authenticate

Obtain a Bearer token to use in subsequent requests.

**Request**

```http
POST /api/v1/login
Content-Type: application/json
```

```json
{
  "username": "your_agent_username",
  "password": "your_agent_password"
}
```

**Response (200 OK)**

```json
{
  "user": {
    "id": 1,
    "username": "verloop",
    "agent_id": 5
  },
  "expires_in": "23:59:59",
  "token": "431bf3de771c920ee30ebd17d0c2ae8e31c1b1a1"
}
```

Use the returned `token` in all following requests:

```
Authorization: Bearer <token>
```

Tokens expire after a configurable period. Re-authenticate when the token is no longer valid.

---

## Step 2 — Resolve the Agenda Disposition ID

Every OMniLeads campaign includes a built-in disposition named **`Agenda`**. This is the disposition type used to indicate that the contact should receive a scheduled callback.

You must retrieve its numeric `id` dynamically for each campaign. **Do not hardcode** this value — it varies per campaign.

**Request**

```http
GET /api/v1/campaign/{campaign_id}/dispositionOptions/
Authorization: Bearer <token>
```

**Response (200 OK)**

```json
[
  {
    "id": 42,
    "name": "Interested",
    "hidden": false
  },
  {
    "id": 94,
    "name": "Agenda",
    "hidden": false
  }
]
```

**Selection rule:** find the entry where `name` equals `"Agenda"` and store its `id` (e.g. `94`). This is the `idDispositionOption` you will use in Step 3.

Hidden dispositions (`hidden: true`) are still returned by this endpoint but cannot be used when submitting a disposition.

---

## Step 3 — Submit the Agenda Disposition

Qualify the contact using the **Agenda** disposition ID obtained in Step 2. This step records the call outcome and prepares the contact for scheduling.

**Request**

```http
POST /api/v1/disposition/
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "idContact": 10,
  "idDispositionOption": 94,
  "callid": "1781961848.10",
  "comments": "Customer requested a callback tomorrow at 1 PM"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `idContact` | integer | Yes | Internal OMniLeads contact ID |
| `idDispositionOption` | integer | Yes | The **Agenda** disposition ID from Step 2 |
| `callid` | string | Recommended | Asterisk call ID of the current interaction |
| `comments` | string | No | Free-text notes about the interaction |

**Response (201 Created)**

```json
{
  "id": 501,
  "idContact": 10,
  "callid": "1781961848.10",
  "idDispositionOption": 94,
  "comments": "Customer requested a callback tomorrow at 1 PM"
}
```

**Common errors**

| Status | Cause |
|--------|-------|
| `400` | Invalid `idDispositionOption` (not found or hidden) |
| `400` | `idContact` does not belong to the disposition's campaign |
| `403` | Authenticated user is not an agent |

> **Why this step matters:** OMniLeads treats **Agenda** as a special disposition type. Submitting it before scheduling ensures the qualification is recorded against the call and the subsequent schedule is correctly associated with that qualification.

---

## Step 4 — Schedule the Callback

Create or update the contact schedule with the desired date, time, and phone number.

**Request**

```http
POST /api/v1/agenda_contacto/
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "campaign_id": 16,
  "contact_id": 10,
  "date": "2026-06-20",
  "time": "13:00:00",
  "phone": "123456746",
  "schedule_type": 1,
  "observations": "Call tomorrow"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `campaign_id` | integer | Yes | Active campaign ID |
| `contact_id` | integer | Yes | Contact ID belonging to the campaign database |
| `date` | string | Yes | Schedule date in `YYYY-MM-DD` format |
| `time` | string | Yes | Schedule time in `HH:MM:SS` or `HH:MM` format |
| `phone` | string | Yes | A phone number from the contact's available phone list |
| `schedule_type` | integer | No | `1` = Personal (default), `2` = Global (dialer campaigns only) |
| `observations` | string | No | Notes for the scheduled callback |

**Response (200 OK)**

```json
{
  "status": "OK",
  "agenda_id": 99,
  "created": true
}
```

- `created: true` — a new schedule was created.
- `created: false` — an existing schedule for the same contact and campaign was updated (upsert behavior).

If a qualification with the **Agenda** disposition already exists for the contact, OMniLeads marks it as scheduled (`agendado: true`) when the schedule is saved.

**Common errors**

| Status | Cause |
|--------|-------|
| `400` | Invalid `phone` (not in the contact's phone list) |
| `400` | Invalid `date` or `time` format |
| `400` | `schedule_type: 2` (Global) on a non-dialer campaign |
| `403` | Agent is not assigned to the campaign |
| `404` | Campaign or contact not found |

---

## Complete Example (cURL)

Replace placeholders with your environment values.

```bash
BASE_URL="https://omnileads.example.com"
USERNAME="your_agent_username"
PASSWORD="your_agent_password"
CAMPAIGN_ID=16
CONTACT_ID=10
CALL_ID="1781961848.10"
PHONE="123456746"
SCHEDULE_DATE="2026-06-20"
SCHEDULE_TIME="13:00:00"

# 1. Login
TOKEN=$(curl -sS -X POST "${BASE_URL}/api/v1/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}" \
  | jq -r '.token')

# 2. Get disposition options and find the Agenda ID
AGENDA_ID=$(curl -sS -X GET "${BASE_URL}/api/v1/campaign/${CAMPAIGN_ID}/dispositionOptions/" \
  -H "Authorization: Bearer ${TOKEN}" \
  | jq '[.[] | select(.name == "Agenda")] | .[0].id')

if [ -z "$AGENDA_ID" ] || [ "$AGENDA_ID" = "null" ]; then
  echo "ERROR: Agenda disposition not found for campaign ${CAMPAIGN_ID}"
  exit 1
fi

# 3. Submit Agenda disposition
curl -sS -X POST "${BASE_URL}/api/v1/disposition/" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"idContact\": ${CONTACT_ID},
    \"idDispositionOption\": ${AGENDA_ID},
    \"callid\": \"${CALL_ID}\",
    \"comments\": \"Customer requested a scheduled callback\"
  }"

# 4. Schedule the callback
curl -sS -X POST "${BASE_URL}/api/v1/agenda_contacto/" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"campaign_id\": ${CAMPAIGN_ID},
    \"contact_id\": ${CONTACT_ID},
    \"date\": \"${SCHEDULE_DATE}\",
    \"time\": \"${SCHEDULE_TIME}\",
    \"phone\": \"${PHONE}\",
    \"schedule_type\": 1,
    \"observations\": \"Call tomorrow\"
  }"
```

---

## Integration Checklist

- [ ] Authenticate with agent credentials and cache the Bearer token until expiry.
- [ ] Call `dispositionOptions` for the target campaign and locate the entry with `name == "Agenda"`.
- [ ] Submit `POST /api/v1/disposition/` using the **Agenda** `id` as `idDispositionOption`.
- [ ] Include the active `callid` in the disposition request.
- [ ] Call `POST /api/v1/agenda_contacto/` with a valid `phone` from the contact record.
- [ ] Handle upsert: a second schedule request for the same contact and campaign updates the existing entry.
- [ ] Use `schedule_type: 1` (Personal) unless the campaign is a dialer and a global schedule is intended.

---

## Related Documentation

- [OMniLeads API — Authentication](./API.md#authentication)
- [OMniLeads API — Disposition Options](./API.md#disposition-options)
- [OMniLeads API — Create Contact Schedule](./API.md#create-contact-schedule)
