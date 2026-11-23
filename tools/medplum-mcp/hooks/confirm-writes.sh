#!/bin/sh
# PreToolUse hook pro nástroje Medplum MCP (medplum-mcp).
# Rozhoduje confirm_writes.py. Když python3 chybí, nespustí se nebo skončí chybou,
# hook žádá potvrzení u každého volání (fail closed). Chybový návratový kód bez výstupu
# by Claude Code bral jako neblokující chybu a zápis by prošel.
HOOK_DIR=${0%/*}
ASK='{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"medplum-mcp: kontrola hooku neproběhla (python3 chybí nebo selhal), typ operace nejde ověřit. Zkontroluj ji a potvrď ručně."}}'
if command -v python3 >/dev/null 2>&1; then
  # Přijme jen jediný řádek: rozhodnutí hooku, nebo "{}" (bez rozhodnutí). Prázdný výstup,
  # banner nebo cokoli jiného znamená, že kontrola neproběhla, a hook se zeptá.
  if out=$(python3 -I "$HOOK_DIR/confirm_writes.py" 2>/dev/null); then
    case "$out" in
      *"
"*) ;;
      '{}') exit 0 ;;
      '{"hookSpecificOutput":'*) printf '%s\n' "$out"; exit 0 ;;
    esac
  fi
  printf '%s\n' "$ASK"
  exit 0
fi
cat >/dev/null
printf '%s\n' "$ASK"
