"""L'agent du service client ThermiForez : un modèle de langage + des outils + des garde-fous.

    python s25-agent/agent.py "Quand a eu lieu le dernier entretien chez CL-0101 ?"
    python s25-agent/agent.py --interactif

Le principe (la « boucle d'agent ») :
  1. on envoie au modèle la consigne, la question et la LISTE des outils ;
  2. le modèle répond soit par du texte (fini), soit par une demande d'outil ;
  3. le PROGRAMME — pas le modèle — exécute l'outil, et renvoie le résultat ;
  4. on recommence, au plus ETAPES_MAX fois.

Le modèle ne touche jamais la base : il demande, le programme décide s'il
exécute. Chaque étape laisse une ligne dans journal/agent.jsonl.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
sys.path.insert(0, str(ICI))

import llm      # noqa: E402
import outils   # noqa: E402

ETAPES_MAX = 6
CONSIGNE = (ICI / "consigne_agent.txt").read_text(encoding="utf-8")
JOURNAL = ICI.parent / "journal" / "agent.jsonl"


def _tracer(ligne: dict) -> None:
    JOURNAL.parent.mkdir(exist_ok=True)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps({"quand": time.strftime("%Y-%m-%dT%H:%M:%S"), **ligne}, ensure_ascii=False) + "\n")


def repondre(question: str, *, bavard: bool = False) -> dict:
    """Fait tourner la boucle. Rend {"reponse", "outils" (dans l'ordre), "etapes", "propositions"}."""
    messages = [{"role": "system", "content": CONSIGNE}, {"role": "user", "content": question}]
    utilises, propositions = [], []
    for etape in range(1, ETAPES_MAX + 1):
        m = llm.discuter(messages, sensibilite="personnelle", etape="agent", outils=outils.OUTILS)
        appels = m.get("tool_calls") or []
        if not appels:
            reponse = llm.texte(m)
            _tracer({"question": question[:120], "etape": etape, "fin": True, "longueur": len(reponse)})
            return {"reponse": reponse, "outils": utilises, "etapes": etape, "propositions": propositions}
        # On renvoie au modèle sa propre demande (sans nos métadonnées), puis les résultats.
        messages.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": appels})
        for a in appels:
            nom, args = a["function"]["name"], a["function"].get("arguments") or "{}"
            resultat = outils.executer(nom, args)
            utilises.append(nom)
            if nom == "proposer_rendez_vous" and '"PROPOSITION' in resultat:
                propositions.append(json.loads(resultat))
            _tracer({"question": question[:120], "etape": etape, "outil": nom, "arguments": args,
                     "taille_resultat": len(resultat), "erreur": '"erreur"' in resultat})
            if bavard:
                print(f"  → {nom}({args})", file=sys.stderr)
            messages.append({"role": "tool", "tool_call_id": a.get("id", nom), "name": nom, "content": resultat})
    _tracer({"question": question[:120], "etape": ETAPES_MAX, "fin": False, "motif": "trop d'étapes"})
    return {"reponse": "Je n'ai pas pu terminer : trop d'étapes. Reformulez la demande, ou traitez-la à la main.",
            "outils": utilises, "etapes": ETAPES_MAX, "propositions": propositions}


def valider_propositions(propositions: list[dict]) -> None:
    """L'humain dans la boucle : une proposition n'est retenue que si une personne dit oui."""
    for p in propositions:
        print(f"\nProposition : {p['client']}, {p['date']}, {p['technicien']} — {p['motif']}")
        if input("La valider ? (o/N) ").strip().lower() == "o":
            with open(ICI.parent / "journal" / "rendez_vous_valides.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(p | {"valide_le": time.strftime("%Y-%m-%dT%H:%M:%S"), "valide_par": "assistante"},
                                   ensure_ascii=False) + "\n")
            print("Validée et notée dans journal/rendez_vous_valides.jsonl.")
        else:
            print("Écartée : rien n'est noté.")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] != "--interactif":
        questions = [" ".join(sys.argv[1:])]
    else:
        print("Assistant ThermiForez — une question par ligne, ligne vide pour finir.")
        questions = iter(lambda: input("\n> ").strip(), "")
    for q in questions:
        try:
            r = repondre(q, bavard=True)
        except (llm.RoutageRefuse, llm.ErreurModele) as exc:
            print(f"Refusé ou en échec : {exc}")
            continue
        print(f"\n{r['reponse']}\n\n[{r['etapes']} étape(s) · outils : {', '.join(r['outils']) or 'aucun'}]")
        if r["propositions"]:
            valider_propositions(r["propositions"])


if __name__ == "__main__":
    main()
