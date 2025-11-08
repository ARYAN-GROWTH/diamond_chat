from pydantic_settings import BaseSettings
from pathlib import Path
from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).parent.parent.parent
load_dotenv(ROOT_DIR / '.env')

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = os.getenv(
        'DATABASE_URL',
        'postgresql+asyncpg://diamond_user:StrongPassword123!@postgres-db-16-3-r1.cimgrjr0vadx.ap-south-1.rds.amazonaws.com:5432/diamond-db-dev'
    )
    SCHEMA: str = os.getenv('SCHEMA', 'public')
    TABLE_NAME: str = os.getenv('TABLE_NAME', 'dev_diamond2')
    
    # LLM
    LLM_PROVIDER: str = os.getenv('LLM_PROVIDER', 'openai')
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '')
    EMERGENT_LLM_KEY: str = os.getenv('EMERGENT_LLM_KEY', 'sk-emergent-cFeD3A3Ec70B941491')
    DEFAULT_MODEL: str = os.getenv('DEFAULT_MODEL', 'gpt-4o-mini')
    
    # Query Settings
    DEFAULT_QUERY_LIMIT: int = int(os.getenv('DEFAULT_QUERY_LIMIT', '200'))
    MAX_QUERY_LIMIT: int = int(os.getenv('MAX_QUERY_LIMIT', '1000'))
    
    # CORS
    CORS_ORIGINS: str = os.getenv('CORS_ORIGINS', '*')
    
    class Config:
        env_file = '.env'
        case_sensitive = True

settings = Settings()
