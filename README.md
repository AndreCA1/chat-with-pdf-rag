# Chat with PDF RAG

![Testes](https://github.com/AndreCA1/chat-with-pdf-rag/actions/workflows/tests.yml/badge.svg)

Sistema de **Retrieval-Augmented Generation (RAG)** com API em **FastAPI**, autenticação **JWT** e **PostgreSQL com pgvector**, utilizando **LangChain** e **OpenRouter** para responder perguntas com base no conteúdo de documentos PDF.

O projeto carrega um PDF, divide o texto em chunks, gera embeddings, armazena os vetores no PostgreSQL e utiliza um LLM para responder perguntas usando apenas as informações presentes no documento. Cada usuário acessa somente os próprios documentos.

---

## Tecnologias Utilizadas

* Python
* FastAPI
* PostgreSQL e pgvector
* SQLAlchemy e Alembic
* JWT e Argon2
* Docker Compose
* LangChain
* OpenRouter
* Sentence Transformers
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
HuggingFaceEmbeddings
```

### 4. Indexação no PostgreSQL

Os embeddings são armazenados em uma coluna `vector` do pgvector, vinculados ao documento e ao seu dono.

### 5. Recuperação de Contexto

Quando uma pergunta é feita:

* A API confere se o documento pertence ao usuário.
* O sistema busca, por distância de cosseno, os chunks mais relevantes desse documento.
* Envia apenas esse contexto ao modelo.

### 6. Geração da Resposta

O modelo gera uma resposta baseada exclusivamente nas informações recuperadas do PDF.

---

## Estrutura do Projeto

```text
chat-with-pdf-rag/
├── app/
│   ├── main.py              # cria o FastAPI e registra as rotas
│   ├── config.py            # variáveis e configurações
│   ├── database.py          # engine e sessões
│   ├── dependencies.py      # usuário autenticado
│   ├── models.py            # tabelas do banco
│   ├── schemas.py           # entrada e saída da API
│   ├── security.py          # Argon2 e JWT
│   ├── routers/             # rotas de autenticação, documentos e interface
│   ├── services/            # validação de PDFs e limite de login
│   ├── rag/                 # loader, embeddings, busca e cadeia RAG
│   └── static/              # interface web
├── documentos/
│   └── curriculo.pdf
├── migrations/
├── cli.py                   # modo de terminal
├── alembic.ini
├── docker-compose.yml
├── .env.example
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

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Preencha o `.env` com sua chave do OpenRouter e com valores aleatórios para a senha do banco e o segredo do JWT. A mesma senha deve aparecer em `POSTGRES_PASSWORD` e em `DATABASE_URL`.

Suba o banco e crie as tabelas:

```bash
docker compose up -d --wait
alembic upgrade head
```

---

## Executando a API

```bash
uvicorn app.main:app --reload
```

* **Interface web:** http://127.0.0.1:8000, para criar a conta, enviar, consultar e excluir documentos.
* **Swagger:** http://127.0.0.1:8000/docs. Depois de criar a conta, use o botão **Authorize**, informando o e-mail no campo `username`.

### Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/auth/register` | Cria uma conta |
| `POST` | `/auth/login` | Entra na conta e devolve um token válido por 30 minutos |
| `POST` | `/documents` | Envia e indexa um PDF de até 20 MB |
| `GET` | `/documents` | Lista os documentos do usuário |
| `DELETE` | `/documents/{document_id}` | Exclui um documento e seus trechos indexados |
| `POST` | `/documents/{document_id}/questions` | Faz uma pergunta sobre um documento do usuário |

### Exemplo de uso

Crie a conta:

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "voce@exemplo.com", "password": "sua-senha-segura"}'
```

Entre na conta e guarde o `access_token`:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -d "username=voce@exemplo.com" \
  --data-urlencode "password=sua-senha-segura"
```

Envie um PDF e guarde o `id` retornado:

```bash
curl -X POST http://127.0.0.1:8000/documents \
  -H "Authorization: Bearer SEU_ACCESS_TOKEN" \
  -F "file=@documentos/curriculo.pdf;type=application/pdf"
```

Faça uma pergunta sobre o documento:

```bash
curl -X POST http://127.0.0.1:8000/documents/ID_DO_DOCUMENTO/questions \
  -H "Authorization: Bearer SEU_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Quais são as principais habilidades do candidato?"}'
```

A resposta traz o texto gerado e os trechos usados como fonte:

```json
{
  "answer": "...",
  "sources": [{ "page": 1, "excerpt": "..." }]
}
```

### Controle de acesso

* As senhas são guardadas com hash Argon2.
* Os documentos usam UUIDs aleatórios, e conhecer um deles não dá acesso ao conteúdo: a API verifica o dono a cada pergunta.
* O documento de outra pessoa recebe a mesma resposta `404` de um documento inexistente.
* Um e-mail inexistente e uma senha errada recebem a mesma resposta no login.
* Cada e-mail tem até 10 tentativas de login a cada 15 minutos, e um login bem-sucedido zera a contagem. Acima disso, a API responde `429` com o cabeçalho `Retry-After`.

Em produção, use a API somente com HTTPS.

## Executando no terminal

Este modo mantém os vetores em memória e não usa o PostgreSQL. Ajuste o caminho do PDF em `DOCUMENT_PATH`, no arquivo `app/config.py`, e execute na raiz do projeto:

```bash
python cli.py
```

## Conceitos Demonstrados

* APIs REST com FastAPI
* Autenticação e autorização
* Modelagem relacional e migrações
* RAG (Retrieval-Augmented Generation)
* Embeddings
* Vector Databases
* Busca Semântica
* LangChain
* PostgreSQL e pgvector
* Processamento de PDFs
* LLM Applications

---

## Objetivo Acadêmico

Este projeto foi desenvolvido como atividade prática para demonstrar a construção de um sistema RAG simples capaz de conversar com documentos PDF utilizando técnicas modernas de Inteligência Artificial Generativa.
