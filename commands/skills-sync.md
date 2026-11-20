---
description: Ranger tout de suite les outils ajoutés, y compris les connecteurs que seul l'agent voit
allowed-tools: Bash(python3:*)
---
1. Regarde les outils que TU as dans cette session et que les fichiers ne montrent pas : connecteurs de l'app
   (navigateur intégré, Chrome, simulateur, connecteurs claude.ai), skills fournis par l'app. Pour chacun, prépare
   `{"id": "mcp:<nom>" ou "skill:<nom>", "description": "<ce qu'il fait, une phrase>"}`.
   Déclare-les : `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/show.py" declare '<liste JSON>'`.
   N'y mets aucun secret ni donnée personnelle.
2. Lance `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/sync.py" --now` (état des serveurs MCP puis classement des
   nouveaux outils ; peut prendre quelques minutes).
3. Lance `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/show.py" status` et dis à l'utilisateur ce qui a été rangé.
