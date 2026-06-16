from steward.config import DEFAULT_BASE_URL, DEFAULT_MODEL, load_qwen_settings


def test_reads_from_env_file(tmp_path, monkeypatch):
    for name in ("QWEN_API_KEY", "QWEN_MODEL", "QWEN_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        'QWEN_API_KEY="sk-test-123"\n# comment line\nQWEN_MODEL=qwen-test\n',
        encoding="utf-8",
    )
    settings = load_qwen_settings(env)
    assert settings.api_key == "sk-test-123"
    assert settings.model == "qwen-test"
    assert settings.base_url == DEFAULT_BASE_URL


def test_process_env_wins_over_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("QWEN_API_KEY=sk-from-file\n", encoding="utf-8")
    monkeypatch.setenv("QWEN_API_KEY", "sk-from-env")
    assert load_qwen_settings(env).api_key == "sk-from-env"


def test_missing_key_is_none_and_defaults_apply(tmp_path, monkeypatch):
    for name in ("QWEN_API_KEY", "QWEN_MODEL", "QWEN_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = load_qwen_settings(tmp_path / ".env")  # file does not exist
    assert settings.api_key is None
    assert settings.model == DEFAULT_MODEL
    assert settings.base_url == DEFAULT_BASE_URL


def test_empty_env_var_overrides_file_key(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("QWEN_API_KEY=sk-from-file\n", encoding="utf-8")
    monkeypatch.setenv("QWEN_API_KEY", "")  # deliberately blanked to force degraded mode
    assert load_qwen_settings(env).api_key is None
