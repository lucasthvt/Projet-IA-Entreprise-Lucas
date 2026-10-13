"""llm.py — le seul endroit du projet qui parle à un modèle de langage.

Toutes les étapes (l'agent, le RAG, le workflow) passent par ici. C'est ce qui
permet d'appliquer partout les mêmes règles :

  • UN DIALECTE : l'API « chat completions » (celle d'OpenAI), que parlent
    Ollama, OVHcloud, GitHub Models, Groq, Mistral et Google. Changer de
    fournisseur = changer une ligne de .env.
  • UN ROUTEUR SOUVERAIN : chaque appel dit quelle SENSIBILITÉ de données il
    transporte (publique, interne, personnelle). La table ROUTAGE dit quels
    fournisseurs ont le droit de les recevoir. Un appel interdit est REFUSÉ
    avant de partir, et le refus est journalisé.
  • UN JOURNAL : chaque appel laisse une ligne dans journal/appels.jsonl —
    quand, quel fournisseur, quel modèle, quelle sensibilité, combien de temps,
    combien de jetons. Jamais le contenu : le journal ne doit pas devenir une
    copie des données clients.

    python llm.py                       essai rapide avec le fournisseur de .env
    python llm.py ovh                   essai avec OVHcloud (sans compte)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

RACINE = Path(__file__).parent
JOURNAL = RACINE / "journal"

# ── .env, lu à la main (aucune dépendance de plus) ─────────────────────────────
_env = RACINE / ".env"
if _env.exists():
    for _l in _env.read_text(encoding="utf-8").splitlines():
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")

# ── Les fournisseurs (conditions relevées le 12/10/2026 : à revérifier) ───────
FOURNISSEURS: dict[str, dict] = {
    "ollama":  {"url": f"{OLLAMA_URL}/v1", "modele": "qwen2.5:7b", "vecteurs": "bge-m3",
                "zone": "local", "cle": False},
    "ovh":     {"url": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
                "modele": "gpt-oss-120b", "vecteurs": "bge-m3",
                "zone": "UE, sans entraînement", "cle": False},
    "github":  {"url": "https://models.github.ai/inference", "modele": "openai/gpt-4o-mini",
                "vecteurs": "openai/text-embedding-3-small", "zone": "hors UE", "cle": True},
    "groq":    {"url": "https://api.groq.com/openai/v1", "modele": "openai/gpt-oss-20b",
                "vecteurs": None, "zone": "hors UE", "cle": True},
    "mistral": {"url": "https://api.mistral.ai/v1", "modele": "mistral-small-latest",
                "vecteurs": "mistral-embed", "zone": "UE, entraînement possible (offre gratuite)", "cle": True},
    "google":  {"url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "modele": "gemini-2.5-flash", "vecteurs": "gemini-embedding-001",
                "zone": "hors UE", "cle": True},
}

# ── La politique : qui a le droit de recevoir quoi ─────────────────────────────
# Elle traduit la charte IA de ThermiForez (donnees/documents/charte-ia.md, points 1 et 2).
ROUTAGE: dict[str, set[str]] = {
    "publique":    set(FOURNISSEURS),            # tarifs, FAQ, réglementation
    "interne":     {"ollama", "ovh"},            # conditions, procédures, rapports pseudonymisés
    "personnelle": {"ollama", "ovh"},            # noms, adresses, téléphones des clients
}
# En vrai, « personnelle » chez OVHcloud exigerait en plus un contrat de sous-traitance
# RGPD signé. Ici, les données sont fictives : on l'accepte pour que chacun puisse
# travailler, même sans carte graphique.

FOURNISSEUR = os.getenv("FOURNISSEUR", "ovh").strip().lower()
MODELE = os.getenv("MODELE", "").strip()
CLE_API = os.getenv("CLE_API", "").strip()
# Prototype sur données FICTIVES : on peut autoriser un fournisseur hors politique,
# en le sachant. Chaque appel concerné est marqué « derogation » au journal.
DONNEES_FICTIVES = os.getenv("DONNEES_FICTIVES", "non").strip().lower() in ("oui", "1", "true")


def _cle(nom: str) -> str:
    """La clé d'un fournisseur : CLE_<NOM> si elle existe, sinon CLE_API pour le fournisseur
    principal. Jamais la clé d'un fournisseur envoyée à un autre."""
    return os.getenv(f"CLE_{nom.upper()}", "").strip() or (CLE_API if nom == FOURNISSEUR else "")


