#!/bin/sh
# PreToolUse hook pro fhir-request (medplum-mcp).
# GET projde běžným schvalováním Claude Code, každá jiná metoda vyžaduje potvrzení.
# Bez python3 hook vstup neověří, a proto žádá potvrzení u každého volání (fail closed).
HOOK_DIR=${0%/*}
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$HOOK_DIR/confirm_writes.py"
fi
cat >/dev/null
printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"medplum-mcp: python3 není k dispozici, typ operace nejde ověřit. Zkontroluj ji a potvrď ručně."}}'
