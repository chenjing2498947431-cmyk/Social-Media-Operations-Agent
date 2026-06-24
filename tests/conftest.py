import pytest

from ai_service.core.config import get_settings
from ai_service.tools.llm_client import reload_llm_client
from ai_service.tools.image_gen_api import reload_image_api


@pytest.fixture(autouse=True)
def isolate_settings_cache(monkeypatch):
    monkeypatch.setenv("SHARED_PLATFORM_ENABLED", "false")
    get_settings.cache_clear()
    reload_llm_client()
    reload_image_api()
    yield
    get_settings.cache_clear()
    reload_llm_client()
    reload_image_api()
