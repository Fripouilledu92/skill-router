#!/usr/bin/env python3
"""Ce que montrent les commandes du plugin.

  show.py why [session_id]        : pourquoi ces outils au dernier message
  show.py map                     : la boîte à outils rangée par catégories
  show.py off <id|nom> / on <id|nom> : couper ou rallumer un outil
  show.py declare '<json>'        : ajouter des outils que seul l'agent voit (connecteurs de l'app)
  show.py status                  : état de l'index
"""
import json
import sys
from collections import defaultdict

from common import DECLARED, INDEX, LAST, PREFS, load, prefs, save


def find(items, q):
    q = q.strip().lower()
    for it in items:
        if q in (it["id"].lower(), it["name"].lower(), it["name"].split(":")[-1].lower()):
            return it
    return None


def why(session=None):
    last = load(LAST, {})
    if not last:
        print("Aucun choix enregistré pour l'instant.")
        return
    key = session if session in last else max(last, key=lambda k: last[k]["t"])
    r = last[key]
    items = {it["id"]: it for it in load(INDEX, {}).get("items", [])}
    print(f"Message : « {r['prompt'][:200]} »\n")
    if not r["choisis"]:
        print("Aucun outil proposé : aucun ne correspondait assez à ce message.")
    else:
        print("Proposés à l'agent (il garde ceux qui servent) :\n")
    for c in r["choisis"]:
        it = items.get(c["id"], {})
        print(f"## {c['id']}  (score {c['score']}, phase {it.get('phase', '?')})")
        print(f"- Mots qui l'ont fait choisir : {', '.join(c['mots']) or '?'}")
        print(f"- Ce qu'il apporte : {it.get('specialite', '')}")
        for v in it.get("voisins", []):
            print(f"- Plutôt que {v['id']} : {v['nuance']}")
        print()
    if r.get("ecartes"):
        print("Écartés de justesse (pas proposés) : " + ", ".join(f"{e['id']} ({e['score']})" for e in r["ecartes"]))
    if r.get("utilises") is not None:
        print("Réellement utilisés : " + (", ".join(r["utilises"]) or "aucun"))


def tool_map():
    index = load(INDEX, {})
    p = prefs()
    groups = defaultdict(list)
    for it in index.get("items", []):
        if it.get("present") is False:
            groups["(absents d'ici : skills d'un autre projet, gardés en réserve)"].append(it)
        elif it.get("connecte") is False:
            groups["(serveurs MCP non connectés : ignorés)"].append(it)
        elif not it.get("classe"):
            groups["(pas encore classés)"].append(it)
        else:
            groups[it.get("categorie", "?")].append(it)
    total = sum(len(v) for v in groups.values())
    print(f"# Boîte à outils : {total} outils\n")
    for cat in sorted(groups, key=lambda c: (c.startswith("("), c)):
        print(f"## {cat} ({len(groups[cat])})")
        for it in sorted(groups[cat], key=lambda x: x["name"]):
            flag = " [coupé]" if it["id"] in p["off"] else ""
            flag += f" [alerte : {it['alerte']}]" if it.get("alerte") else ""
            w = p["poids"].get(it["id"])
            flag += f" [poids {w}]" if w and w != 1.0 else ""
            print(f"- **{it['name']}** ({it['kind']}){flag} : {it.get('specialite') or it.get('description', '')[:120]}")
        print()


def toggle(q, off):
    items = load(INDEX, {}).get("items", [])
    it = find(items, q)
    if not it:
        print(f"Introuvable : {q}")
        return
    p = prefs()
    s = set(p["off"])
    (s.add if off else s.discard)(it["id"])
    p["off"] = sorted(s)
    save(PREFS, p)
    print(f"{it['id']} : {'coupé, ne sera plus proposé' if off else 'rallumé'}")


def declare(raw):
    new = json.loads(raw)
    cur = {it["id"]: it for it in load(DECLARED, [])}
    for it in new:
        it.setdefault("kind", it["id"].split(":")[0])
        it.setdefault("name", it["id"].split(":", 1)[1])
        it.setdefault("source", "déclaré par l'agent")
        cur[it["id"]] = it
    save(DECLARED, sorted(cur.values(), key=lambda x: x["id"]))
    print(f"{len(new)} outil(s) déclaré(s). Ils seront classés à la prochaine synchro.")


def status():
    index = load(INDEX, {})
    items = index.get("items", [])
    print(f"{len(items)} outils, {sum(1 for i in items if i.get('classe'))} classés, "
          f"{len(index.get('a_classer', []))} à classer, {len(prefs()['off'])} coupés.")


if __name__ == "__main__":
    a = sys.argv[1:] or ["status"]
    cmd = a[0]
    if cmd == "why":
        why(a[1] if len(a) > 1 else None)
    elif cmd == "map":
        tool_map()
    elif cmd in ("off", "on") and len(a) > 1:
        toggle(" ".join(a[1:]), cmd == "off")
    elif cmd == "declare" and len(a) > 1:
        declare(a[1])
    else:
        status()
