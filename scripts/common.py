"""Outils partagés par les scripts de skill-router : chemins, lecture/écriture, texte."""
import json
import os
import re
import unicodedata
from pathlib import Path

DATA = Path(os.environ.get("SKILL_ROUTER_HOME", Path.home() / ".claude" / "skill-router"))
INDEX = DATA / "index.json"          # outils classés
PREFS = DATA / "prefs.json"          # outils coupés, poids appris, réglages
LAST = DATA / "last.json"            # dernier choix par session (pour /why)
USAGE = DATA / "usage.jsonl"         # outils réellement utilisés
MCP_STATUS = DATA / "mcp-status.json"
DECLARED = DATA / "declares.json"    # outils que seul l'agent voit (connecteurs de l'app), déclarés par /skills-sync
LOCK = DATA / "refresh.lock"
CORRECTIONS = DATA / "corrections.json"  # corrections à la main : elles passent toujours devant le classement auto

PHASES = ["cadrer", "concevoir", "construire", "verifier", "livrer", "transverse"]
CHILD_ENV = "SKILL_ROUTER_CHILD"     # posé dans le `claude -p` de classement : les hooks s'y taisent


def is_child():
    return os.environ.get(CHILD_ENV) == "1"


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def apply_corrections(index):
    """Applique corrections.json : {"categories": {ancienne: nouvelle}, "items": {id: {champ: valeur}},
    "recettes": {catégorie: [chaînes]}}. Une chaîne peut proposer un choix : "skill:a|skill:b"."""
    c = load(CORRECTIONS, {})
    ren = c.get("categories", {})
    fix = c.get("items", {})
    for it in index.get("items", []):
        if it.get("categorie") in ren:
            it["categorie"] = ren[it["categorie"]]
        if it["id"] in fix:
            it.update(fix[it["id"]])
            it["corrige"] = True
    rec = index.get("recettes", {})
    for old, new in ren.items():
        if old in rec:
            rec.setdefault(new, []).extend(rec.pop(old))
    rec.update(c.get("recettes", {}))
    if rec:
        index["recettes"] = rec
    return index


def save_index(index):
    save(INDEX, apply_corrections(index))


def prefs():
    p = load(PREFS, {})
    p.setdefault("off", [])
    p.setdefault("poids", {})
    p.setdefault("max", 5)
    p.setdefault("classement_auto", True)
    p.setdefault("modele", "sonnet")
    p.setdefault("langue", "français")
    return p


STOP = set("""
a au aux avec ce ces cette cet c ça ca dans de des du elle en et eux il ils je j la le les leur lui ma mais me
mes moi mon ne nos notre nous on ou où par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos
votre vous y est sont suis es être etre fait fais faire peux peut veux veut voudrais aimerais stp svp merci
moi-même tout tous toute toutes très tres plus moins bien bon bonne juste aussi comme si alors donc là la-bas
genre truc trucs chose choses ducoup du coup après apres avant encore déjà deja
ai as a avons avez ont eu quand ou quoi comment pourquoi combien veuillez peux-tu pourrais-tu mettre met mets va vais vas
the a an and or of to in on for with is are be this that it my me i you your we can could would please
do does make get want need some any all just also from into about how what which
""".split())

ACKS = {"ok", "oui", "non", "merci", "go", "vas-y", "vas y", "continue", "parfait", "super", "top", "d'accord",
        "daccord", "yes", "no", "thanks", "thx", "ok merci", "c'est bon", "cest bon", "nickel", "valide", "ça marche"}


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s):
    s = strip_accents(s.lower())
    s = re.sub(r"[’'`]", " ", s)
    return re.sub(r"[^a-z0-9+#.\- ]+", " ", s)


def stem(w):
    """Racine grossière FR/EN : assez pour que « animations » et « animation » se rejoignent."""
    for suf in ("ements", "ement", "ations", "ation", "ings", "ing", "euses", "euse", "eurs", "eur",
                "ees", "ies", "es", "ee", "ed", "s", "x", "e"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(s):
    return [stem(w) for w in norm(s).replace("-", " ").replace(".", " ").split() if w not in STOP and len(w) > 1]


# Équivalences FR/EN ajoutées au message (pas aux outils) : « relis » trouve aussi « review ».
SYN = {
    "reli": "review relecture", "relir": "review relecture", "relecture": "review", "review": "relecture",
    "pouss": "push commit", "push": "pousser", "commit": "push",
    "utilisateur": "users analytics", "user": "utilisateur analytics", "visiteur": "analytics traffic",
    "statistiqu": "analytics stats", "stat": "analytics", "chiffr": "analytics stats",
    "bug": "debug erreur", "plant": "crash bug", "crash": "plante bug", "erreur": "error bug",
    "site": "website", "websit": "site", "appli": "app application",
    "video": "vidéo", "montag": "edit editing", "sous-titr": "captions subtitles", "titr": "captions",
    "son": "audio sound", "bruitag": "sfx sound effect", "musiqu": "music",
    "deploi": "deploy", "deploy": "déploie", "mettr en lign": "deploy",
    "graphiqu": "chart graph", "courb": "chart", "tableau": "table dashboard",
    "anim": "animation motion", "mouv": "motion animation", "transit": "transition animation",
    "reunion": "meeting", "meeting": "réunion", "mail": "email gmail", "agenda": "calendar",
    "cherch": "search find", "trouv": "find search", "lis": "read", "lir": "read",
    "fonctionn": "bug", "repond": "bug", "bloqu": "bug",
    "lent": "performance slow", "rapid": "performance speed", "charg": "performance load", "fluid": "performance jank",
    "teste": "test", "verifi": "check verify test", "plan": "planning",
}


def expand(words):
    syn = {**SYN, **{stem(k): v for k, v in SYN.items()}}
    out = list(words)
    for w in words:
        if w in syn:
            out += tokens_raw(syn[w])
    return out


def tokens_raw(s):
    return [stem(w) for w in norm(s).replace("-", " ").replace(".", " ").split() if w not in STOP and len(w) > 1]
