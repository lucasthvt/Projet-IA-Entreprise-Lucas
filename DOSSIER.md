# Dossier — IA en entreprise

> Lucas THEVENET · BTS SIO 2 SLAM · octobre 2026 · fournisseur(s) utilisé(s) : ovh (par défaut) — ollama possible en local

## 1. De l'assistant grand public à une application (séance 25, mission 1)

**Ce qui ne va pas quand un salarié colle un rapport dans un assistant en ligne** (trois raisons, chacune reliée à un point de la [charte IA](donnees/documents/charte-ia.md)) :

1. **Fuite de données personnelles hors du système d'information.** Un rapport d'intervention contient des noms, des adresses et des numéros de téléphone. Les coller dans un assistant grand public revient à les envoyer à un tiers hors Union européenne, sans contrat de sous-traitance RGPD, avec un risque qu'ils servent à entraîner le modèle. → **Charte, article 1** (« les données des clients ne sont jamais copiées dans un outil d'IA grand public ») et **article 2** (traitement sur nos serveurs ou chez un prestataire UE, sous-traitant RGPD, sans entraînement).

2. **Perte de traçabilité et absence de validation humaine.** Un résumé produit par un modèle peut déformer un fait (une date, une référence de pièce, la nature d'une panne). Or la décision qui engage l'entreprise doit être validée par une personne habilitée, et chaque proposition doit être tracée. Un copier-coller dans un assistant en ligne ne laisse aucune trace exploitable : ni version de l'outil, ni règle citée, ni nom du validateur. → **Charte, article 3** (« l'IA propose, une personne décide ») et **article 4** (traçabilité : données, règles, version, validateur).

3. **Droits trop larges et client non informé.** Pour résumer un rapport technique, l'outil n'a besoin ni du nom ni du téléphone du client : la charte impose que chaque outil n'ait que les droits nécessaires à sa tâche. De plus, le client doit être informé lorsqu'une réponse a été préparée avec l'aide d'une IA, ce qu'un usage individuel et caché ne permet pas. → **Charte, article 5** (droits minimaux, lecture seule) et **article 6** (information du client).

**Ce que j'ai observé au lancement de `llm.py`** : le fournisseur par défaut est OVHcloud (`gpt-oss-120b`, zone « UE, sans entraînement ») et il accepte les trois sensibilités (publique, interne, personnelle). La table `ROUTAGE` de `llm.py` associe à chaque sensibilité les fournisseurs autorisés : `publique` → tous ; `interne` et `personnelle` → `ollama` ou `ovh` uniquement. Un appel demandant une sensibilité interdite est **refusé avant de partir**, et le refus est journalisé.

**L'architecture de l'agent** — schéma complété :

```mermaid
flowchart LR
    U[Assistante] -->|question| A[agent.py<br/>la boucle]
    A -->|consigne + question + liste des outils| R{llm.py<br/>routage souverain}
    R -->|données « personnelle » : ovh ou ollama| M[(Modèle)]
    R -->|sensibilité interdite| X[Refus RoutageRefuse<br/>journalisé dans appels.jsonl]
    M -->|« appelle fiche_client, code CL-0101 »| A
    A -->|exécute, lecture seule| O[outils.py]
    O --> B[(thermiforez.db)]
    A -->|proposition de rendez-vous| H{Validation<br/>humaine}
    H -->|accepté / corrigé / refusé| U
    A -->|tout est tracé, sans contenu| J[le journal]