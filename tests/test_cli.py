from unittest.mock import MagicMock

import cli


def run_cli(monkeypatch, answers: list[str]) -> MagicMock:
    chain = MagicMock()
    chain.invoke.return_value = {"answer": "Resposta do terminal."}
    monkeypatch.setattr(cli, "load_and_split", MagicMock(return_value=["trecho"]))
    monkeypatch.setattr(cli, "build_retriever", MagicMock(return_value="retriever"))
    monkeypatch.setattr(cli, "build_rag_chain", MagicMock(return_value=chain))
    typed = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(typed))
    cli.main()
    return chain


def test_sair_ends_without_asking_the_chain(monkeypatch):
    chain = run_cli(monkeypatch, ["sair"])
    chain.invoke.assert_not_called()


def test_question_is_answered_until_the_user_leaves(monkeypatch, capsys):
    chain = run_cli(monkeypatch, ["Qual o tema?", "sair"])

    chain.invoke.assert_called_once_with({"input": "Qual o tema?"})
    assert "Sistema: Resposta do terminal." in capsys.readouterr().out


def test_components_are_connected(monkeypatch):
    run_cli(monkeypatch, ["sair"])

    cli.build_retriever.assert_called_once_with(["trecho"])
    cli.build_rag_chain.assert_called_once_with("retriever")
