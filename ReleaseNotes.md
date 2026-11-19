# Release Notes
PRE-2.6.7

## Added

- oml-3475 Outbound Route Trunks can configure a Caller id.
- oml-3489 MOH config for Manual and Preview campaigns.
- oml-3255 Customize premium reports columns selection.

## Changed

- oml-3423 Tests updates for a 2.6.6 hotfix.
- oml-3349 Avoid execution of external commands.
- oml-3277 Dialers ended campaigns list pagination.
- oml-3494 Supervision: bound Redis supervision streams memory and stop sending data of unassigned campaigns and agents.
- oml-3493 Recording file API (/api/v1/grabacion/archivo/) accepts Bearer token authentication.

## Fixed

- oml-3418 Difference between "Pending calls" and "Estimated pending calls".
- oml-3375 Fix Dialer campaigns calls without agents in Asterisk queue.
- oml-3446 Apply recording API's restrictions.
- oml-3451 Background task method Whitelist.
- oml-3440 Use Task Key and User id to save background tasks information in redis to avoid clashes.
- oml-3434 Mandatory app_secret configuration for Meta accounts.
- oml-3450 Private ip restrictions at External Site. Configure SITIO_EXTERNO_ALLOWLIST at Constance. 
- oml-3442 Remove idAgent parameter in Click2CallView.
- oml-3452 WebSockets and Django Endpoints Permission control improved.
- oml-3441 Websocket server connections authentication.
- oml-3006 Limit Users Addon
- oml-3498 Fix node and pnpm versions
- oml-3453 Campaign contacts access control.
- oml-3439 Authenticate internal services with a shared secret (OML_INTERNAL_SECRET) and add login to the Omnidialer Admin.

## Removed

- oml-3439 Remove unauthenticated API endpoint /api/v1/asterisk/queues_data/.

## Migrations

| Version | App                         | Migrations       |
|---------|-----------------------------|------------------|
| 2.6.0   | whatsapp_app                | 0015             |
| 2.6.1   | ominicontacto_app           | 0114, 0115       |
| 2.6.2   | ominicontacto_app           | 0116             |
| 2.6.3   | whatsapp_app                | 0016             |
| 2.6.4   | ominicontacto_app           | 0117             |
|         | facebook_meta_app           | 0001             |
|         | configuracion_telefonia_app | 0024, 0025       |
| 2.6.5   | whatsapp_app                | 0017             |
| 2.6.6   | ominicontacto_app           | 0118, 0119, 0120 |
|         | configuracion_telefonia_app | 0026             |
|         | instagram_app               | 0001             |
|         | email_app                   | 0001             |
|         | facebook_meta_app           | 0002             |
| 2.6.7   | supervision_app             | 0001             |
|         | configuracion_telefonia_app | 0027             |
