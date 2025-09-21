
# BayrouMeter


### Application de sondage en ligne (Oui/Non) hébergée sur Azure :

 - Front statique (HTML/JS) → Azure Static Web Apps
 - API (Python / Azure Functions) → Function App
 - Données → Azure Cosmos DB (API SQL)


### Sommaire

- Architecture
- Schéma
- Endpoints API
- Arborescence
- Captures d’écran



### Architecture

- L’utilisateur ouvre le site statique (pages frontend/) servi par Azure Static Web Apps.
- Le front appelle l’API exposée par Azure Functions.
- Les fonctions lisent/écrivent dans Cosmos DB :

        users : enregistrements d’utilisateurs (unicité sur l’email).

        votes : un vote par utilisateur (partitionné par userId).
        resultat : qui retoune en pourcentage la totaliter des votes soumis
- Application Insights (activé par défaut sur Function App) collecte logs & métriques.

### Schéma

```
flowchart LR
  User((👤 Utilisateur))
  SWA[Azure Static Web Apps\n(frontend HTML/JS)]
  API[Azure Functions\n(Python)]
  COSMOS[(Azure Cosmos DB\nAPI SQL)]
  AI[(Application Insights\nlogs/metrics)]

  User -->|HTTP GET| SWA
  SWA -->|fetch() /api/*| API
  API -->|SQL (SDK/Bindings)| COSMOS
  API --> AI
```

### API Reference

```
 Base (prod) : https://bayroumeter-functions.azurewebsites.net/api
 En local(exemple) : http://localhost:7071/api
```

#### post user

```
  post /postUser
```

Crée ou retourne un utilisateur existant (idempotent via l’email).

{ "email": "test@example.com", "pseudo": "test" }

#### Get user

```
  GET /users
```

Retourne la liste { id, pseudo, email }

{ "id": "uuid1", "pseudo": "test", "email": "test@example.com" }

#### post postVote

```
  post /postVote?userId=<UUID>
```

Enregistre un vote Oui/Non pour l’utilisateur.

{ "choice": "Oui" }

#### Get votes

```
  GET /votes
```

Liste brute des votes :

{ "id":"v-uuid", "userId":"u-uuid", "choice":"Oui", "createdAt":"..." }

#### Get resultat

```
  GET /resultat
```

Agrège les votes et renvoie pourcentages.

{
  "total": 12,
  "counts": { "Oui": 7, "Non": 5 },
  "percent": { "Oui": 58.3, "Non": 41.7 }
}



### Arborescence

```
BayrouMeter/
├─ api/
│  └─ BayrouMeter-functions/
│     ├─ function_app.py
│     ├─ requirements.txt
│     ├─ host.json
│     └─ local.settings.json   (local uniquement)
├─ frontend/
│  ├─ login.html
│  ├─ vote.html
│  └─ results.html
└─ docs/
   ├─ login.png
   ├─ vote.png
   ├─ results.png
   └─ monitoring-functions.png
```
