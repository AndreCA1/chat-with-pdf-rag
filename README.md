# Chat with PDF RAG

Sistema de **Retrieval-Augmented Generation (RAG)** utilizando **LangChain**, **ChromaDB** e **OpenAI** para responder perguntas com base no conteúdo de documentos PDF.

O projeto carrega um PDF, divide o texto em chunks, gera embeddings, armazena os vetores no ChromaDB e utiliza um LLM para responder perguntas usando apenas as informações presentes no documento.

---

## Tecnologias Utilizadas

* Python
* LangChain
* OpenAI
* ChromaDB
* PyPDF
* Vector Embeddings
* Retrieval-Augmented Generation (RAG)

---

## Como Funciona

### 1. Carregamento do PDF

O documento é carregado utilizando:

```python
PyPDFLoader
```

### 2. Divisão do Texto

O conteúdo é dividido em pequenos trechos (chunks) utilizando:

```python
RecursiveCharacterTextSplitter
```

Isso permite que o sistema trabalhe com documentos grandes respeitando os limites de contexto do modelo.

### 3. Criação dos Embeddings

Cada chunk é convertido em vetores semânticos utilizando:

```python
OpenAIEmbeddings
```

### 4. Indexação no ChromaDB

Os embeddings são armazenados em um banco vetorial ChromaDB para busca semântica eficiente.

### 5. Recuperação de Contexto

Quando uma pergunta é feita:

* O sistema busca os chunks mais relevantes.
* Recupera os trechos relacionados à pergunta.
* Envia apenas esse contexto ao modelo.

### 6. Geração da Resposta

O modelo gera uma resposta baseada exclusivamente nas informações recuperadas do PDF.

---

## Estrutura do Projeto

```text
chat-with-pdf-rag/
│
├── documentos/
│   └── curriculo.pdf
│
├── main.py
├── chain.py
├── config.py
├── loader.py
├── vectorstore.py
├── requirements.txt
└── README.md
```

---

## Instalação

Clone o repositório:

```bash
git clone https://github.com/AndreCA1/chat-with-pdf-rag.git
```

Entre na pasta:

```bash
cd chat-with-pdf-rag
```

Crie um ambiente virtual:

```bash
python -m venv .venv
```

Ative o ambiente:

### Windows

```bash
.venv\Scripts\activate
```

### Linux

```bash
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

---

## Configuração

Crie um arquivo:

```text
.env
```

Com sua chave da OpenAI:

```env
OPENAI_API_KEY=SUA_CHAVE_AQUI
```

---

## Executando

Adicione um PDF ao projeto e ajuste o caminho no código.

Execute:

```bash
python main.py
```

## Conceitos Demonstrados

* RAG (Retrieval-Augmented Generation)
* Embeddings
* Vector Databases
* Busca Semântica
* LangChain
* ChromaDB
* Processamento de PDFs
* LLM Applications

---

## Objetivo Acadêmico

Este projeto foi desenvolvido como atividade prática para demonstrar a construção de um sistema RAG simples capaz de conversar com documentos PDF utilizando técnicas modernas de Inteligência Artificial Generativa.
