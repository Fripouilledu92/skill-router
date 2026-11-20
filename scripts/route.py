#!/usr/bin/env python3
"""Hook UserPromptSubmit : choisit les outils utiles au message, sans appeler de modèle.

Entrée (stdin) : le JSON du hook ({"prompt", "session_id", "cwd", ...}).
Sortie : un court contexte ajouté au message (≈ 60 à 150 tokens), ou rien.

Hors hook : route.py --test "fais-moi un site web"   (affiche le choix et les scores)
"""
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict

from common import (ACKS, INDEX, LAST, PHASES, expand, is_child, load, norm, prefs, save, tokens)

K1 = 1.5
W_NAME, W_TAGS, W_TRIG, W_DESC = 2.0, 3.0, 1.2, 1.0
MIN_SCORE = 5.0      # en dessous, rien n'est proposé
REL_CUT = 0.3        # candidats : au moins 30 % du meilleur score (Claude fait le tri final)
TRIG_BONUS = 8.0     # bonus quand le message ressemble à un déclencheur type
CAT_KEEP = 0.4       # catégories gardées : au moins 40 % du vote de la meilleure
CAT_PENALTY = 0.5    # score des outils hors de ces catégories
GENERIC_CAT = 0.35   # un mot présent dans plus de 35 % des catégories…
GENERIC = 0.4        # …compte 2,5 fois moins


def build(items):
    docs, df, cats = [], Counter(), defaultdict(set)
    for it in items:
        tf = defaultdict(float)
        name = it["name"].replace(":", " ").replace("-", " ")
        for w in tokens(name):
            tf[w] += W_NAME
        for tag in it.get("etiquettes", []):
            for w in tokens(tag):
                tf[w] += W_TAGS
        for t in it.get("declencheurs", []):
            for w in tokens(t):
                tf[w] += W_TRIG
        for w in tokens(it.get("description", "") + " " + it.get("specialite", "")):
            tf[w] += W_DESC
        phrases = [norm(t).strip() for t in it.get("etiquettes", []) if " " in t.strip()]
        names = {norm(it["name"]).strip(), norm(it["name"].split(":")[-1]).strip()}
        trig = [set(tokens(t)) for t in it.get("declencheurs", [])]
        docs.append((it, tf, phrases, names, trig))
        df.update(tf.keys())
        for w in tf:
            cats[w].add(it.get("categorie"))
    return docs, df, cats


def score(prompt, items, p):
    docs, df, cats = build(items)
    ncat = len({it.get("categorie") for it in items}) or 1
    n = len(docs) or 1
    q = set(expand(tokens(prompt)))
    text = " " + norm(prompt) + " "
    out = []
    def idf(w):
        if w not in df:
            return 2.0
        v = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
        return v * GENERIC if len(cats[w]) / ncat > GENERIC_CAT else v   # « app », « page » : partout
    for it, tf, phrases, names, trig in docs:
        s, hits = 0.0, []
        best = 0.0                      # le message ressemble-t-il à un déclencheur type ?
        for t in trig:
            if t:
                best = max(best, sum(idf(w) for w in t & q) / sum(idf(w) for w in t))
        if best >= 0.5:
            s += TRIG_BONUS * best
        for w in q:
            if w in tf:
                s += idf(w) * tf[w] * (K1 + 1) / (tf[w] + K1)
                hits.append(w)
        for ph in phrases:
            if f" {ph} " in text:
                s += 3.0
                hits.append(ph)
        for nm in names:
            if len(nm) > 3 and f" {nm} " in text:   # l'utilisateur nomme l'outil : il le veut
                s += 15.0
                hits.append(nm)
        s *= p["poids"].get(it["id"], 1.0)
        if s > 0:
            out.append((s, it, hits))
    out.sort(key=lambda x: -x[0])
    # vote des catégories : les outils hors des domaines du message passent derrière
    votes = defaultdict(float)
    for s, it, _ in out[:12]:
        votes[it.get("categorie")] += s
    if votes:
        best = max(votes.values())
        keep = {c for c, v in votes.items() if v >= CAT_KEEP * best}
        out = [(s if it.get("categorie") in keep else s * CAT_PENALTY, it, h) for s, it, h in out]
        out.sort(key=lambda x: -x[0])
    return out


def recipe(prompt, picks, recipes):
    """La chaîne habituelle qui colle le mieux : même catégorie que les candidats, mots en commun."""
    if not picks or not recipes:
        return None
    q = set(tokens(prompt))
    cats = defaultdict(float)
    for sc, it, _ in picks:
        cats[it.get("categorie")] += sc
    ids = {it["id"] for _, it, _ in picks}
    top_cat = picks[0][1].get("categorie")
    best, best_sc = None, 0.0
    for cat, chains in recipes.items():
        for ch in chains:
            mots = set(w for m in ch.get("mots", []) for w in tokens(m))
            chain_ids = {x for step in ch["chaine"] for x in step.split("|")}
            sc = len(q & mots) * 2 + len(ids & chain_ids) + (cats.get(cat, 0) > 0) * 2
            common = len(q & mots)
            if (common >= 2 or (common == 1 and cat == top_cat)) and sc > best_sc:
                best, best_sc = dict(ch, categorie=cat), sc
    return best if best_sc >= 4 else None


