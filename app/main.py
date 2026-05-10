from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(title="Agentic Banking CRM")

app.include_router(router)