---
description: Pourquoi ces outils ont été choisis pour le dernier message
allowed-tools: Bash(python3:*)
---
Lance `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/show.py" why` et explique le résultat à l'utilisateur, simplement :
pour chaque outil choisi, ce qui l'a fait choisir (les mots du message), ce qu'il apporte, et pourquoi lui plutôt
que ses voisins. Dis aussi lesquels ont été réellement utilisés, et ceux écartés de justesse. Court, sans jargon.
