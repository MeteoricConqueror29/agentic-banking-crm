from fastapi import APIRouter
from app.models.customer_intelligence import HighValueCustomerFilters
from app.services.duckdb_service import DuckDBService
from app.tools.customer_tool import CustomerIntelligenceTool

router = APIRouter()


@router.get("/")
def health_check():
    return {
        "status": "success",
        "message": "Agentic Banking CRM running"
    }


db_service = DuckDBService(auto_initialize=True)
customer_tool = CustomerIntelligenceTool(db_service)


@router.get("/high-value-customers")
def get_high_value_customers():

    filters = HighValueCustomerFilters(
        min_relationship_score=60,
        min_income=50000,
        min_credit_score=700
    )

    result = customer_tool.find_high_value_customers(filters)

    return result.model_dump()