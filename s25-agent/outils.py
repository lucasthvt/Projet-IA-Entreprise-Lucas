"""Les outils de l'agent : ce qu'il a le DROIT de faire dans le système d'information.

Un agent ne « sait » rien de ThermiForez : il demande. Chaque outil est une
fonction Python qui interroge la base, et sa description (OUTILS, plus bas) est
tout ce que le modèle en voit. Trois règles, tirées de la charte IA (point 5) :

  1. LECTURE SEULE : la base est ouverte en mode « ro ». Même un outil mal
     écrit ne peut rien modifier.
  2. REQUÊTES PARAMÉTRÉES : jamais de SQL fabriqué avec le texte du modèle.
     Pas d'outil « exécuter du SQL » : ce serait donner les clés de la maison.
  3. MINIMISATION : un outil ne rend que ce dont la tâche a besoin. Ni
     téléphone, ni e-mail, ni adresse : l'assistante les a déjà sous les yeux.

    python s25-agent/outils.py          essaie chaque outil, sans modèle
"""
from __future__ import annotations

import json
import sqlite3
import unicodedata
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "donnees" / "thermiforez.db"
DATE_DU_JOUR = date(2026, 10, 14)        # la date du scénario : mercredi 14 octobre 2026


def connexion() -> sqlite3.Connection:
    """Ouverte en LECTURE SEULE (mode=ro) : toute écriture lève une erreur."""
    db = sqlite3.connect(f"file:{BASE}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.create_function("simple", 1, _simple, deterministic=True)
    return db


def _simple(t: str | None) -> str:
    """« Saint-Étienne » → « saint-etienne » : la recherche ignore accents et majuscules."""
    if t is None:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _jj_mm_aaaa(iso: str | None) -> str | None:
    return None if not iso else f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"


# ── Les outils fournis ─────────────────────────────────────────────────────────

def chercher_client(recherche: str) -> dict:
    """Clients qui correspondent à TOUS les mots de la recherche (code, nom, prénom ou commune), 5 au plus.
    « Martin Saint-Étienne » trouve Mme Sophie Martin, de Saint-Étienne."""
    mots = [m for m in recherche.replace(",", " ").split() if m.lower() not in ("m.", "mme", "m", "et", "à", "de")]
    if not mots:
        return {"nombre": 0, "clients": [], "attention": "recherche vide"}
    conditions = " and ".join(["(code = upper(?) or simple(nom) like ? or simple(prenom) like ? "
                               "or simple(commune) like ?)"] * len(mots))
    valeurs = [v for m in mots for v in (m, *[f"%{_simple(m)}%"] * 3)]
    with connexion() as db:
        lignes = db.execute(f"select code, civilite, nom, prenom, commune from clients where {conditions} "
                            "order by code limit 6", valeurs).fetchall()
    trouves = [dict(x) for x in lignes[:5]]
    return {"nombre": len(trouves), "clients": trouves,
            "attention": "plus de 5 clients correspondent : affinez la recherche" if len(lignes) > 5 else None}

def fiche_client(code: str) -> dict:
    """Le client, son contrat (actif ou non à la date du jour) et ses équipements. Sans coordonnées."""
    with connexion() as db:
        c = db.execute("select code, type, civilite, nom, prenom, commune, secteur, note "
                       "from clients where code = upper(?)", (code.strip(),)).fetchone()
        if not c:
            return {"erreur": f"aucun client avec le code {code}"}
        contrat = db.execute("select formule, debut, fin, renouvele from contrats where client_code = ? "
                             "order by fin desc limit 1", (c["code"],)).fetchone()
        equip = db.execute("select id, type, marque, modele, puissance_kw, mise_en_service from equipements "
                           "where client_code = ?", (c["code"],)).fetchall()
    fiche = dict(c)
    if contrat:
        actif = contrat["debut"] <= DATE_DU_JOUR.isoformat() <= contrat["fin"]
        fiche["contrat"] = {"formule": contrat["formule"], "debut": _jj_mm_aaaa(contrat["debut"]),
                            "fin": _jj_mm_aaaa(contrat["fin"]), "actif_aujourdhui": actif}
    else:
        fiche["contrat"] = None
    fiche["equipements"] = [dict(e) | {"mise_en_service": _jj_mm_aaaa(e["mise_en_service"])} for e in equip]
    return fiche


def historique_interventions(code: str, limite: int = 5) -> dict:
    """Les dernières interventions chez un client, les plus récentes d'abord."""
    with connexion() as db:
        lignes = db.execute(
            """select i.id, i.date, i.type, i.statut, i.resume, e.type as equipement,
                      t.prenom || ' ' || t.nom as technicien
                 from interventions i
                 join equipements e on e.id = i.equipement_id
                 left join techniciens t on t.id = i.technicien_id
                where e.client_code = upper(?)
                order by i.date desc limit ?""", (code.strip(), max(1, min(int(limite), 20)))).fetchall()
        res = []
        for x in lignes:
            pieces = db.execute("select p.libelle, ip.quantite, ip.prise_en_charge from intervention_pieces ip "
                                "join pieces p using(ref) where ip.intervention_id = ?", (x["id"],)).fetchall()
            res.append(dict(x) | {"date": _jj_mm_aaaa(x["date"]), "pieces": [dict(p) for p in pieces]})
    return {"code": code.upper(), "interventions": res}


def garantie_equipement(equipement_id: int) -> dict:
    """Jusqu'à quand le constructeur garantit les pièces de cet équipement
    (règles : donnees/documents/garanties-constructeurs.md)."""
    with connexion() as db:
        e = db.execute("select id, client_code, type, marque, modele, mise_en_service from equipements "
                       "where id = ?", (int(equipement_id),)).fetchone()
    if not e:
        return {"erreur": f"aucun équipement {equipement_id}"}
    mes = date.fromisoformat(e["mise_en_service"])
    def plus(ans):
        try:
            return mes.replace(year=mes.year + ans)
        except ValueError:             # 29 février
            return mes.replace(year=mes.year + ans, day=28)
    maitresse = {"Calorix": ("échangeur", 5), "Aerotherm": ("compresseur", 5), "Ventalis": ("moteur", 3)}.get(e["marque"])
    res = {"equipement": dict(e) | {"mise_en_service": _jj_mm_aaaa(e["mise_en_service"])},
           "pieces_garanties_jusquau": plus(2).strftime("%d/%m/%Y"),
           "pieces_sous_garantie_aujourdhui": plus(2) >= DATE_DU_JOUR}
    if maitresse:
        nom, ans = maitresse
        res[f"{nom}_garanti_jusquau"] = plus(ans).strftime("%d/%m/%Y")
        res[f"{nom}_sous_garantie_aujourdhui"] = plus(ans) >= DATE_DU_JOUR
    res["condition"] = "entretien à jour et mise en service par un professionnel"
    return res


def proposer_rendez_vous(code: str, motif: str, semaine_du: str | None = None) -> dict:
    """PROPOSE un créneau (le premier jour ouvré où un technicien du secteur a moins de
    trois interventions). N'ÉCRIT RIEN : une personne valide ensuite."""
    debut = date.fromisoformat(semaine_du) if semaine_du else DATE_DU_JOUR + timedelta(days=7 - DATE_DU_JOUR.weekday())
    with connexion() as db:
        c = db.execute("select code, secteur from clients where code = upper(?)", (code.strip(),)).fetchone()
        if not c:
            return {"erreur": f"aucun client avec le code {code}"}
        pac = db.execute("select count(*) from equipements where client_code = ? and type like 'PAC%'",
                         (c["code"],)).fetchone()[0] > 0
        techs = db.execute("select id, prenom, nom from techniciens where secteur = ? "
                           "and (? = 0 or habilitation_fluides = 1)", (c["secteur"], int(pac))).fetchall()
        for i in range(10):
            jour = debut + timedelta(days=i)
            if jour.weekday() >= 5:
                continue
            for t in techs:
                n = db.execute("select count(*) from interventions where technicien_id = ? and date = ? "
                               "and statut = 'planifiée'", (t["id"], jour.isoformat())).fetchone()[0]
                if n < 3:
                    return {"statut": "PROPOSITION — à valider par une personne ; rien n'est enregistré",
                            "client": c["code"], "motif": motif, "date": jour.strftime("%d/%m/%Y"),
                            "technicien": f"{t['prenom']} {t['nom']}",
                            "habilitation_fluides_requise": pac}
    return {"statut": "aucun créneau trouvé sur deux semaines", "client": c["code"]}


# ── À vous : deux outils de plus (séance 25, mission 3) ────────────────────────

def stock_piece(recherche: str, depot: str | None = None) -> dict:
    """Quantité en stock d'une pièce, par dépôt (Saint-Étienne, Montbrison).

    recherche : une référence (P-CIRC-25) ou un morceau de libellé (« circulateur »).
    depot     : facultatif ; sans lui, les deux dépôts.
    Rend : {"pieces": [{"ref", "libelle", "depot", "quantite"}, …]} — au plus 10 lignes.
    Tables : pieces (ref, libelle) et stock (ref, depot, quantite). Requête paramétrée !
    """
    conditions = "(upper(p.ref) = upper(?) or simple(p.libelle) like ?)"
    valeurs = [recherche.strip(), f"%{_simple(recherche)}%"]
    if depot:
        conditions += " and simple(s.depot) = simple(?)"
        valeurs.append(depot.strip())
    with connexion() as db:
        lignes = db.execute(
            f"""select p.ref, p.libelle, s.depot, s.quantite
                  from pieces p
                  join stock s on s.ref = p.ref
                 where {conditions}
                 order by p.ref, s.depot
                 limit 10""", valeurs).fetchall()
    return {"pieces": [dict(x) for x in lignes]}


def techniciens_secteur(secteur: str, fluides: bool = False) -> dict:
    """Les techniciens d'un secteur (Saint-Étienne, Montbrison, Gier, Ondaine).

    fluides : si vrai, seulement ceux qui ont l'habilitation fluides frigorigènes
              (nécessaire pour ouvrir le circuit d'une pompe à chaleur).
    Rend : {"secteur", "techniciens": [{"prenom", "nom", "habilitation_fluides"}, …]}.
    Table : techniciens. Ni téléphone ni adresse : il n'y en a pas, et c'est voulu.
    """
    sql = ("select prenom, nom, habilitation_fluides from techniciens "
           "where simple(secteur) = simple(?)")
    valeurs = [secteur.strip()]
    if fluides:
        sql += " and habilitation_fluides = 1"
    sql += " order by nom, prenom"
    with connexion() as db:
        lignes = db.execute(sql, valeurs).fetchall()
    return {"secteur": secteur, "techniciens": [dict(x) for x in lignes]}


# ── Ce que le modèle voit : nom, description, paramètres (JSON Schema) ──────────

def _outil(nom: str, description: str, proprietes: dict, requis: list[str]) -> dict:
    return {"type": "function", "function": {"name": nom, "description": description,
            "parameters": {"type": "object", "properties": proprietes, "required": requis}}}


OUTILS = [
    _outil("chercher_client", "Trouver un client par son code (CL-0101), son nom, son prénom ou sa commune. "
           "Rend au plus 5 clients, sans coordonnées.",
           {"recherche": {"type": "string", "description": "code, nom, prénom ou commune"}}, ["recherche"]),
    _outil("fiche_client", "La fiche d'un client : contrat (formule, dates, actif ou non aujourd'hui) et équipements.",
           {"code": {"type": "string", "description": "code client, ex. CL-0101"}}, ["code"]),
    _outil("historique_interventions", "Les dernières interventions chez un client (entretiens, dépannages), "
           "les plus récentes d'abord.",
           {"code": {"type": "string"}, "limite": {"type": "integer", "description": "1 à 20, 5 par défaut"}}, ["code"]),
    _outil("garantie_equipement", "Jusqu'à quand le constructeur garantit les pièces d'un équipement "
           "(id d'équipement donné par fiche_client).",
           {"equipement_id": {"type": "integer"}}, ["equipement_id"]),
    _outil("proposer_rendez_vous", "PROPOSER un rendez-vous à un client. N'enregistre rien : la proposition "
           "doit être validée par une personne.",
           {"code": {"type": "string"}, "motif": {"type": "string"},
            "semaine_du": {"type": "string", "description": "lundi de la semaine voulue, AAAA-MM-JJ (facultatif)"}},
           ["code", "motif"]),
        _outil("stock_piece", "Quantité en stock d'une pièce, par dépôt (Saint-Étienne, Montbrison). "
           "recherche : une référence (P-CIRC-25) ou un morceau de libellé (« circulateur »). "
           "depot : facultatif.",
           {"recherche": {"type": "string", "description": "référence ou morceau de libellé"},
            "depot": {"type": "string", "description": "Saint-Étienne ou Montbrison (facultatif)"}},
           ["recherche"]),
    _outil("techniciens_secteur", "Les techniciens d'un secteur (Saint-Étienne, Montbrison, Gier, Ondaine). "
           "fluides=true pour ne garder que ceux habilités fluides frigorigènes (pompes à chaleur).",
           {"secteur": {"type": "string", "description": "nom du secteur"},
            "fluides": {"type": "boolean", "description": "true = habilitation fluides seulement"}},
           ["secteur"]),
]

EXECUTER = {
    "chercher_client": chercher_client,
    "fiche_client": fiche_client,
    "historique_interventions": historique_interventions,
    "garantie_equipement": garantie_equipement,
    "proposer_rendez_vous": proposer_rendez_vous,
    "stock_piece": stock_piece,
    "techniciens_secteur": techniciens_secteur,
}


def executer(nom: str, arguments: str | dict) -> str:
    """Exécute l'outil demandé par le modèle et rend le résultat en JSON (texte).
    Une erreur est RENDUE au modèle (il peut se corriger), jamais levée."""
    if nom not in EXECUTER:
        return json.dumps({"erreur": f"outil inconnu ou non autorisé : {nom}"}, ensure_ascii=False)
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        return json.dumps(EXECUTER[nom](**args), ensure_ascii=False, default=str)
    except NotImplementedError as exc:
        return json.dumps({"erreur": str(exc)}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"erreur": f"{type(exc).__name__} : {exc}"}, ensure_ascii=False)


if __name__ == "__main__":
    print(executer("chercher_client", {"recherche": "Martin"}))
    print(executer("fiche_client", {"code": "CL-0115"}))
    print(executer("historique_interventions", {"code": "CL-0101", "limite": 2}))
    print(executer("garantie_equipement", {"equipement_id": 120}))
    print(executer("proposer_rendez_vous", {"code": "CL-0112", "motif": "entretien"}))
    print(executer("stock_piece", {"recherche": "circulateur", "depot": "Montbrison"}))
    print(executer("techniciens_secteur", {"secteur": "Montbrison", "fluides": True}))
