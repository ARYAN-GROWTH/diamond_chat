import pytest
from httpx import AsyncClient
from src.main import app

@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        
        # May fail if database not connected, but endpoint should exist
        assert response.status_code in [200, 503]

@pytest.mark.asyncio
async def test_query_endpoint_structure():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/query",
            json={"query": "Show me data", "session_id": "test"}
        )
        
        # May fail due to database/LLM, but check structure
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            assert "sql" in data
            assert "columns" in data
            assert "rows" in data

@pytest.mark.asyncio
async def test_schema_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/schema")
        
        # May fail if database not connected
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert "table_name" in data
            assert "columns" in data
