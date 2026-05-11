from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from app.api.routes import router

app = FastAPI(title="Agentic Banking CRM")

app.include_router(router)