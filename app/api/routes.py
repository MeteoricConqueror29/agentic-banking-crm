from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def health_check():
    return {
        "status": "success",
        "message": "Agentic Banking CRM running"
    }