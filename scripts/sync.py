#!/usr/bin/env python3
"""Hook SessionStart : met l'index à jour avec ce qui est branché, en moins d'une seconde.

- relit les skills, agents, commandes, plugins et serveurs MCP ;
- garde le classement des outils inchangés, marque les nouveaux ou modifiés « à classer » ;
- retire ce qui a été désinstallé ;
- lance en arrière-plan refresh.py (état des MCP + classement des nouveaux) si besoin.

Hors hook : sync.py --now   (tout de suite, en attendant la fin du classement)
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from common import (DATA, DECLARED, INDEX, LOCK, MCP_STATUS, is_child, load, save, save_index)
from inventory import inventory

HERE = Path(__file__).parent
MCP_MAX_AGE = 6 * 3600


def h(it):
    return it.get("hash") or hashlib.sha1((it.get("description", "") + it.get("excerpt", "")).encode()).hexdigest()[:12]


def current_items(cwd):
    items = inventory(cwd)
    status = load(MCP_STATUS, {}).get("serveurs", {})
    by_id = {it["id"]: it for it in items}
    for sid, s in status.items():
        it = by_id.get(sid) or {"id": sid, "kind": "mcp", "name": sid.split(":", 1)[1], "description": "",
                                "path": s.get("adresse", ""), "source": s.get("source", "mcp"), "excerpt": s.get("adresse", "")}
        it["connecte"] = s["connecte"]
        by_id[sid] = it
    for it in load(DECLARED, []):
        by_id.setdefault(it["id"], dict(it, source=it.get("source", "déclaré")))
    for it in by_id.values():
        it["hash"] = h(it)
    return list(by_id.values())


def merge(cwd):
    index = load(INDEX, {"version": 1, "items": []})
    old = {it["id"]: it for it in index["items"]}
    new_items, pending = [], []
    for it in current_items(cwd):
        prev = old.get(it["id"])
        if prev and prev.get("hash") == it["hash"] and prev.get("classe"):
            prev.update({k: it[k] for k in ("path", "source", "description") if it.get(k)})
            prev["connecte"] = it.get("connecte", True)
            prev["present"] = True
            new_items.append(prev)
        else:
            raw = dict(it, classe=False, etiquettes=[], declencheurs=[], voisins=[], phase="transverse",
                       specialite=it.get("description", ""))
            if prev and prev.get("classe"):      # outil modifié : on garde l'ancien classement en attendant
                raw = dict(prev, **{k: it[k] for k in it}, classe=False)
            new_items.append(raw)
            pending.append(it["id"])
    # un outil classé qui n'est pas visible d'ici (skill d'un autre projet) garde son classement, en réserve
    seen = {it["id"] for it in new_items}
    for oid, prev in old.items():
        if oid not in seen and prev.get("classe") and prev.get("kind") != "mcp":
            prev["present"] = False
            new_items.append(prev)
    index["items"] = sorted(new_items, key=lambda x: x["id"])
    index["a_classer"] = pending
    index["maj"] = int(time.time())
    save_index(index)
    return index


def refresh_running():
    try:
        pid, t = LOCK.read_text().split()
        if time.time() - float(t) > 900:
            return False
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def spawn_refresh(cwd):
    if refresh_running():
        return
    DATA.mkdir(parents=True, exist_ok=True)
    log = open(DATA / "refresh.log", "a")
    subprocess.Popen([sys.executable, str(HERE / "refresh.py"), "--cwd", cwd], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True, env=dict(os.environ))


def main():
    if is_child():
        return
    try:
        data = json.load(sys.stdin) if not sys.stdin.isatty() and "--now" not in sys.argv else {}
    except json.JSONDecodeError:
        data = {}
    cwd = data.get("cwd") or os.getcwd()
    index = merge(cwd)
    mcp_age = time.time() - load(MCP_STATUS, {}).get("t", 0)
    if "--now" in sys.argv:
        subprocess.run([sys.executable, str(HERE / "refresh.py"), "--cwd", cwd])
        return
    if index["a_classer"] or mcp_age > MCP_MAX_AGE:
        spawn_refresh(cwd)
    note = index.pop("annonce", None)
    if note:
        save_index(index)
        print(json.dumps({"systemMessage": note}, ensure_ascii=False))


if __name__ == "__main__":
    main()