def choose(prompt, items, p, recipes=None):
    ranked = score(prompt, items, p)
    if not ranked or ranked[0][0] < MIN_SCORE:
        return [], None, ranked
    top = ranked[0][0]
    picks = [r for r in ranked if r[0] >= max(MIN_SCORE, REL_CUT * top)][: p["max"] + 3]
    return picks, recipe(prompt, picks, recipes), ranked


def usable(items, p):
    off = set(p["off"])
    return [it for it in items
            if it["id"] not in off and it.get("connecte", True) and it.get("present", True)]


def skip(prompt):
    s = prompt.strip()
    if not s or s.startswith("/") or s.startswith("<"):
        return True
    low = norm(s).strip(" .!?")
    return low in ACKS or len(tokens(s)) == 0


def short(s, n=95):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def how(it):
    return {"skill": "outil Skill", "agent": "agent", "command": "commande", "mcp": "serveur MCP"}.get(it["kind"], "")


def render(picks, chain, p, items_by_id):
    lines = ["[skill-router] Outils branchés qui peuvent servir ce message (du plus au moins probable) :"]
    ids = {r[1]["id"] for r in picks}
    for _, it, _ in picks:
        lines.append(f"- {it['name']} ({how(it)}, {it.get('phase', '')}) : {short(it.get('specialite') or it.get('description'), 85)}")
    if chain:
        nm = lambda i: items_by_id[i]["name"] if i in items_by_id else i.split(":", 1)[1]
        names = [" ou ".join(nm(i) for i in step.split("|")) for step in chain["chaine"]]
        lines.append(f"Enchaînement habituel ({short(chain['quand'], 70)}) : " + " → ".join(names))
    seen, n = set(), 0
    for _, it, _ in picks:
        for v in it.get("voisins", []):
            pair = frozenset((it["id"], v["id"]))
            if v["id"] in ids and pair not in seen and n < 3:
                seen.add(pair)
                n += 1
                lines.append(f"Nuance {it['name']} / {v['id'].split(':', 1)[1]} : {short(v['nuance'], 150)}")
    if p["langue"].lower().startswith("fr"):
        lines.append(f"Garde ceux qui servent vraiment (souvent 2 à {p['max']}) ; si l'enchaînement colle à la demande, "
                     "suis-le en entier, passes de finition comprises. Ordre : cadrer → concevoir → construire → "
                     "vérifier → livrer (un skill s'ouvre avec l'outil Skill). "
                     "Termine ta réponse par une ligne « Outils : nom (ce qu'il a apporté) · … », "
                     "ou « Outils : aucun, parce que … ».")
    else:
        lines[0] = "[skill-router] Connected tools that may help with this message (most likely first):"
        lines.append(f"Keep the ones that really help (often 2 to {p['max']}); if the usual chain fits the request, "
                     "follow all of it, finishing passes included. Order: frame → design → build → verify → ship "
                     "(open a skill with the Skill tool). "
                     "End your answer with one line \"Tools: name (what it brought) · …\", "
                     "or \"Tools: none, because …\".")
    return "\n".join(lines)


def remember(session, prompt, picks, ranked):
    last = load(LAST, {})
    last[session] = {
        "t": int(time.time()),
        "prompt": prompt[:300],
        "choisis": [{"id": it["id"], "score": round(s, 1), "mots": h[:8]} for s, it, h in picks],
        "ecartes": [{"id": it["id"], "score": round(s, 1), "mots": h[:5]} for s, it, h in ranked[len(picks):len(picks) + 5]],
    }
    if len(last) > 30:
        for k in sorted(last, key=lambda k: last[k]["t"])[:-30]:
            del last[k]
    save(LAST, last)


def main():
    if "--test" in sys.argv:
        prompt = sys.argv[sys.argv.index("--test") + 1]
        p = prefs()
        index = load(INDEX, {})
        items = usable(index.get("items", []), p)
        picks, chain, ranked = choose(prompt, items, p, index.get("recettes"))
        for s, it, h in ranked[:10]:
            mark = "✔" if any(it is x[1] for x in picks) else " "
            print(f"{mark} {s:6.1f}  {it['id']:<45} {', '.join(h[:6])}")
        out = render(picks, chain, p, {i["id"]: i for i in items}) if picks else "(rien proposé)"
        print("---\n" + out + f"\n--- ≈ {len(out) // 4} tokens")
        return
    if is_child():
        return
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    prompt = data.get("prompt", "")
    if skip(prompt):
        return
    index = load(INDEX, None)
    if not index:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
              "[skill-router] Pas encore de classement des outils : propose à l'utilisateur de lancer /skills-sync."}}))
        return
    p = prefs()
    items = usable(index.get("items", []), p)
    picks, chain, ranked = choose(prompt, items, p, index.get("recettes"))
    remember(data.get("session_id", "?"), prompt, picks, ranked)
    if picks:
        ctx = render(picks, chain, p, {i["id"]: i for i in items})
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": ctx}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
