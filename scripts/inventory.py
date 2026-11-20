#!/usr/bin/env python3
"""Inventaire de tout ce qui est branché sur l'agent : skills, plugins, agents, commandes, serveurs MCP.

Ne lit que les en-têtes (nom, description) et un court extrait : jamais d'exécution de script.
Sortie : JSON sur stdout, ou dans le fichier passé en argument.

Usage : inventory.py [--cwd DOSSIER] [--out FICHIER]
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE = HOME / ".claude"


def frontmatter(text):
    """Lit l'en-tête YAML simple (clé: valeur, valeurs sur une ligne ou repliées)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        return {}, text
    meta, key = {}, None
    for line in m.group(1).splitlines():
        kv = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val in (">", "|", ">-", "|-"):
                val = ""
            meta[key] = val.strip("'\"")
        elif key and line.startswith((" ", "\t")):
            meta[key] = (meta[key] + " " + line.strip()).strip()
    return meta, text[m.end():]


def excerpt(body, n=600):
    body = re.sub(r"```.*?```", " ", body, flags=re.S)
    body = re.sub(r"\s+", " ", body)
    return body.strip()[:n]


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def item(kind, name, desc, path, source, body=""):
    return {
        "id": f"{kind}:{name}",
        "kind": kind,
        "name": name,
        "description": desc,
        "path": str(path),
        "source": source,
        "excerpt": excerpt(body),
        "hash": hashlib.sha1((desc + body[:4000]).encode()).hexdigest()[:12],
    }


def skills_in(folder, source, prefix=""):
    out = []
    folder = Path(folder)
    if not folder.is_dir():
        return out
    for skill_md in sorted(folder.glob("*/SKILL.md")):
        meta, body = frontmatter(read(skill_md))
        name = skill_md.parent.name  # Claude Code appelle un skill par le nom de son dossier
        out.append(item("skill", prefix + name, meta.get("description", ""), skill_md, source, body))
    return out


def md_entries(folder, kind, source, prefix=""):
    out = []
    folder = Path(folder)
    if not folder.is_dir():
        return out
    for f in sorted(folder.glob("*.md")):
        meta, body = frontmatter(read(f))
        name = meta.get("name") or f.stem
        out.append(item(kind, prefix + name, meta.get("description", ""), f, source, body))
    return out


def plugins():
    """Plugins installés ET activés, à leur version courante seulement (pas les anciennes du cache)."""
    out = []
    reg = CLAUDE / "plugins" / "installed_plugins.json"
    settings = {}
    try:
        settings = json.loads(read(CLAUDE / "settings.json") or "{}")
    except json.JSONDecodeError:
        pass
    enabled = settings.get("enabledPlugins", {})
    try:
        data = json.loads(read(reg) or "{}")
    except json.JSONDecodeError:
        return out
    for key, installs in data.get("plugins", {}).items():
        if enabled and enabled.get(key) is False:
            continue
        plugin = key.split("@")[0]
        if plugin == "skill-router":
            continue
        for inst in installs[-1:]:
            root = Path(inst.get("installPath", ""))
            src = f"plugin:{key}"
            out += skills_in(root / "skills", src, f"{plugin}:")
            out += md_entries(root / "commands", "command", src, f"{plugin}:")
            out += md_entries(root / "agents", "agent", src, f"{plugin}:")
    return out


def mcp_servers(cwd):
    """Serveurs MCP déclarés dans la config. L'état « connecté » est ajouté par sync.py."""
    out, seen = [], set()
    try:
        cfg = json.loads(read(HOME / ".claude.json") or "{}")
    except json.JSONDecodeError:
        cfg = {}
    sources = [("user", cfg.get("mcpServers", {}))]
    proj = cfg.get("projects", {}).get(str(cwd), {})
    sources.append(("project", proj.get("mcpServers", {})))
    mcp_json = Path(cwd) / ".mcp.json"
    if mcp_json.exists():
        try:
            sources.append(("project", json.loads(read(mcp_json)).get("mcpServers", {})))
        except json.JSONDecodeError:
            pass
    for scope, servers in sources:
        for name, conf in servers.items():
            if name in seen:
                continue
            seen.add(name)
            cmd = " ".join([conf.get("command", "")] + conf.get("args", [])) or conf.get("url", "")
            out.append(item("mcp", name, "", f"{scope}-config", f"mcp:{scope}", cmd))
    return out


def inventory(cwd):
    cwd = Path(cwd).resolve()
    items = []
    items += skills_in(CLAUDE / "skills", "user")
    items += md_entries(CLAUDE / "agents", "agent", "user")
    items += md_entries(CLAUDE / "commands", "command", "user")
    # le projet courant et ses parents (Claude Code charge .claude/skills en remontant)
    for d in [cwd, *cwd.parents]:
        if d == HOME or d == Path("/"):
            break
        items += skills_in(d / ".claude" / "skills", f"project:{d.name}")
        items += md_entries(d / ".claude" / "agents", "agent", f"project:{d.name}")
        items += md_entries(d / ".claude" / "commands", "command", f"project:{d.name}")
    items += plugins()
    items += mcp_servers(cwd)
    # un même nom présent à deux endroits : on garde le plus proche (projet > utilisateur)
    by_id = {}
    for it in items:
        if it["id"] in by_id and by_id[it["id"]]["source"].startswith("project"):
            continue
        by_id[it["id"]] = it
    return sorted(by_id.values(), key=lambda x: x["id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--out")
    a = ap.parse_args()
    data = inventory(a.cwd)
    text = json.dumps(data, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"{len(data)} éléments -> {a.out}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
