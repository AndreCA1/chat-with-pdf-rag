"use strict";

// O token fica na sessionStorage: sobrevive a um recarregamento da página, mas
// é apagado ao fechar a aba. Textos vindos da API são sempre inseridos com
// textContent, para que um nome de arquivo malicioso não execute como HTML.

const TOKEN_KEY = "access_token";
const EMAIL_KEY = "user_email";

const $ = (id) => document.getElementById(id);

let isRegistering = false;
let selectedDocumentId = null;
let documentToDelete = null;

function showMessage(element, message) {
  element.textContent = message;
  element.hidden = !message;
}

function setBusy(button, busy, busyLabel) {
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = busyLabel;
  } else if (button.dataset.label) {
    button.textContent = button.dataset.label;
  }
  button.disabled = busy;
}

class ApiError extends Error {}

async function api(path, options = {}) {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const headers = { ...options.headers };
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiError("Não foi possível conectar ao servidor.");
  }

  if (response.status === 401 && token) {
    endSession("Sua sessão expirou. Entre novamente.");
    throw new ApiError("");
  }
  if (response.status === 204) return null;

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // Erros de validação do FastAPI trazem uma lista em vez de um texto.
    const detail = typeof data?.detail === "string" ? data.detail : null;
    throw new ApiError(detail ?? options.validationMessage ?? "Ocorreu um erro. Tente novamente.");
  }
  return data;
}

function startSession(token, email) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(EMAIL_KEY, email);
  render();
}

function endSession(message = "") {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(EMAIL_KEY);
  selectDocument(null);
  $("document-list").replaceChildren();
  $("password").value = "";
  if ($("delete-dialog").open) $("delete-dialog").close();
  render();
  showMessage($("auth-error"), message);
}

function render() {
  const loggedIn = Boolean(sessionStorage.getItem(TOKEN_KEY));
  $("auth-view").hidden = loggedIn;
  $("app-view").hidden = !loggedIn;
  if (loggedIn) {
    $("user-email").textContent = sessionStorage.getItem(EMAIL_KEY);
    loadDocuments();
  }
}

function setAuthMode(registering) {
  isRegistering = registering;
  $("auth-submit").textContent = registering ? "Criar conta" : "Entrar";
  $("auth-toggle").textContent = registering ? "Já tenho uma conta" : "Criar uma conta";
  $("auth-subtitle").textContent = registering
    ? "Crie sua conta com uma senha de 8 a 128 caracteres."
    : "Entre para acessar seus documentos.";
  $("password").autocomplete = registering ? "new-password" : "current-password";
  showMessage($("auth-error"), "");
}

async function login(email, password) {
  const { access_token: token } = await api("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  $("password").value = "";
  startSession(token, email);
}

async function submitAuth(event) {
  event.preventDefault();
  const email = $("email").value.trim();
  const password = $("password").value;
  showMessage($("auth-error"), "");
  setBusy($("auth-submit"), true, "Aguarde…");
  try {
    if (isRegistering) {
      await api("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        validationMessage: "Informe um e-mail válido e uma senha de 8 a 128 caracteres.",
      });
    }
    await login(email, password);
    setAuthMode(false);
  } catch (error) {
    showMessage($("auth-error"), error.message);
  } finally {
    setBusy($("auth-submit"), false);
  }
}

async function loadDocuments() {
  showMessage($("list-error"), "");
  try {
    renderDocuments(await api("/documents"));
  } catch (error) {
    showMessage($("list-error"), error.message);
  }
}

function renderDocuments(documents) {
  const items = documents.map((doc) => {
    const item = $("document-template").content.firstElementChild.cloneNode(true);
    const name = doc.filename ?? "Documento sem nome";
    item.dataset.id = doc.id;
    item.classList.toggle("selected", doc.id === selectedDocumentId);
    item.querySelector(".filename").textContent = name;
    item.querySelector(".document-date").textContent =
      new Date(doc.created_at).toLocaleString("pt-BR");
    item.querySelector(".document-select").addEventListener("click", () => selectDocument(doc));

    const trash = item.querySelector(".icon-danger");
    trash.title = "Excluir documento";
    trash.setAttribute("aria-label", `Excluir ${name}`);
    trash.addEventListener("click", () => openDeleteDialog(doc, name));
    return item;
  });
  $("document-list").replaceChildren(...items);
  $("empty-list").hidden = documents.length > 0;
}

function selectDocument(doc) {
  selectedDocumentId = doc?.id ?? null;
  $("question-title").textContent = doc ? (doc.filename ?? "Documento sem nome") : "Perguntas";
  $("question-hint").hidden = Boolean(doc);
  $("question-form").hidden = !doc;
  $("question").value = "";
  $("answer").hidden = true;
  showMessage($("question-error"), "");
  document.querySelectorAll(".document").forEach((item) => {
    item.classList.toggle("selected", item.dataset.id === selectedDocumentId);
  });
}

async function submitUpload(event) {
  event.preventDefault();
  const body = new FormData();
  body.append("file", $("file").files[0]);
  showMessage($("upload-error"), "");
  setBusy($("upload-submit"), true, "Enviando…");
  try {
    await api("/documents", { method: "POST", body });
    $("upload-form").reset();
    await loadDocuments();
  } catch (error) {
    showMessage($("upload-error"), error.message);
  } finally {
    setBusy($("upload-submit"), false);
  }
}

function openDeleteDialog(doc, name) {
  documentToDelete = doc;
  $("delete-filename").textContent = name;
  showMessage($("delete-error"), "");
  $("delete-dialog").showModal();
}

async function confirmDelete() {
  showMessage($("delete-error"), "");
  setBusy($("delete-confirm"), true, "Excluindo…");
  try {
    await api(`/documents/${documentToDelete.id}`, { method: "DELETE" });
    if (documentToDelete.id === selectedDocumentId) selectDocument(null);
    $("delete-dialog").close();
    await loadDocuments();
  } catch (error) {
    showMessage($("delete-error"), error.message);
  } finally {
    setBusy($("delete-confirm"), false);
  }
}

async function submitQuestion(event) {
  event.preventDefault();
  const documentId = selectedDocumentId;
  showMessage($("question-error"), "");
  $("answer").hidden = true;
  setBusy($("question-submit"), true, "Consultando…");
  try {
    const result = await api(`/documents/${documentId}/questions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: $("question").value }),
      validationMessage: "Escreva uma pergunta de até 2000 caracteres.",
    });
    // Ignora a resposta se o usuário trocou de documento durante a consulta.
    if (documentId !== selectedDocumentId) return;
    $("answer-text").textContent = result.answer;
    $("sources").replaceChildren(...result.sources.map((source) => {
      const item = document.createElement("li");
      const page = source.page ? `Página ${source.page}: ` : "";
      item.textContent = `${page}${source.excerpt}`;
      return item;
    }));
    $("answer").hidden = false;
  } catch (error) {
    if (documentId === selectedDocumentId) showMessage($("question-error"), error.message);
  } finally {
    setBusy($("question-submit"), false);
  }
}

$("auth-form").addEventListener("submit", submitAuth);
$("auth-toggle").addEventListener("click", () => setAuthMode(!isRegistering));
$("logout").addEventListener("click", () => endSession());
$("upload-form").addEventListener("submit", submitUpload);
$("question-form").addEventListener("submit", submitQuestion);
$("delete-cancel").addEventListener("click", () => $("delete-dialog").close());
$("delete-confirm").addEventListener("click", confirmDelete);

render();
