# =============================================================================
# chain.py — Montagem da cadeia RAG (Retrieval-Augmented Generation)
# =============================================================================
# Responsabilidade única: unir o Retriever, o Prompt e o LLM em uma única
# cadeia de execução que aceita uma pergunta e devolve uma resposta embasada
# no documento original.
#
# Diferença em relação à versão OpenAI:
#   O ChatOpenAI é configurado com a base URL e a chave do OpenRouter,
#   tornando-o compatível com qualquer modelo disponível na plataforma.

#from langchain.chains import create_retrieval_chain
#from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, SYSTEM_PROMPT


def build_rag_chain(retriever: object) -> object:
    """
    Constrói e retorna a cadeia RAG completa usando o OpenRouter como LLM.

    Fluxo interno
    -------------
    Pergunta do usuário
        → Retriever busca os chunks mais relevantes no banco vetorial
        → create_stuff_documents_chain injeta esses chunks no Prompt
        → ChatOpenAI (via OpenRouter) gera a resposta fundamentada nos chunks
        → Resposta retorna ao usuário

    Parâmetros
    ----------
    retriever : VectorStoreRetriever
        Retriever criado pelo módulo `vectorstore`.

    Retorna
    -------
    Runnable
        Cadeia RAG invocável com `chain.invoke({"input": "sua pergunta"})`.
    """

    # --- LLM via OpenRouter ---
    # O ChatOpenAI aceita qualquer endpoint compatível com a API da OpenAI.
    # Basta sobrescrever openai_api_base e openai_api_key.
    llm = ChatOpenAI(
        model=LLM_MODEL,
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base=OPENROUTER_BASE_URL,
        # Cabeçalhos opcionais recomendados pelo OpenRouter para identificar
        # seu app no painel de uso deles.
        default_headers={
            "HTTP-Referer": "http://localhost",   # URL do seu site/app
            "X-Title": "RAG LangChain Project",   # Nome exibido no dashboard
        },
    )

    # --- Prompt ---
    # {context} será preenchido automaticamente com os chunks recuperados;
    # {input} receberá a pergunta do usuário.
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
    ])

    # --- Subcadeia de Q&A ---
    # "stuff" = estratégia que concatena todos os chunks num único bloco de
    # contexto. Funciona bem quando os chunks cabem no contexto do LLM.
    question_answer_chain = create_stuff_documents_chain(llm, prompt)

    # --- Cadeia RAG completa ---
    # Une o Retriever (busca) com a subcadeia de Q&A (geração).
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)

    print("[chain] Cadeia RAG montada com sucesso.")
    return rag_chain