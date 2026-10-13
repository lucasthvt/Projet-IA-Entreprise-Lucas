"""Vérifier la pseudonymisation SANS modèle (séance 26, mission 5).

    python s26-rag-decision/test_pseudo.py
"""
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import workflow  # noqa: E402

ok = []
def verifier(libelle, condition):
    ok.append(condition); print(("✓ " if condition else "✗ ") + libelle)

textes = {f.name: workflow.pseudonymiser(f.read_text(encoding="utf-8")) for f in sorted(workflow.RAPPORTS.glob("*.txt"))}
tout = "\n".join(textes.values())
verifier("aucun nom de client ne reste (Martin, Perrin, Delorme, Bonnet, Teyssier…)",
         not any(n in tout for n in ["Martin", "Perrin", "Delorme", "Mme Bonnet", "Teyssier", "Vernay", "Faure", "Roche,", "Hélène"]))
verifier("aucun numéro de téléphone ne reste", "06 39 98" not in tout and "04 65 71" not in tout)
verifier("les codes clients restent (ils servent à vérifier en base)", "CL-0101" in tout and "CL-0138" in tout)
verifier("les communes restent (elles servent à décider)", "Firminy" in tout and "Montbrison" in tout)
verifier("mission 5 — « 12 rue Michelet » est masqué", "Michelet" not in tout)
verifier("mission 5 — « 16 rue Jean-Jaurès » est masqué", "Jean-Jaurès" not in tout)
verifier("mission 5 — « rue des Acacias » est masqué", "Acacias" not in tout)
verifier("mission 5 — « hameau de Chazelles » est masqué", "Chazelles" not in tout)
print(f"\n{sum(ok)}/{len(ok)} vérifications passent.")
print("\nExemple :\n" + textes["RAP-2026-1007.txt"][:400])
sys.exit(0 if all(ok) else 1)
