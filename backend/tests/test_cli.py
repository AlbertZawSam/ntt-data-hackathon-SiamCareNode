import json

import pytest

from siamcare.cli import main


def test_default_from_another_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["hospitals", "list"]) == 0
    captured = capsys.readouterr()
    assert len(json.loads(captured.out)) == 8
    assert "do not guarantee admission" in captured.err


def test_custom_dataset(record, write_dataset, capsys):
    path = write_dataset([{**record, "hospital_id": "CUSTOM"}])
    assert main(["--dataset", str(path), "hospitals", "get", "CUSTOM"]) == 0
    assert json.loads(capsys.readouterr().out)["hospital_id"] == "CUSTOM"


@pytest.mark.parametrize(
    ("args", "code", "message"),
    [
        (["hospitals", "get", "missing"], 1, "not found"),
        (
            [
                "hospitals",
                "search",
                "--specialty",
                "neurology",
                "--min-free-beds",
                "-1",
            ],
            2,
            "nonnegative integer",
        ),
        (["--dataset", "missing.json", "hospitals", "list"], 2, "Cannot load"),
    ],
)
def test_errors(args, code, message, capsys):
    assert main(args) == code
    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err


def test_empty_search(capsys):
    assert main(["hospitals", "search", "--specialty", ""]) == 0
    assert json.loads(capsys.readouterr().out) == []
