# Execução:      uvicorn app.main:app --reload
# Documentação:  http://127.0.0.1:8000/docs

# Os endpoints são funções síncronas de propósito: gerar embeddings e chamar o
# LLM são operações bloqueantes, e o FastAPI executa funções síncronas em um
# pool de threads, sem travar o servidor.

# As sessões do banco ficam abertas só durante as consultas. Assim, nenhuma
# conexão fica presa enquanto os embeddings são gerados ou o LLM responde.

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR
from app.routers import auth, documents, interface

app = FastAPI(
    title="Chat with PDF RAG",
    description="Crie uma conta, envie PDFs e faça perguntas sobre o conteúdo deles.",
    version="2.1.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(interface.router)
app.include_router(auth.router)
app.include_router(documents.router)
