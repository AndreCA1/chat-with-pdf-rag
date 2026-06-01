import os
from dotenv import load_dotenv

load_dotenv()

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
DOCUMENT_PATH = "chat-with-pdf-rag/documentos/curriculo.pdf"

OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY")
    
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

LLM_MODEL = "meta-llama/llama-3-8b-instruct"

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

SYSTEM_PROMPT = (
    "Você é um assistente prestativo. "
    "Use os seguintes pedaços de contexto recuperado para responder à pergunta. "
    "Se não souber a resposta, diga que não sabe. "
    "\n\n"
    "{context}"
)