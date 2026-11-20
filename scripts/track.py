#!/usr/bin/env python3
"""Apprentissage. Deux modes de hook :

  track.py use   (PostToolUse) : note l'outil réellement utilisé (skill, agent, serveur MCP).
  track.py learn (Stop)        : compare aux outils proposés pour ce message et ajuste les poids.

Un outil proposé et utilisé monte un peu ; proposé et ignoré, il descend un peu. Bornes 0,5 à 1,5.
"""
import json
import re
import sys
import time

from common import LAST, PREFS, USAGE, is_child, load, prefs, save

UP, DOWN, LO, HI = 0.05, 0.03, 0.5, 1.5


def tool_id(name, inp):
    if name == "Skill":
        s = (inp or {}).get("skill", "")
        return "skill:" + s if s else None
    if name in ("Agent", "Task"):
        a = (inp or {}).get("subagent_type", "")
        return "agent:" + a if a else None
    m = re.match(r"mcp__(.+?)__", name or "")
    if not m:
        return None
    server = m.group(1)
    if re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", server):
        return None                      # connecteur claude.ai : nom illisible, on ne peut pas le relier
    if server.startswith("plugin_"):
        server = server.split("_")[1]
    return "mcp:" + re.sub(r"[^a-z0-9]+", "-", server.lower()).strip("-")


def use(data):
    tid = tool_id(data.get("tool_name"), data.get("tool_input"))
    if tid:
        USAGE.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE, "a") as f:
            f.write(json.dumps({"s": data.get("session_id"), "t": int(time.time()), "id": tid}) + "\n")


def used_since(session, t0):
    out = set()
    try:
        for line in open(USAGE):
            u = json.loads(line)
            if u["s"] == session and u["t"] >= t0:
                out.add(u["id"])
    except (OSError, json.JSONDecodeError):
        pass
    return out


def learn(data):
    session = data.get("session_id")
    last = load(LAST, {})
    route = last.get(session)
    if not route or route.get("appris") or not route.get("choisis"):
        return
    used = used_since(session, route["t"])
    p = prefs()
    for c in route["choisis"]:
        w = p["poids"].get(c["id"], 1.0)
        w = min(HI, w + UP) if c["id"] in used else max(LO, w - DOWN)
        p["poids"][c["id"]] = round(w, 3)
    route["appris"] = True
    route["utilises"] = sorted(used)
    save(LAST, last)
    save(PREFS, p)


def main():
    if is_child() or len(sys.argv) < 2:
        return
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    {"use": use, "learn": learn}.get(sys.argv[1], lambda d: None)(data)


if __name__ == "__main__":
    main()
