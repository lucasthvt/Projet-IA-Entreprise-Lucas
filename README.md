# IA en entreprise — agents, RAG, workflows, décisions de confiance

> BTS SIO 2 SLAM · module 2026-2027 · **Consignes des séances** : <https://ggaillard.github.io/portail-bts/distance/ia-entreprise.html>
> Organisation, personnes, adresses et données : **fictives**.

## Le contexte : ThermiForez

ThermiForez (fictive) entretient et dépanne chaudières, pompes à chaleur et VMC autour de Saint-Étienne : 38 salariés, 14 techniciens sur quatre secteurs, environ 2 400 clients sous contrat. Aujourd'hui, l'assistante du service client cherche les informations dans trois écrans, et certains salariés **collent des rapports d'intervention dans un assistant IA grand public** pour les résumer — avec les noms, adresses et téléphones des clients dedans.

La direction veut passer de cet usage « à la ChatGPT » à de **vrais outils**, intégrés au système d'information, dont on peut **mesurer** le comportement, **tracer** chaque décision, et dont les données ne sortent pas n'importe où. Elle a adopté une [charte IA](donnees/documents/charte-ia.md) ; vous construisez ce qu'elle décrit.

## Ce que vous construisez

| Séance | Ce que vous construisez | Concepts |
|---|---|---|
| **25** — un agent connecté | un assistant pour le service client, qui **interroge la base** par des outils, en lecture seule, et **propose** des rendez-vous qu'une personne valide | agent conversationnel connecté ; orchestration (le modèle demande, le programme exécute) ; droits minimaux ; injection indirecte ; routage souverain |
| **26** — RAG, workflow, décision | un **RAG** qui répond à partir des documents internes en les citant ; un **workflow** qui transforme les rapports des techniciens en décisions de prise en charge **calculées, justifiées, validées** | RAG (mots-clés contre vecteurs) ; workflow automatisé ; IA d'aide à la décision ; calibration de la confiance ; humain dans la boucle ; pseudonymisation |

Les trois idées qui traversent le module :

1. **Confiance et décision** — l'IA ne produit pas seulement du texte : elle prépare une décision. Le programme calcule ce qui se calcule, le modèle qualifie ce qui est écrit en langage naturel, une personne décide dès que l'enjeu le demande. Et on **mesure** si la confiance affichée est méritée.
2. **Orchestration** — un projet IA n'est pas un prompt : ce sont des étapes, chacune à sa place (Python, modèle, base, humain), avec un journal.
3. **Souveraineté et sécurité** — chaque appel au modèle déclare la **sensibilité** des données qu'il transporte ; [`llm.py`](llm.py) refuse de les envoyer à un fournisseur qui n'y a pas droit.

## Démarrer

1. **Use this template → Create a new repository**, à votre nom : `ia-entreprise-<prenom>`. Clonez-le.
2. Python 3.10 ou plus, puis :
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows   (macOS, Linux : source .venv/bin/activate)
   pip install -r requirements.txt
   copy .env.example .env          # macOS, Linux : cp .env.example .env
   ```
3. Essayez le modèle — par défaut **OVHcloud, sans compte ni clé, hébergé en France** :
   ```bash
   python llm.py
   ```
   La sortie dit aussi quelles sensibilités de données ce fournisseur a le droit de recevoir.

La base `donnees/thermiforez.db` est fournie ; `python donnees/creer_base.py` la recrée à l'identique.

## Quel fournisseur ?

| `FOURNISSEUR=` | Ce qu'il faut | Données internes et personnelles ? |
|---|---|---|
| `ovh` | rien (2 requêtes par minute et par modèle sans clé) | oui : France, pas d'entraînement selon OVHcloud |
| `ollama` | Ollama et un modèle qui sait appeler des outils (`qwen2.5:7b` ou plus) | oui : rien ne sort de votre PC |
| `github`, `groq`, `google` | un compte gratuit et une clé (séance 24) | **non** : hors Union européenne |
| `mistral` | compte et téléphone vérifié | **non** sur l'offre gratuite : entraînement possible |

Pour **prototyper** avec un fournisseur hors politique, parce que les données sont fictives : `DONNEES_FICTIVES=oui` dans `.env`. Chaque appel est alors marqué « derogation » dans `journal/appels.jsonl` — en production, ce serait refusé.

## Le dépôt

| | |
|---|---|
| [`llm.py`](llm.py) | le seul endroit qui parle au modèle : fournisseurs, **routage souverain**, journal |
| [`donnees/`](donnees/) | la base SQLite, les 9 documents internes (RAG), les 12 rapports d'intervention |
| [`s25-agent/`](s25-agent/) | l'agent : `agent.py` (la boucle), `outils.py` (ce qu'il a le droit de faire), `consigne_agent.txt`, `questions.json` + `evaluer_agent.py` (la mesure), `test_outils.py` |
| [`s26-rag-decision/`](s26-rag-decision/) | `rag.py` + `evaluer_rag.py` ; `workflow.py` (sept étapes), `valider.py` (l'humain), `decisions_attendues.json` + `evaluer_decisions.py`, `test_pseudo.py` |
| `journal/` | tout ce qui s'est passé : appels au modèle, étapes de l'agent et du workflow, décisions, validations, mesures |
| [`DOSSIER.md`](DOSSIER.md) | **votre dossier**, à remplir au fil des deux séances |
