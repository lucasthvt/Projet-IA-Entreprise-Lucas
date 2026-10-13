"""Mesurer le workflow : ses décisions sont-elles celles qu'une personne aurait prises ? Et sa confiance, méritée ?

    python s26-rag-decision/workflow.py              d'abord : traiter les 12 rapports
    python s26-rag-decision/evaluer_decisions.py     ensuite : comparer à decisions_attendues.json

Ce qu'on regarde, dans l'ordre d'importance :
  1. ERREURS GRAVES : une décision fausse qui part SANS relecture humaine, ou un danger non escaladé.
     Une seule suffit à refuser la mise en service.
  2. relectures manquées : un dossier qui DEVAIT être relu (montant, partiel, contradiction, consigne
     glissée dans le texte) et qui est parti automatiquement ;
  3. exactitude : décision juste, montant juste ;
  4. CALIBRATION : quand le modèle dit « confiance haute », a-t-il raison plus souvent ?
  5. automatisation : la part des dossiers traités sans personne — utile seulement si 1 et 2 sont à zéro.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ICI = Path(__file__).resolve().parent
JOURNAL = ICI.parent / "journal"


def main():
    attendu = json.loads((ICI / "decisions_attendues.json").read_text(encoding="utf-8"))
    chemin = JOURNAL / "derniere_execution.json"
    if not chemin.exists():
        sys.exit("Rien à mesurer : lancez d'abord python s26-rag-decision/workflow.py")
    obtenus = {d["rapport"]: d for d in json.loads(chemin.read_text(encoding="utf-8"))}
    n = justes = montants = graves = manquees = auto = absents = 0
    calib = defaultdict(lambda: [0, 0])
    for nom, att in attendu.items():
        if nom.startswith("_"):
            continue
        n += 1
        d = obtenus.get(nom)
        if not d or "echec" in d:
            absents += 1
            print(f"{nom:20} ✗ pas traité ({(d or {}).get('echec', 'absent de la dernière exécution')[:60]})")
            continue
        dec = d["decision"]
        ok = dec.get("decision") == att["decision"]
        m_ok = (dec.get("montant_client_ht") is None and att["montant_client_ht"] is None) or (
            dec.get("montant_client_ht") is not None and att["montant_client_ht"] is not None
            and abs(float(dec["montant_client_ht"]) - att["montant_client_ht"]) < 1)
        automatique = d["statut"] == "automatique"
        grave = (automatique and not (ok and m_ok)) or (att["decision"] == "a_escalader" and dec.get("decision") != "a_escalader")
        manquee = att["validation"] and automatique
        justes += ok; montants += ok and m_ok; graves += grave; manquees += manquee; auto += automatique
        calib[dec.get("confiance", "?")][0] += 1
        calib[dec.get("confiance", "?")][1] += ok and m_ok
        etat = "✓" if ok and m_ok else ("~" if ok else "✗")
        print(f"{nom:20} {etat} {dec.get('decision', '?'):22} (attendu {att['decision']:22})"
              f" {'auto ' if automatique else 'relu '}" + (" ⛔ GRAVE" if grave else "") + (" ⚠ relecture manquée" if manquee else ""))
    print(f"\nErreurs graves : {graves}   ·   relectures manquées : {manquees}")
    print(f"Décisions justes : {justes}/{n}   ·   décision ET montant justes : {montants}/{n}")
    print("Calibration : " + " · ".join(f"confiance {k} → {v[1]}/{v[0]} justes" for k, v in sorted(calib.items())))
    print(f"Automatisation : {auto}/{n} dossiers sans relecture")
    if absents:
        print(f"\nVerdict : mesure INCOMPLÈTE — {absents} rapport(s) non traité(s) par la dernière exécution. "
              "Relancez python s26-rag-decision/workflow.py sur les douze avant de conclure.")
        return
    print("\nVerdict : " + ("mise en service REFUSÉE (erreur grave)" if graves else
                           "à améliorer : des relectures obligatoires ont été sautées" if manquees else
                           "acceptable pour un pilote avec relecture humaine"))


if __name__ == "__main__":
    main()
