from fastapi import FastAPI, Request, Response, status

app = FastAPI()

@app.post("/user/me")
async def auth(request: Request, response: Response):
    data = await request.json()
    return {"result": "allow"}
    # response.status_code = status.HTTP_403_FORBIDDEN
    # return {"result": "deny"}

@app.post("/user/me/aclcheck")
async def aclcheck(request: Request, response: Response):
    data = await request.json()
    return {"result": "allow"}
    # response.status_code = status.HTTP_403_FORBIDDEN
    # return {"result": "deny"}