class RoutageRefuse(Exception):
    """La politique interdit d'envoyer ces données à ce fournisseur."""


class ErreurModele(Exception):
    """Le fournisseur n'a pas répondu correctement (réseau, clé, quota, modèle)."""


def _fournisseur(nom: str | None = None) -> tuple[str, dict, str]:
    nom = (nom or FOURNISSEUR).lower()
    if nom not in FOURNISSEURS:
        raise ErreurModele(f"FOURNISSEUR={nom!r} inconnu. Choix : {', '.join(FOURNISSEURS)}")
    f = FOURNISSEURS[nom]
    modele = MODELE if (MODELE and nom == FOURNISSEUR) else f["modele"]
    if nom != "ollama" and ":" in modele:
        raise ErreurModele(f"MODELE={modele!r} est un nom de modèle Ollama : videz MODELE dans .env.")
    if f["cle"] and not _cle(nom):
        raise ErreurModele(f"{nom} demande une clé : CLE_API=… (ou CLE_{nom.upper()}=…) dans .env.")
    return nom, f, modele


def verifier_routage(sensibilite: str, nom: str | None = None) -> str:
    """Rend 'ok' ou 'derogation', ou lève RoutageRefuse. Appelée AVANT tout envoi."""
    nom = (nom or FOURNISSEUR).lower()
    if sensibilite not in ROUTAGE:
        raise RoutageRefuse(f"Sensibilité inconnue : {sensibilite!r} (publique, interne, personnelle).")
    if nom in ROUTAGE[sensibilite]:
        return "ok"
    if DONNEES_FICTIVES:
        return "derogation"
    raise RoutageRefuse(
        f"Données « {sensibilite} » interdites vers {nom} ({FOURNISSEURS.get(nom, {}).get('zone', '?')}). "
        f"Autorisés : {', '.join(sorted(ROUTAGE[sensibilite]))}. "
        "Pour un prototype sur données fictives seulement : DONNEES_FICTIVES=oui dans .env.")


