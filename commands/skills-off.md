---
description: Ne plus jamais proposer un outil (ou le rallumer avec "on nom")
argument-hint: <nom de l'outil> | on <nom>
allowed-tools: Bash(python3:*)
---
Arguments : `$ARGUMENTS`
- S'ils commencent par `on `, lance `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/show.py" on <le reste>`.
- Sinon lance `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/show.py" off $ARGUMENTS`.
Dis en une ligne ce qui a changé. Si l'outil est introuvable, lance `show.py map` et propose les noms proches.
