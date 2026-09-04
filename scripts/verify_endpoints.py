"""Verify application health endpoints directly."""

import os
import sys

# Ensure root workspace directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from httpx import AsyncClient, ASGITransport
from app.api.main import app, lifespan


async def main() -> None:
    print("=== Testing Application Lifespan & Health Endpoints ===")
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. /health/live
            r_live = await client.get("/health/live")
            print(f"GET /health/live  -> Status: {r_live.status_code}, Body: {r_live.json()}")
            assert r_live.status_code == 200
            assert r_live.json()["status"] == "alive"

            # 2. /health/ready
            r_ready = await client.get("/health/ready")
            print(f"GET /health/ready -> Status: {r_ready.status_code}, Body: {r_ready.json()}")

            # 3. /health
            r_health = await client.get("/health")
            print(f"GET /health       -> Status: {r_health.status_code}, Body: {r_health.json()}")

            # 4. /api/health
            r_api = await client.get("/api/health")
            print(f"GET /api/health   -> Status: {r_api.status_code}, Body: {r_api.json()}")
    print("=== Lifespan & Health Endpoint Verification Completed Successfully ===")


if __name__ == "__main__":
    asyncio.run(main())
