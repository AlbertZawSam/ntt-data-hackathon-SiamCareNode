from siamcare import config
from siamcare.composition import build_hospital_service, build_referral_service


def test_dotenv_path_is_independent_of_working_directory(tmp_path, monkeypatch):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".env").write_text("SIAMCARE_DATABASE_PATH=./data/app.sqlite3\n")
    monkeypatch.setattr(config, "configuration_directory", lambda: backend)
    monkeypatch.delenv("SIAMCARE_DATABASE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    assert config.database_path() == backend / "data/app.sqlite3"


def test_environment_overrides_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SIAMCARE_DATABASE_PATH=ignored.sqlite3\n")
    monkeypatch.setattr(config, "configuration_directory", lambda: tmp_path)
    target = tmp_path / "environment.sqlite3"
    monkeypatch.setenv("SIAMCARE_DATABASE_PATH", str(target))
    assert config.database_path() == target


def test_unconfigured_keeps_existing_default(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "configuration_directory", lambda: tmp_path)
    monkeypatch.delenv("SIAMCARE_DATABASE_PATH", raising=False)
    assert config.database_path() == config.Path.home() / ".siamcare/referrals.sqlite3"


def test_explicit_database_overrides_environment(tmp_path, monkeypatch):
    ignored = tmp_path / "ignored.sqlite3"
    monkeypatch.setenv("SIAMCARE_DATABASE_PATH", str(ignored))
    selected = tmp_path / "selected.sqlite3"
    build_referral_service(build_hospital_service(), selected)
    assert selected.is_file()
    assert not ignored.exists()
