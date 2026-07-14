# Release Notes
260601.01

## Added

- oml-3291 Whatsapp interactive Menu Flow.
- oml-3320 Whatsapp Webhook Signature Validation.
- oml-3323 Recording search task status notification.

## Changed

- oml-3303 Adds indexes in model definition to avoid problems migration.
- oml-3312 New "Out of time" policies for Whatsapp.
- oml-3313 Support campaign transfer events in reports.
- oml-3321 Signature Validation for Whatsapp outbound attachment media.
- oml-3278 Supervisor's message to agent notification window improved.
- oml-3328 Quick Whatsapp Interactive Menu conversations expiry. 
- oml-3322 Premium Reports: optimizations, task status notification and logging.
- oml-3330 New Registration Server.

## Fixed

- oml-3296 Fix Whatsapp stream log too long.
- oml-3317 Fix Race conditions between Requests in Conversation UI.
- oml-3311 Avoid regenerar_asterisk command error for inconsistent campaign database data. 
- oml-3314 Optimize preview contact update and fix distribution algorithm.
- oml-3327 Fix Campaign Wizard: Show configured form name in disabled option.
- oml-3334 Premium Reports: Fix Agent on Hold time. 

## Removed

- No removals in this release.

## Migrations

2.6.0 whatsapp_app: 0015
2.6.1 ominicontacto_app: 0114, 0115
2.6.2 ominicontacto_app: 0116
2.6.3 whatsapp_app: 0016
2.6.4 ominicontacto_app: 0117
      facebook_meta_app: 0001
      configuracion_telefonia_app: 0024, 0025
2.6.5 whatsapp_app: 0017
