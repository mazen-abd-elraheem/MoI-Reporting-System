import asyncio
import httpx
from sqlalchemy import text
from app.core.config import get_settings
from app.core.database import 

settings = get_settings()

async def test_db_connection():
    """Test async connection to Azure SQL"""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar_one()
        print(f"✅ Database connection successful, test query returned: {val}")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")

def test_keyvault_secrets():
    """Check if Key Vault secrets are loaded"""
    missing = []
    for secret_name in ["DATABASE_CONNECTION_STRING", "BLOB_STORAGE_CONNECTION_STRING", "SECRET_KEY"]:
        value = getattr(settings, secret_name, None)
        if not value:
            missing.append(secret_name)
    if missing:
        print(f"✗ Missing Key Vault secrets: {missing}")
    else:
        print("✅ All Key Vault secrets loaded successfully")

async def test_health_endpoint():
    """Optional: test /health if app is deployed"""
    health_url = "http://localhost:8000/health"  # change to deployed URL if testing remotely
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(health_url)
        if resp.status_code == 200:
            print(f"✅ Health endpoint returned: {resp.json()}")
        else:
            print(f"✗ Health endpoint returned status: {resp.status_code}")
    except Exception as e:
        print(f"✗ Health endpoint request failed: {e}")

async def main():
    test_keyvault_secrets()
    await test_db_connection()
    # Uncomment below if you want to test health endpoint locally/deployed
    # await test_health_endpoint()


print("Loaded Key Vault secrets:")
print("DATABASE_CONNECTION_STRING:", settings.DATABASE_CONNECTION_STRING)
print("BLOB_STORAGE_CONNECTION_STRING:", settings.BLOB_STORAGE_CONNECTION_STRING)
print("SECRET_KEY:", settings.SECRET_KEY)

if __name__ == "__main__":
    asyncio.run(main())
