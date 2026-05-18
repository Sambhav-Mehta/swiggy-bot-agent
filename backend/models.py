from pydantic import BaseModel


class Persona(BaseModel):
    name: str
    location: str
    diet_goals: str = ""
    restrictions: str = ""
    preferences: str = ""
    budget_wkday: str = ""
    budget_wknd: str = ""
    address_id: str = ""   # Swiggy addressId; falls back to SWIGGY_ADDRESS_ID env var


class ChatRequest(BaseModel):
    message: str
    session_id: str   # UUID generated in the browser, stored in localStorage
    persona: Persona
