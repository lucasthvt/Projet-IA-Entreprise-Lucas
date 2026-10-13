"""L'humain dans la boucle : relire la file des décisions à valider.

    python s26-rag-decision/valider.py

Pour chaque dossier en attente : ce que l'outil propose, pourquoi il faut le relire, les
sources citées. Vous acceptez, corrigez ou refusez ; votre décision est tracée dans
journal/validations.jsonl avec votre nom et l'heure (charte IA, point 4).
"""
import json
import time
from pathlib import Path

JOURNAL = Path(__file__).resolve().parent.parent / "journal"
DECISIONS = ["couvert_contrat", "garantie_constructeur", "partiellement_couvert", "facturable", "a_escalader", "incomplet"]


def main():
    file = JOURNAL / "file_validation.jsonl"
    deja = set()
    if (JOURNAL / "validations.jsonl").exists():
        deja = {json.loads(l)["rapport"] for l in (JOURNAL / "validations.jsonl").read_text(encoding="utf-8").splitlines() if l}
    attente = [json.loads(l) for l in file.read_text(encoding="utf-8").splitlines() if l] if file.exists() else []
    attente = list({d["rapport"]: d for d in attente if d["rapport"] not in deja}.values())
    if not attente:
        print("Aucun dossier en attente.")
        return
    qui = input("Votre nom (il sera tracé) : ").strip() or "anonyme"
    for d in attente:
        dc = d["decision"]
        print("\n" + "─" * 70 + f"\n{d['rapport']} — client {d['code_client']}")
        print(f"Proposé : {dc.get('decision')} · {dc.get('montant_client_ht')} € HT · confiance {dc.get('confiance')}")
        print(f"Justification : {dc.get('justification')}")
        print(f"Sources : {', '.join(dc.get('sources') or []) or 'aucune'}")
        print("À relire parce que : " + " ; ".join(d["validation"]["raisons"]))
        for p in dc.get("points_a_verifier") or []:
            print(f"  · à vérifier : {p}")
        choix = input("[a]ccepter, [c]orriger, [r]efuser, [p]asser ? ").strip().lower()[:1]
        if choix not in ("a", "c", "r"):
            continue
        ligne = {"rapport": d["rapport"], "propose": dc, "action": {"a": "acceptée", "c": "corrigée", "r": "refusée"}[choix],
                 "valide_par": qui, "valide_le": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if choix == "c":
            ligne["decision_finale"] = input(f"Décision ({', '.join(DECISIONS)}) : ").strip()
            ligne["montant_final_ht"] = input("Montant client HT (vide si aucun) : ").strip() or None
            ligne["motif"] = input("Pourquoi corriger ? ").strip()
        elif choix == "r":
            ligne["motif"] = input("Pourquoi refuser ? ").strip()
        with open(JOURNAL / "validations.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        print("Tracé dans journal/validations.jsonl.")


if __name__ == "__main__":
    main()
