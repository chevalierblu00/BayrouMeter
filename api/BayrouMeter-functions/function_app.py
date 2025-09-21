import azure.functions as func
import datetime
import uuid
import json
import logging

app = func.FunctionApp()

# ---- POST /postUser : crée un utilisateur (pseudo, email) ----
@app.function_name(name="postUser")
@app.route(route="postUser", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# 🔹 Sortie (écriture dans Cosmos DB)
@app.cosmos_db_output(
    arg_name="outUser",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="users",
    create_if_not_exists=True,
    partition_key="/id"
)
# 🔹 Entrée (lecture dans Cosmos DB)
@app.cosmos_db_input(
    arg_name="existingUser",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="users",
    sql_query="SELECT * FROM c WHERE c.email = {email}"
)
def postUser(
    req: func.HttpRequest,
    outUser: func.Out[func.Document],
    existingUser: func.DocumentList
) -> func.HttpResponse:

    # Lire/valider le JSON du body
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Corps JSON invalide"}),
            mimetype="application/json",
            status_code=400
        )

    pseudo = (body.get("pseudo") or "").strip()
    email  = (body.get("email") or "").strip().lower()

    if not pseudo or not email:
        return func.HttpResponse(
            json.dumps({"error": "Champs requis: pseudo, email"}),
            mimetype="application/json",
            status_code=400
        )

    #  Vérifier si l'utilisateur existe déjà
    if existingUser:  
        return func.HttpResponse(
            json.dumps({"error": "User already exists"}),
            mimetype="application/json",
            status_code=403
        )

    # Création du document si pas existant
    user_doc = {
        "id": str(uuid.uuid4()),
        "pseudo": pseudo,
        "email": email,
        "createdAt": __import__("datetime").datetime.utcnow().isoformat() + "Z"
    }

    outUser.set(func.Document.from_dict(user_doc))
    return func.HttpResponse(
        json.dumps({
            "id": user_doc["id"],
            "pseudo": user_doc["pseudo"],
            "email": user_doc["email"]
        }),
        mimetype="application/json",
        status_code=201
    )

# ---- GET /users : renvoie tous les utilisateurs (id, pseudo, email) ----
@app.function_name(name="getUsers")
@app.route(route="users", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@app.cosmos_db_input(
    arg_name="inUsers",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="users",
    sql_query="SELECT c.id, c.pseudo, c.email FROM c"
)
def getUsers(req: func.HttpRequest, inUsers: func.DocumentList) -> func.HttpResponse:
    logging.info("Processing GET /users")
    try:
        items = [doc.to_dict() for doc in inUsers]  # liste de {id, pseudo, email}
        return func.HttpResponse(
            json.dumps(items),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.exception("Erreur GET /users")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )


# ---- POST /postVote : crée un vote (userId, choice) ----
@app.function_name(name="postVote")
@app.route(route="postVote", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# vérifier l'existence de l'utilisateur
@app.cosmos_db_input(
    arg_name="inUser",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="users",
    sql_query="SELECT TOP 1 c.id FROM c WHERE c.id = {userId}"
)
# vérifier le vote existant pour cet utilisateur
@app.cosmos_db_input(
    arg_name="inExisting",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="votes",
    sql_query="SELECT TOP 1 c.id FROM c WHERE c.userId = {userId}"
)
# vote de sortie
@app.cosmos_db_output(
    arg_name="outVote",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="votes",
    create_if_not_exists=True,
    partition_key="/userId"
)
def postVote(req: func.HttpRequest,
             inUser: func.DocumentList,
             inExisting: func.DocumentList,
             outVote: func.Out[func.Document]) -> func.HttpResponse:
    logging.info("Processing POST /postVote")

    # userId doit être fourni comme paramètre de requête pour que les liaisons remplacent {userId}
    user_id = (req.params.get("userId") or "").strip()
    if not user_id:
        return func.HttpResponse(json.dumps({"error": "Missing query parameter: userId"}),
                                 mimetype="application/json", status_code=400)

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(json.dumps({"error": "Corps JSON invalide"}),
                                 mimetype="application/json", status_code=400)

    choice = (body.get("choice") or "").strip()
    if choice not in ["Oui", "Non"]:
        return func.HttpResponse(json.dumps({"error": "Choix invalide (Oui/Non)"}),
                                 mimetype="application/json", status_code=400)

    # verifie si l'utilisateur existe
    if not inUser or len(inUser) == 0:
        return func.HttpResponse(json.dumps({"error": "Utilisateur inexistant"}),
                                 mimetype="application/json", status_code=404)

    # verifie si l'utilisateur a déjà voté
    if inExisting and len(inExisting) > 0:
        return func.HttpResponse(json.dumps({"error": "Ce compte a déjà voté"}),
                                 mimetype="application/json", status_code=409)

    vote_doc = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "choice": choice,
        "createdAt": __import__("datetime").datetime.utcnow().isoformat() + "Z"
    }

    outVote.set(func.Document.from_dict(vote_doc))
    return func.HttpResponse(json.dumps(vote_doc),
                             mimetype="application/json", status_code=201)

# ---- GET /votes : renvoie tous les votes (id, userId, choice, createdAt) ----
@app.function_name(name="getVotes")
@app.route(route="votes", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@app.cosmos_db_input(
    arg_name="inVotes",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="votes",
    sql_query="SELECT c.id, c.userId, c.choice, c.createdAt FROM c"
)
def getVotes(req: func.HttpRequest, inVotes: func.DocumentList) -> func.HttpResponse:
    items = [doc.to_dict() for doc in inVotes]
    return func.HttpResponse(json.dumps(items), mimetype="application/json", status_code=200)

# ---- GET /resultat : agrège Oui/Non et renvoie en % ----
@app.function_name(name="resultat")  
@app.route(route="resultat", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
# Input binding Cosmos DB :
#   - lit dans la base "sondage-db", conteneur "votes"
#   - exécute la requête d’agrégation pour obtenir, par choix, le nombre de votes
#   - le résultat est injecté dans le paramètre Python `inAgg` (DocumentList)
@app.cosmos_db_input(
    arg_name="inAgg",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="votes",
    sql_query="SELECT c.choice, COUNT(1) AS count FROM c GROUP BY c.choice"
)
def resultat(req: func.HttpRequest, inAgg: func.DocumentList) -> func.HttpResponse:
    try:
        # Initialisation des compteurs
        counts = {"Oui": 0, "Non": 0}

        # Parcours des lignes renvoyées par l’input binding
        for d in inAgg:
            row = d.to_dict() if hasattr(d, "to_dict") else d
            # Suivant les versions, le driver peut remonter des clés différentes
            choice = row.get("choice") or row.get("c.choice")  # suivant le driver
            cnt = row.get("count") or row.get("$1") or 0       # $1 si pas d'alias
            # Normalisation en entier
            try:
                cnt = int(cnt)
            except Exception:
                cnt = 0
            if choice in counts:
                counts[choice] = cnt

        # Calcul des pourcentages
        total = counts["Oui"] + counts["Non"]
        pct_oui = round((counts["Oui"] / total) * 100, 1) if total else 0.0
        pct_non = round((counts["Non"] / total) * 100, 1) if total else 0.0

        # Préparation du payload
        payload = {
            "total": total,
            "counts": counts,
            "percent": {"Oui": pct_oui, "Non": pct_non}
        }
        return func.HttpResponse(json.dumps(payload), mimetype="application/json", status_code=200)

    except Exception as e:
        logging.exception("Erreur GET /results")
        return func.HttpResponse(json.dumps({"error": str(e)}),
                                 mimetype="application/json", status_code=500)