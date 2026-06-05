from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str   # UUID generated in the browser, stored in localStorage
    # persona is no longer sent by the client — it is loaded from the DB
    # using the user_id extracted from the JWT
