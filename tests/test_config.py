from synapse.config import load


def test_environment_overrides_vault_config(tmp_path, monkeypatch):
    config_path = tmp_path / "synapse.toml"
    config_path.write_text(
        'base_url = "http://from-file/v1"\nmodel = "file-model"\nowner = "Ada"\n'
    )
    monkeypatch.setenv("SYNAPSE_BASE_URL", "http://from-env/v1")
    monkeypatch.setenv("SYNAPSE_MODEL", "env-model")
    monkeypatch.setenv("SYNAPSE_EMBEDDING_MODEL", "env-embedding")

    config = load(config_path)
    assert config.base_url == "http://from-env/v1"
    assert config.model == "env-model"
    assert config.owner == "Ada"
    assert config.embedding_base_url == "http://from-env/v1"
    assert config.embedding_model == "env-embedding"
