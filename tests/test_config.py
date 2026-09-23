from libbyctl.config.settings import Settings


def test_settings_roundtrip(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    monkeypatch.setenv("LIBBYCTL_CONFIG", str(config_path))
    monkeypatch.setenv("LIBBYCTL_DATA_DIR", str(tmp_path / "data"))
    settings = Settings.load()
    settings.preferred_formats = ["ebook", "audiobook"]
    settings.max_concurrency = 3
    settings.save()
    loaded = Settings.load()
    assert loaded.preferred_formats == ["ebook", "audiobook"]
    assert loaded.max_concurrency == 3
