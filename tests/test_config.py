from app.config import Settings


def test_default_models_form_a_failover_chain(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings.from_env()
    assert len(settings.gemini_models) >= 2 and settings.gemini_api_key is None


def test_env_can_override_models_and_key(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", " model-a , model-b ,,")
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    settings = Settings.from_env()
    assert settings.gemini_models == ("model-a", "model-b") and settings.gemini_api_key == "secret"


def test_blank_model_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "  ,  ")
    assert Settings.from_env().gemini_models == Settings.gemini_models


def test_default_chain_has_no_duplicates_and_valid_names():
    from app.gemini import GeminiClient
    models = Settings.gemini_models
    assert len(models) == len(set(models))
    GeminiClient("k", models)  # raises if any name is invalid
