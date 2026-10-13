"""Mesurer le RAG : la bonne source est-elle trouvée ? la réponse est-elle juste ? s'abstient-il quand il faut ?

    python s26-rag-decision/evaluer_rag.py                      mode mots-clés
    python s26-rag-decision/evaluer_rag.py --mode vecteurs      mode vecteurs (index --vecteurs requis)
    python s26-rag-decision/evaluer_rag.py --pause 20           avec un fournisseur limité en débit

Quatre chiffres :
  • trouvée  : la source attendue est parmi les passages donnés au modèle (la RECHERCHE marche) ;
  • juste    : la réponse contient ce qu'il faut (la GÉNÉRATION marche) ;
  • citée    : la réponse cite un passage de la source attendue ;
  • abstention correcte : pour une question hors documents, « Je ne trouve pas… ».
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import rag  # noqa: E402

def norm(t):
    for a, b in (("**", ""), ("’", "'"), ("‑", "-"), (" ", " "), (" ", " ")):
        t = t.replace(a, b)
    return t.lower()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["motscles", "vecteurs"], default="motscles")
    p.add_argument("--pause", type=float, default=0)
    a = p.parse_args()
    cas_tous = json.loads((ICI / "questions_rag.json").read_text(encoding="utf-8"))
    lignes, cpt = [], {"trouvee": 0, "juste": 0, "citee": 0, "dans": 0, "hors": 0, "abst": 0}
    for i, c in enumerate(cas_tous):
        if a.pause and i:
            time.sleep(a.pause)
        r = rag.repondre(c["question"], a.mode)
        rep = norm(r["reponse"])
        abstenu = "je ne trouve pas cette information" in rep
        if c["source_attendue"]:
            cpt["dans"] += 1
            attendues = c["source_attendue"].split("|")
            trouvee = any(s.split("#")[0] in attendues for s in r["sources"])
            juste = not abstenu and all(any(norm(m) in rep for m in g) for g in c["doit_contenir_un_de"])
            citee = any(s.split("#")[0] in attendues for s in r["cites"])
            cpt["trouvee"] += trouvee; cpt["juste"] += juste; cpt["citee"] += citee
            v = f"trouvée {'ok' if trouvee else '--'} · juste {'ok' if juste else '--'} · citée {'ok' if citee else '--'}"
        else:
            cpt["hors"] += 1; cpt["abst"] += abstenu
            v = f"hors documents · abstention {'ok' if abstenu else '--'}"
        print(f"{c['id']} {v} · {c['question'][:60]}")
        lignes.append([c["id"], a.mode, v, " ".join(r["sources"]), r["reponse"].replace("\n", " ")[:400]])
    n = cpt["dans"]
    print(f"\nMode {a.mode} : source trouvée {cpt['trouvee']}/{n} · réponse juste {cpt['juste']}/{n} · "
          f"citée {cpt['citee']}/{n} · abstention correcte {cpt['abst']}/{cpt['hors']}")
    nom = ICI.parent / "journal" / time.strftime(f"resultats-rag-{a.mode}-%Y%m%d-%H%M.csv")
    with open(nom, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["id", "mode", "verdict", "sources", "reponse"]); w.writerows(lignes)
    print(f"Détail : {nom.relative_to(ICI.parent)}")

if __name__ == "__main__":
    main()
