# 0011 - Code-level interface language catalog

## Status

Accepted

## Context

The app needed Portuguese UI copy while keeping the English version available.
There is no user-facing settings use case yet, and the requested language switch
is a variable that appears only inside the code.

Learn and Sandbox already keep their practice and audio rules outside the Qt
views. Localization should not make those policies depend on presentation text.

## Decision

Interface copy lives in `interfaces/i18n.py`, selected by `APP_LANGUAGE`.
Qt adapters request text by stable catalog keys. Domain enums and detector
states remain unchanged and are mapped to localized labels only at the UI edge.

## Discarded Options

- Runtime language selector: discarded because product settings do not exist
  yet, and adding that workflow would create unused state and persistence
  decisions.
- Translating domain enum values directly: discarded because controller tests
  and state machines should keep stable policy vocabulary independent from UI
  language.
- Environment variable language selection: discarded because the requested
  switch is explicit code-level configuration, not deployment configuration.

## Open Questions

Play mode still contains English UI text, but it is currently disabled from the
main menu. It should be localized when the Play GUI becomes an operational entry
point again.

