import json
import subprocess
import sys

import pytest

from siamcare.cli import main


def test_workflow_in_separate_processes(tmp_path):
    database = tmp_path / "processes.sqlite3"

    def run(*args, code=0):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from siamcare.cli import main; raise SystemExit(main())",
                "--database",
                str(database),
                *args,
            ],
            cwd=tmp_path,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == code, result.stderr
        assert "Traceback" not in result.stderr
        if code:
            assert result.stdout == ""
            return result.stderr
        assert "LOCAL SIMULATION" in result.stderr
        return json.loads(result.stdout)

    clinician = ("--actor", "demo-clinician", "--role", "clinician")
    staff = (
        "--actor",
        "demo-staff",
        "--role",
        "hospital_staff",
        "--actor-hospital",
        "H01",
    )
    approver = ("--actor", "demo-physician", "--role", "approver")
    referral = run(
        "referrals",
        "create",
        "--patient",
        "SYN-CLI",
        "--specialty",
        "neurology",
        "--urgency",
        "routine",
        *clinician,
    )
    rid = referral["referral_id"]
    assert [h["hospital_id"] for h in run("referrals", "hospitals", rid)] == [
        "H01",
        "H06",
    ]
    request = run("requests", "send", rid, "--hospital", "H01", *clinician)
    qid = request["request_id"]
    assert run("requests", "list", "--hospital", "H01")[0]["request_id"] == qid
    assert run("requests", "list", "--referral", rid)[0]["request_id"] == qid
    run("requests", "accept", qid, *staff)
    run("referrals", "submit-review", rid, *clinician)
    assert run("referrals", "approve", rid, *approver)["status"] == "approved"
    assert run("referrals", "get", rid)["status"] == "approved"
    assert run("referrals", "list")[0]["referral_id"] == rid
    assert len(run("referrals", "history", rid)) == 5
    assert "expected awaiting_review" in run(
        "referrals", "approve", rid, *approver, code=2
    )
    assert len(run("referrals", "history", rid)) == 5
    assert "not found" in run("referrals", "get", "unknown", code=1)


@pytest.mark.parametrize(
    "args",
    [
        [
            "referrals",
            "create",
            "--patient",
            "SYN",
            "--specialty",
            "neurology",
            "--actor",
            "demo",
            "--role",
            "clinician",
        ],
        [
            "requests",
            "decline",
            "unknown",
            "--actor",
            "demo",
            "--role",
            "hospital_staff",
        ],
        ["referrals", "reject", "unknown", "--actor", "demo", "--role", "approver"],
        ["requests", "list"],
    ],
)
def test_required_arguments(args, tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--database", str(tmp_path / "unused.sqlite3"), *args])
    assert caught.value.code == 2
    assert "required" in capsys.readouterr().err


@pytest.mark.parametrize("role", ["invalid-role", "hospital_staff"])
def test_invalid_demo_identity(role, tmp_path, capsys):
    args = [
        "--database",
        str(tmp_path / "actors.sqlite3"),
        "referrals",
        "create",
        "--patient",
        "SYN",
        "--specialty",
        "neurology",
        "--urgency",
        "routine",
        "--actor",
        "demo",
        "--role",
        role,
    ]
    if role == "invalid-role":
        with pytest.raises(SystemExit) as caught:
            main(args)
        assert caught.value.code == 2
    else:
        assert main(args) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_database_error_is_presented(tmp_path, capsys):
    assert main(["--database", str(tmp_path), "referrals", "list"]) == 2
    output = capsys.readouterr()
    assert "Database operation failed" in output.err
    assert "Traceback" not in output.err
    assert output.out == ""


def test_hospital_commands_do_not_initialize_database(tmp_path, capsys):
    database = tmp_path / "not-created.sqlite3"
    assert main(["--database", str(database), "hospitals", "list"]) == 0
    assert not database.exists()
    assert len(json.loads(capsys.readouterr().out)) == 8
