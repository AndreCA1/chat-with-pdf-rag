from config import DOCUMENT_PATH
from loader import load_and_split
from vectorstore import build_retriever
from chain import build_rag_chain

def main():
    print(f"--- Iniciando Sistema RAG ---")
    print(f"Documento alvo: {DOCUMENT_PATH}\n")

    splits = load_and_split(DOCUMENT_PATH)

    retriever = build_retriever(splits)

    rag_chain = build_rag_chain(retriever)


    # perguntas_base = [
    #     "Quais são as principais habilidades desse candidato?",
    #     "Ele tem experiência com Python?"
    # ]

    # for pergunta in perguntas_base:
    #     print(f"\nUsuário: {pergunta}")

    #     resposta = rag_chain.invoke({"input": pergunta})
    #     print(f"Sistema: {resposta['answer']}")
    
    while(True):
        pergunta = input("Digite sua pergunta(ou 'sair' para encerrar): ")
        if pergunta == 'sair': break
        
        resposta = rag_chain.invoke({"input": pergunta})
        print(f"Sistema: {resposta['answer']}")

if __name__ == "__main__":
    main()