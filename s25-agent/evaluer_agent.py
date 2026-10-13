"""Mesurer l'agent : rejouer questions.json et compter.

    python s25-agent/evaluer_agent.py                    une fois chaque question
    python s25-agent/evaluer_agent.py --essais 3         trois fois (les réponses varient)
    python s25-agent/evaluer_agent.py --seulement A04 A05 --pause 30

Pour chaque question, trois verdicts :
  • réponse : contient ce qu'il faut (un mot de chaque groupe de « doit_contenir_un_de »)
              et rien de ce qui est interdit (« ne_doit_pas ») ;
  • outils  : les outils attendus ont été appelés, les outils interdits non ;
  • juste   : les deux.
Écrit resultats-agent-AAAAMMJJ-HHMM.csv dans le journal.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import agent  # noqa: E402
import llm    # noqa: E402


def normaliser(t: str) -> str:
    """Ce qui ne change pas le sens ne doit pas changer le verdict : gras, apostrophes, espaces, tirets."""
    for a, b in (("**", ""), ("’", "'"), ("\u2011", "-"), ("\u2010", "-"), ("\u00a0", " "), ("\u202f", " ")):
        t = t.replace(a, b)
    return t.lower()


def juger(cas: dict, r: dict) -> tuple[bool, bool]:
    bas = normaliser(r["reponse"])
    rep_ok = all(any(normaliser(m) in bas for m in groupe) for groupe in cas.get("doit_contenir_un_de", []))
    rep_ok = rep_ok and not any(normaliser(m) in bas for m in cas.get("ne_doit_pas", []))
    outils_ok = all(o in r["outils"] for o in cas.get("outils_attendus", []))
    outils_ok = outils_ok and not any(o in r["outils"] for o in cas.get("outils_interdits", []))
    return rep_ok, outils_ok


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--essais", type=int, default=1)
    p.add_argument("--pause", type=float, default=0, help="secondes entre deux questions")
    p.add_argument("--seulement", nargs="*", help="identifiants de questions (A01 A04…)")
    a = p.parse_args()

    cas_tous = json.loads((ICI / "questions.json").read_text(encoding="utf-8"))
    if a.seulement:
        cas_tous = [c for c in cas_tous if c["id"] in a.seulement]
    lignes, justes, total, durees = [], 0, 0, []
    for cas in cas_tous:
        for essai in range(1, a.essais + 1):
            if a.pause and total:
                time.sleep(a.pause)
            debut = time.perf_counter()
            try:
                r = agent.repondre(cas["question"])
            except (llm.ErreurModele, llm.RoutageRefuse) as exc:
                r = {"reponse": f"ERREUR {exc}", "outils": [], "etapes": 0}
            duree = time.perf_counter() - debut
            rep_ok, outils_ok = juger(cas, r) if not r["reponse"].startswith("ERREUR") else (False, False)
            total += 1
            justes += rep_ok and outils_ok
            durees.append(duree)
            marque = "✓" if rep_ok and outils_ok else ("~" if rep_ok or outils_ok else "✗")
            print(f"{cas['id']}.{essai} {marque} réponse {'ok' if rep_ok else '--'} · outils {'ok' if outils_ok else '--'}"
                  f" · {duree:5.1f} s · {cas['nom']}")
            lignes.append([cas["id"], essai, cas["nom"], int(rep_ok), int(outils_ok), round(duree, 1),
                           " > ".join(r["outils"]), r["reponse"].replace("\n", " ")[:400]])
    nom = ICI.parent / "journal" / time.strftime("resultats-agent-%Y%m%d-%H%M.csv")
    nom.parent.mkdir(exist_ok=True)
    with open(nom, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "essai", "nom", "reponse_ok", "outils_ok", "duree_s", "outils", "reponse"])
        w.writerows(lignes)
    print(f"\nJuste : {justes}/{total} = {100 * justes / max(total, 1):.0f} %"
          f" · temps médian {statistics.median(durees):.1f} s · fournisseur {llm.FOURNISSEUR}")
    print(f"Détail : {nom.relative_to(ICI.parent)}")


if __name__ == "__main__":
    main()
