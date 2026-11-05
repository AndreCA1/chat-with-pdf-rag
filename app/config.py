import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
DOCUMENT_PATH = "documentos/curriculo.pdf"

OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

LLM_MODEL = "meta-llama/llama-3.1-8b-instruct"

MAX_UPLOAD_SIZE_MB = 20
MAX_QUESTION_LENGTH = 2000

DATABASE_URL = os.getenv("DATABASE_URL")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

MAX_LOGIN_ATTEMPTS = 10
LOGIN_ATTEMPT_WINDOW_MINUTES = 15

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSIONS = 384
RETRIEVER_TOP_K = 4

SYSTEM_PROMPT = (
    "Você é um assistente prestativo. "
    "Use os seguintes pedaços de contexto recuperado para responder à pergunta. "
    "Se não souber a resposta, diga que não sabe. "
    "\n\n"
    "{context}"
)
