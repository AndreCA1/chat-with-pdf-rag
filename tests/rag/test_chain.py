import pytest
from langchain_core.documents import Document

from app.config import LLM_MODEL, OPENROUTER_BASE_URL
from app.rag import chain as chain_module
from app.rag.chain import build_rag_chain
from app.rag.vectorstore import build_retriever


@pytest.fixture
def rag_chain():
    return build_rag_chain(
        build_retriever(
            [
                Document(page_content="Os gatos dormem muito."),
                Document(page_content="Os cachorros latem alto."),
            ]
        )
    )


def test_llm_is_configured_for_openrouter(rag_chain):
    arguments = chain_module.ChatOpenAI.call_args.kwargs

    assert arguments["model"] == LLM_MODEL
    assert arguments["openai_api_base"] == OPENROUTER_BASE_URL
    assert arguments["openai_api_key"] == "chave-falsa"


def test_chain_returns_the_llm_answer(rag_chain):
    assert rag_chain.invoke({"input": "gatos"})["answer"] == "Resposta de teste."


def test_chain_returns_the_chunks_used_as_context(rag_chain):
    context = rag_chain.invoke({"input": "gatos"})["context"]
    assert context[0].page_content == "Os gatos dormem muito."


def test_prompt_contains_the_instructions_context_and_question(rag_chain, fake_llm):
    rag_chain.invoke({"input": "O que fazem os gatos?"})

    system_message, human_message = fake_llm.received[0]
    assert "assistente prestativo" in system_message.content
    assert "Os gatos dormem muito." in system_message.content
    assert human_message.content == "O que fazem os gatos?"


def test_chain_propagates_llm_errors(rag_chain, fake_llm):
    fake_llm.error = RuntimeError("falha no provedor")

    with pytest.raises(RuntimeError, match="falha no provedor"):
        rag_chain.invoke({"input": "gatos"})
