from fastapi import FastAPI, Request, Response, status
import logging
from pydantic import BaseModel

class ACLCheckPayload(BaseModel):
    username: str
    client_id: str
    topic: str
    access: int

class UserCheckPayload(BaseModel):
    username: str
    password: str
    client_id: str


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

app = FastAPI()

def valid_user(username: str, password: str, client_id: str):
    return username == ALLOWED_USERNAME and password == ALLOWED_PASSWORD

def valid_acl(username: str, topic: str, client_id=None, access=None):
    return username == ALLOWED_USERNAME and topic == ALLOWED_TOPIC

ALLOWED_USERNAME="testuser"
ALLOWED_TOPIC="test/topic"
ALLOWED_USERID=""
ALLOWED_PASSWORD="testpassword"
ALLOWED_ACCESS=1

@app.post("/user/me")
async def auth(payload: UserCheckPayload, response: Response):
    logging.debug(f"user/me payload: {payload}")
    if valid_user(payload.username, payload.password, payload.client_id):
        return {"result": "allow"}
    else:
        response.status_code = status.HTTP_403_FORBIDDEN
        return {"result": "deny"}

@app.post("/user/me/aclcheck")
async def aclcheck(payload: ACLCheckPayload, response: Response):
    logging.debug(f"user/me/aclcheck payload: {payload}")
    if valid_acl(payload.username, payload.topic, payload.client_id, payload.access):
        return {"result": "allow"}
    else:
        response.status_code = status.HTTP_403_FORBIDDEN
        return {"result": "deny"}
