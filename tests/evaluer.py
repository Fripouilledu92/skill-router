#!/usr/bin/env python3
"""Mesure le routeur sur des cas étiquetés : python3 tests/evaluer.py [cas.json]

« doit » : chaque entrée doit figurer parmi les candidats (a|b = l'un des deux suffit).
« jamais » : ne doit pas figurer ; "*" = aucun candidat attendu.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from common import INDEX, load, prefs  # noqa: E402
from route import choose, skip, usable  # noqa: E402

cas = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "cas.json").read_text())
index = load(INDEX, {})
p = prefs()
items = usable(index.get("items", []), p)
ok = 0
for c in cas:
    picks, chain = ([], None) if skip(c["q"]) else choose(c["q"], items, p, index.get("recettes"))[:2]
    ids = [it["id"] for _, it, _ in picks]
    if chain:                       # ce que Claude voit : candidats + enchaînement
        ids += [x for step in chain["chaine"] for x in step.split("|") if x not in ids]
    fails = [d for d in c["doit"] if not any(x in ids for x in d.split("|"))]
    bad = (["(des candidats)"] if ids else []) if c["jamais"] == ["*"] else [j for j in c["jamais"] if j in ids]
    good = not fails and not bad
    ok += good
    print(f"{'OK ' if good else 'NON'} {c['q'][:55]:<55} manque={fails} en_trop={bad}" + ("" if good else f"\n      -> {ids}"))
print(f"\n{ok}/{len(cas)} cas réussis")