def _journaliser(ligne: dict) -> None:
    JOURNAL.mkdir(exist_ok=True)
    ligne = {"quand": time.strftime("%Y-%m-%dT%H:%M:%S"), **ligne}
    with open(JOURNAL / "appels.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def _empreinte(obj) -> str:
    """Une empreinte du contenu : permet de rapprocher deux appels sans stocker le texte."""
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def _post(nom: str, chemin: str, corps: dict, delai: float, essais: int = 4) -> dict:
    f = FOURNISSEURS[nom]
    entetes = {"Content-Type": "application/json"}
    if _cle(nom) and nom != "ollama":
        entetes["Authorization"] = f"Bearer {_cle(nom)}"
    for essai in range(1, essais + 1):
        try:
            r = httpx.post(f"{f['url']}{chemin}", json=corps, headers=entetes, timeout=delai)
        except httpx.HTTPError as exc:
            raise ErreurModele(f"injoignable : {exc}") from exc
        if r.status_code == 429 and essai < essais:
            attente = min(float(r.headers.get("retry-after", 0) or 0) or 15 * essai, 40)
            print(f"   … quota du fournisseur atteint, nouvel essai dans {attente:.0f} s", file=sys.stderr)
            time.sleep(attente)
            continue
        if r.status_code >= 400:
            raise ErreurModele(f"HTTP {r.status_code} : {r.text[:300]}")
        return r.json()
    raise ErreurModele("quota atteint (429) après plusieurs essais : attendez, ou changez de fournisseur")


def discuter(messages: list[dict], *, sensibilite: str, etape: str = "?",
             outils: list[dict] | None = None, json_attendu: bool = False,
             temperature: float = 0.1, fournisseur: str | None = None,
             delai: float = 180) -> dict:
    """Un tour de conversation. Rend le message de l'assistant (dict : content, tool_calls…)
    et ajoute '_meta' (fournisseur, modèle, durée, jetons).

    sensibilite : 'publique' | 'interne' | 'personnelle' — OBLIGATOIRE, c'est elle qui décide.
    etape       : le nom de l'étape qui appelle (pour le journal).
    """
    nom, f, modele = _fournisseur(fournisseur)
    try:
        statut = verifier_routage(sensibilite, nom)
    except RoutageRefuse as exc:
        _journaliser({"etape": etape, "fournisseur": nom, "sensibilite": sensibilite,
                      "routage": "refuse", "motif": str(exc)[:200]})
        raise
    corps = {"model": modele, "messages": messages, "temperature": temperature}
    if outils:
        corps["tools"] = outils
    if json_attendu:
        corps["response_format"] = {"type": "json_object"}
    debut = time.perf_counter()
    try:
        d = _post(nom, "/chat/completions", corps, delai)
    except ErreurModele as exc:
        _journaliser({"etape": etape, "fournisseur": nom, "modele": modele, "sensibilite": sensibilite,
                      "routage": statut, "erreur": str(exc)[:200]})
        raise ErreurModele(f"{nom} : {exc}") from exc
    duree = round(time.perf_counter() - debut, 2)
    message = (d.get("choices") or [{}])[0].get("message", {}) or {}
    usage = d.get("usage") or {}
    _journaliser({"etape": etape, "fournisseur": nom, "modele": modele, "sensibilite": sensibilite,
                  "routage": statut, "duree_s": duree,
                  "jetons_entree": usage.get("prompt_tokens"), "jetons_sortie": usage.get("completion_tokens"),
                  "outils_demandes": [t["function"]["name"] for t in message.get("tool_calls") or []],
                  "empreinte": _empreinte(messages)})
    message["_meta"] = {"fournisseur": nom, "modele": modele, "duree_s": duree, "routage": statut}
    return message


def vecteurs(textes: list[str], *, sensibilite: str, fournisseur: str | None = None) -> list[list[float]]:
    """Les plongements (embeddings) d'une liste de textes, en un seul appel.
    Fournisseur : FOURNISSEUR_VECTEURS dans .env s'il est donné, sinon FOURNISSEUR."""
    nom, f, _ = _fournisseur(fournisseur or os.getenv("FOURNISSEUR_VECTEURS") or None)
    if not f["vecteurs"]:
        raise ErreurModele(f"{nom} ne propose pas de plongements : utilisez le mode « motscles », "
                           "ou FOURNISSEUR_VECTEURS=ovh dans .env.")
    statut = verifier_routage(sensibilite, nom)
    debut = time.perf_counter()
    d = _post(nom, "/embeddings", {"model": f["vecteurs"], "input": textes}, 300)
    _journaliser({"etape": "vecteurs", "fournisseur": nom, "modele": f["vecteurs"], "sensibilite": sensibilite,
                  "routage": statut, "duree_s": round(time.perf_counter() - debut, 2), "textes": len(textes)})
    return [x["embedding"] for x in sorted(d["data"], key=lambda x: x["index"])]


def texte(message: dict) -> str:
    """Le texte d'une réponse, sans le raisonnement que certains modèles mettent entre <think>…</think>."""
    t = message.get("content") or ""
    if "</think>" in t:
        t = t.split("</think>", 1)[1]
    return t.strip()


if __name__ == "__main__":
    choix = sys.argv[1] if len(sys.argv) > 1 else None
    nom, f, modele = _fournisseur(choix)
    print(f"Fournisseur : {nom} · modèle : {modele} · zone : {f['zone']}")
    for s in ROUTAGE:
        try:
            print(f"  données {s:<11} : {verifier_routage(s, nom)}")
        except RoutageRefuse:
            print(f"  données {s:<11} : REFUSÉ")
    m = discuter([{"role": "user", "content": "En une phrase : qu'est-ce qu'un contrat d'entretien de chaudière ?"}],
                 sensibilite="publique", etape="essai", fournisseur=choix)
    print("\n" + texte(m) + f"\n\n({m['_meta']['duree_s']} s — une ligne de plus dans journal/appels.jsonl)")
