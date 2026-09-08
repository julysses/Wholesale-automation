from web.app import frontend_config


def test_frontend_config_uses_vite_values_first(monkeypatch):
    monkeypatch.setenv("VITE_SUPABASE_URL", " https://vite-project.supabase.co ")
    monkeypatch.setenv("VITE_SUPABASE_ANON_KEY", " vite-anon ")
    monkeypatch.setenv("SUPABASE_URL", "https://backend-project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "backend-anon")

    assert frontend_config() == {
        "supabase_url": "https://vite-project.supabase.co",
        "supabase_anon_key": "vite-anon",
    }


def test_frontend_config_falls_back_to_standard_supabase_names(monkeypatch):
    monkeypatch.delenv("VITE_SUPABASE_URL", raising=False)
    monkeypatch.delenv("VITE_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_URL", " https://backend-project.supabase.co ")
    monkeypatch.setenv("SUPABASE_ANON_KEY", " backend-anon ")

    assert frontend_config() == {
        "supabase_url": "https://backend-project.supabase.co",
        "supabase_anon_key": "backend-anon",
    }


def test_blank_vite_values_do_not_hide_backend_config(monkeypatch):
    monkeypatch.setenv("VITE_SUPABASE_URL", "   ")
    monkeypatch.setenv("VITE_SUPABASE_ANON_KEY", "   ")
    monkeypatch.setenv("SUPABASE_URL", "https://backend.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "backend-key")
    assert frontend_config() == {"supabase_url": "https://backend.supabase.co", "supabase_anon_key": "backend-key"}
