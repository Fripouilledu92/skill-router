#!/usr/bin/env python3
"""Travail de fond, lancé par sync.py : état des serveurs MCP, puis classement des outils nouveaux.

Le classement passe par `claude -p` (le compte de l'utilisateur, une seule fois par outil ajouté).
Les hooks de ce `claude -p` se taisent grâce à SKILL_ROUTER_CHILD=1.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from common import CHILD_ENV, INDEX, LOCK, MCP_STATUS, PHASES, load, prefs, save, save_index
import sync

HERE = Path(__file__).parent
PROMPT = HERE.parent / "prompts" / "classer.md"
BATCH = 12
CATS = [l.strip("- ").strip() for l in PROMPT.read_text().split("## Catégories")[1].split("##")[0].splitlines()
        if l.strip().startswith("-")] if PROMPT.exists() else []

LINE = re.compile(r"^(?P<name>.+?): (?P<addr>.*) - (?P<state>✔ Connected|✓ Connected|! .*|✗ .*)$")


def mcp_id(name):
    name = name.strip()
    if name.startswith("claude.ai "):
        name = name[len("claude.ai "):]
    if name.startswith("plugin:"):
        name = name.split(":")[1]
    return "mcp:" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def child_env():
    env = dict(os.environ)
    env[CHILD_ENV] = "1"
    return env


def mcp_status():
    try:
        out = subprocess.run(["claude", "mcp", "list"], capture_output=True, text=True, timeout=120,
                             env=child_env()).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        print("mcp list impossible :", e)
        return
    servers = {}
    for line in out.splitlines():
        m = LINE.match(line.strip())
        if m:
            src = "connecteur claude.ai" if line.startswith("claude.ai ") else "mcp"
            servers[mcp_id(m["name"])] = {"nom": m["name"], "adresse": m["addr"][:200], "source": src,
                                          "connecte": "Connected" in m["state"]}
    if servers:
        save(MCP_STATUS, {"t": int(time.time()), "serveurs": servers})
        print(f"{sum(s['connecte'] for s in servers.values())}/{len(servers)} serveurs MCP connectés")


def ask_claude(items, catalog):
    consigne = f"Langue de sortie : {prefs()['langue']}\n\n" + PROMPT.read_text()
    payload = [{k: it.get(k, "") for k in ("id", "kind", "name", "description", "path", "excerpt")} for it in items]
    prompt = (consigne + "\n\n## Outils à classer\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=1)
              + "\n```\n\n## Outils déjà classés (pour les voisins)\n"
              + "\n".join(f"- {c['id']} [{c.get('categorie', '')}] {c.get('specialite', '')[:110]}" for c in catalog)
              + "\n\nRéponds UNIQUEMENT par la liste JSON, sans texte autour.")
    r = subprocess.run(["claude", "-p", prompt, "--model", prefs()["modele"], "--allowedTools", "Read",
                        "--output-format", "text"], capture_output=True, text=True, timeout=900,
                       env=child_env(), cwd=str(Path.home()))
    m = re.search(r"\[.*\]", r.stdout, re.S)
    if not m:
        raise ValueError("pas de JSON dans la réponse : " + r.stdout[:300] + r.stderr[:300])
    return json.loads(m.group(0))


def make_recipes(index):
    """Chaînes habituelles par catégorie, refaites quand des outils ont été rangés."""
    catalog = [it for it in index["items"] if it.get("classe") and it.get("connecte", True)]
    text = (f"Langue de sortie : {prefs()['langue']}\n\n" + (HERE.parent / "prompts" / "recettes.md").read_text()
            + "\n\n## Catalogue\n" + "\n".join(
                f"- {c['id']} [{c.get('categorie')}] ({c.get('phase')}) {c.get('specialite', '')[:100]}" for c in catalog))
    r = subprocess.run(["claude", "-p", text, "--model", prefs()["modele"], "--output-format", "text"],
                       capture_output=True, text=True, timeout=900, env=child_env(), cwd=str(Path.home()))
    m = re.search(r"\{.*\}", r.stdout, re.S)
    if not m:
        print("recettes ratées :", r.stdout[:300], r.stderr[:300])
        return
    known = {c["id"] for c in catalog}
    out = {}
    for cat, chains in json.loads(m.group(0)).items():
        good = []
        for ch in chains if isinstance(chains, list) else []:
            ids = [i for i in ch.get("chaine", []) if all(x in known for x in i.split("|"))]
            if len(ids) >= 2:
                good.append({"quand": ch.get("quand", ""), "mots": ch.get("mots", [])[:12], "chaine": ids[:6]})
        if good:
            out[cat] = good
    index = load(INDEX, index)
    index["recettes"] = out
    save_index(index)
    print(f"recettes : {sum(len(v) for v in out.values())} chaînes dans {len(out)} catégories")


def valid(c, known):
    ok = (isinstance(c, dict) and c.get("id") in known and c.get("phase") in PHASES
          and isinstance(c.get("etiquettes"), list) and len(c["etiquettes"]) >= 3)
    if ok:
        if CATS and c.get("categorie") not in CATS:
            c["categorie"] = "Outillage de l'agent"
        c["voisins"] = [v for v in c.get("voisins", []) if isinstance(v, dict) and v.get("id") in known][:4]
    return ok


def classify(cwd):
    index = sync.merge(cwd)
    todo = [it for it in index["items"] if it["id"] in set(index["a_classer"])]
    if not prefs()["classement_auto"]:
        return
    if not todo:
        todo = []
    known = {it["id"] for it in index["items"]}
    catalog = [it for it in index["items"] if it.get("classe")]
    done = []
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            result = ask_claude(batch, catalog)
        except Exception as e:  # noqa: BLE001 — un lot raté sera repris à la prochaine session
            print("classement raté :", e)
            continue
        got = {c["id"]: c for c in result if valid(c, known)}
        index = load(INDEX, index)
        for it in index["items"]:
            if it["id"] in got:
                c = got[it["id"]]
                it.update({k: c.get(k) for k in ("categorie", "etiquettes", "specialite", "voisins", "phase",
                                                  "declencheurs", "eviter_si", "cout", "alerte")})
                it["classe"] = True
                done.append(it["name"])
        index["a_classer"] = [x for x in index["a_classer"] if x not in got]
        save_index(index)
    if done:
        index = load(INDEX, index)
        noms = ", ".join(done[:6]) + (" …" if len(done) > 6 else "")
        index["annonce"] = f"skill-router : {len(done)} nouvel(s) outil(s) rangé(s) : {noms}"
        save_index(index)
        print(index["annonce"])
    index = load(INDEX, index)
    if (done or "recettes" not in index or "--recettes" in sys.argv) and not index.get("a_classer"):
        make_recipes(index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--recettes", action="store_true")
    a = ap.parse_args()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(f"{os.getpid()} {time.time()}")
    try:
        print(time.strftime("%Y-%m-%d %H:%M"), "refresh")
        mcp_status()
        classify(a.cwd)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
