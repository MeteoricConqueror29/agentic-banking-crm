from fastapi import APIRouter, Query

from app.models.customer_intelligence import HighValueCustomerFilters
from app.models.recommendation import RecommendationResponse
from app.services.duckdb_service import DuckDBService
from app.tools.customer_tool import CustomerIntelligenceTool
from app.tools.recommendation_tool import RecommendationTool
from app.tools.transaction_tool import TransactionAnalysisTool

router = APIRouter()


@router.get("/")
def health_check():
    return {
        "status": "success",
        "message": "Agentic Banking CRM running"
    }


db_service = DuckDBService(auto_initialize=True)
customer_tool = CustomerIntelligenceTool(db_service)
transaction_tool = TransactionAnalysisTool(db_service)
recommendation_tool = RecommendationTool(customer_tool, transaction_tool)


@router.get("/high-value-customers")
def get_high_value_customers():

    filters = HighValueCustomerFilters(
        min_relationship_score=60,
        min_income=50000,
        min_credit_score=700
    )

    result = customer_tool.find_high_value_customers(filters)

    return result.model_dump()


@router.get("/customers/{customer_id}/transaction-analysis")
def get_customer_transaction_analysis(
    customer_id: str,
    top_categories: int = Query(5, ge=0, le=50),
):
    """Return structured transaction metrics and behavioral indicators for one customer."""
    result = transaction_tool.analyze_customer_transactions(
        customer_id,
        top_categories=top_categories,
    )
    return result.model_dump()


@router.get("/customers/{customer_id}/recommendations", response_model=RecommendationResponse)
def get_customer_recommendations(customer_id: str):
    """Generate explainable product recommendations for one customer."""
    result = recommendation_tool.generate_recommendations(customer_id)
    return result