import pytest
from fastapi.testclient import TestClient

from open_scout.api import create_app
from open_scout.config import Settings
from open_scout.search import Engine
from open_scout.store import Store


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, api_key="", neural=False, _env_file=None)


@pytest.fixture
def engine(settings):
    return Engine(Store(settings.data_dir), settings)


@pytest.fixture
def docs(engine):
    values = [
        {
            "url": "https://python.org/guide",
            "domain": "python.org",
            "title": "Python guide",
            "text": "Python is a programming language used for software, data science, "
            "and automation.",
        },
        {
            "url": "https://docs.python.org/async",
            "domain": "docs.python.org",
            "title": "Asynchronous programming",
            "text": "Python asyncio supports concurrent programming. "
            "Coroutines and tasks allow network operations to run together.",
        },
        {
            "url": "https://garden.example/",
            "domain": "garden.example",
            "title": "Growing tomatoes",
            "text": "Tomato plants need sunlight, fertile soil, and water. "
            "Grow healthy vegetables.",
        },
    ]
    return [engine.index(doc) for doc in values]


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        yield client
