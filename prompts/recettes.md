# Chaînes d'outils par catégorie (skill-router)

Voici le catalogue des outils branchés sur un agent, rangés par catégorie. Pour chaque catégorie qui a au moins
3 outils, écris la ou les chaînes habituelles : les outils qu'un bon professionnel enchaînerait, dans l'ordre,
pour une demande typique de ce domaine (ex. pour un site web : cadrer la demande, concevoir, construire, vérifier,
mettre en ligne). Une chaîne peut emprunter des outils d'autres catégories (méthode, vérification, déploiement).

Règles :
- 1 à 3 chaînes par catégorie, 3 à 6 étapes chacune, uniquement des ids du catalogue. Une étape peut offrir un choix
  entre outils voisins : "id1|id2" (ex. deux skills de design au style différent).
- Pense aux passes de finition : un outil qui corrige ce que l'agent vient de produire (relecture, passe anti-« fait par IA », test des cas extrêmes) a sa place juste après la construction.
- `quand` : une phrase courte qui dit pour quel genre de demande cette chaîne sert.
- `mots` : 5 à 10 mots-clés (français et anglais, minuscules) qui signalent ce genre de demande.
- Réponds UNIQUEMENT par un objet JSON :
  {"<catégorie>": [{"quand": "...", "mots": ["..."], "chaine": ["id1", "id2", "id3"]}]}
