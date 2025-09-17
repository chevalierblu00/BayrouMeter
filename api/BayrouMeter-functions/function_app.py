import azure.functions as func
import datetime
import uuid
import json
import logging

app = func.FunctionApp()

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

    # ✅ Récupération et validation du JSON
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

    # ✅ Vérifier si l'utilisateur existe déjà
    if existingUser:  # func.DocumentList se comporte comme une liste
        return func.HttpResponse(
            json.dumps({"error": "User already exists"}),
            mimetype="application/json",
            status_code=403
        )

    # ✅ Création du document si pas existant
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

@app.function_name(name="getUsers")
@app.route(route="users", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@app.cosmos_db_input(
    arg_name="inUsers",
    connection="COSMOS_CONN_STRING",   # AccountEndpoint=...;AccountKey=...;
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

# ------------------------------------------------------------
# POST /postVote?userId=...  — vote par ID utilisateur
# - lit l'utilisateur (inUser) et un éventuel vote existant (inExisting)
# - écrit le vote via outVote
# ------------------------------------------------------------
@app.function_name(name="postVote")
@app.route(route="postVote", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
# check user existence
@app.cosmos_db_input(
    arg_name="inUser",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="users",
    sql_query="SELECT TOP 1 c.id FROM c WHERE c.id = {userId}"
)
# check existing vote for this user
@app.cosmos_db_input(
    arg_name="inExisting",
    connection="COSMOS_CONN_STRING",
    database_name="sondage-db",
    container_name="votes",
    sql_query="SELECT TOP 1 c.id FROM c WHERE c.userId = {userId}"
)
# output vote
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

    # userId must be provided as query param for the bindings to substitute {userId}
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

    # user exists?
    if not inUser or len(inUser) == 0:
        return func.HttpResponse(json.dumps({"error": "Utilisateur inexistant"}),
                                 mimetype="application/json", status_code=404)

    # already voted?
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

# ------------------------------------------------------------
# GET /votes  — liste tous les votes
# ------------------------------------------------------------
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