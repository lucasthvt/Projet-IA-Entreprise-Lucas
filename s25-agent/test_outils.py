"""Vérifier les outils SANS modèle : ils doivent être justes avant qu'un agent s'en serve.

    python s25-agent/test_outils.py

Chaque ligne dit ce qu'elle vérifie. Les deux outils de la mission 3 échouent
tant qu'ils ne sont pas écrits : c'est normal.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outils  # noqa: E402

resultats = []


def verifier(libelle, fonction):
    try:
        ok = fonction()
    except Exception as exc:  # noqa: BLE001
        ok, libelle = False, f"{libelle} — {type(exc).__name__} : {exc}"
    resultats.append(ok)
    print(("✓ " if ok else "✗ ") + libelle)


def ecrire_est_impossible():
    try:
        with outils.connexion() as db:
            db.execute("delete from interventions where statut = 'annulée'")
        return False
    except sqlite3.OperationalError:
        return True


verifier("la base est ouverte en lecture seule", ecrire_est_impossible)
verifier("chercher_client('Martin') rend Sophie ET Paul",
         lambda: {"CL-0101", "CL-0102"} <= {c["code"] for c in outils.chercher_client("Martin")["clients"]})
verifier("fiche_client ne rend ni téléphone, ni e-mail, ni adresse",
         lambda: not {"telephone", "email", "adresse"} & set(outils.fiche_client("CL-0101")))
verifier("le contrat de CL-0115 n'est plus actif",
         lambda: outils.fiche_client("CL-0115")["contrat"]["actif_aujourdhui"] is False)
verifier("une injection SQL dans la recherche ne rend rien de plus",
         lambda: outils.chercher_client("x' or '1'='1")["nombre"] == 0)
verifier("proposer_rendez_vous n'écrit rien (statut PROPOSITION)",
         lambda: outils.proposer_rendez_vous("CL-0112", "entretien")["statut"].startswith("PROPOSITION"))
verifier("mission 3 — stock_piece('P-CIRC-25', 'Montbrison') rend 2",
         lambda: outils.stock_piece("P-CIRC-25", "Montbrison")["pieces"][0]["quantite"] == 2)
verifier("mission 3 — stock_piece('circulateur') rend les deux dépôts",
         lambda: {p["depot"] for p in outils.stock_piece("circulateur")["pieces"]} == {"Saint-Étienne", "Montbrison"})
verifier("mission 3 — techniciens_secteur('Montbrison', fluides=True) rend Thomas Brun seul",
         lambda: [t["nom"] for t in outils.techniciens_secteur("Montbrison", True)["techniciens"]] == ["Brun"])
verifier("mission 3 — les deux outils sont décrits au modèle (OUTILS) et exécutables (EXECUTER)",
         lambda: {"stock_piece", "techniciens_secteur"} <= {o["function"]["name"] for o in outils.OUTILS}
         and {"stock_piece", "techniciens_secteur"} <= set(outils.EXECUTER))
verifier("mission 3 — executer() rend du JSON même quand l'outil échoue",
         lambda: "erreur" in json.loads(outils.executer("stock_piece", {"mauvais": 1})))

print(f"\n{sum(resultats)}/{len(resultats)} vérifications passent.")
sys.exit(0 if all(resultats) else 1)
