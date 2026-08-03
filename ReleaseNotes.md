# Release Notes
PRE-2.6.6

## Added

- oml-3248 Allow SECRET_KEY envar configuration.
- oml-3265 Whatsapp previous client conversation available for Agents.
- oml-3344 Instagram Channel.
- oml-3173 Email Channel.
- oml-3354 Whatsapp Interactive Menu UX Flow in full screen.
- oml-3353 Premium Reports: New metric: Agent response time.

## Changed

- oml-3336 Static code analysis fixes.
- oml-3305 Simplify Campaign Wizard forms references.
- oml-3339 Remove unreachable code.
- oml-3299 Wallboard: UI Dark/Light.
- oml-3300 Survey: UI Dark/Light.
- oml-3298 Premium Reports:  UI Dark/Light.
- oml-3335 Premium Reports: Remove unused functions.
- oml-3346 Premium Reports: Chat center improvements.
- oml-3350 Premium Reports: Chat center Interactive Menu abandons report.
- oml-3338 Exception management improvements.
- oml-3347 Restrict API auth methods.
- oml-3302 Show the telephone used in the call in Disposition Reports.
- oml-3343 Display Whatsapp media messages caption.
- oml-3342 Configure Pause on first login as a Group option.
- oml-3365 Prevent code injections in VueJs frontends.
- oml-3368 Static code issues corrections.

## Fixed

- oml-3262 Dialer: Prevent service crash catching errors at GEARMAN.submit_job.
- oml-3331 Redial dispositioned contact bug when contact is not initially identified.
- oml-3341 Fix Whatsapp transfers to wrong agents.
- oml-3356 Avoid inserting HOLD logs after call ending log.

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
2.6.6
  ominicontacto_app: 0118, 0119, 0120
  configuracion_telefonia_app: 0026
  instagram_app: 0001
  email_app: 0001
