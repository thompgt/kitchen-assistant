"""Tests for scripts/setup_vector_search.py — no network, no API key.

The point of the lazy client is that importing this script (and calling the
pure helpers in it) never touches the API, so these tests deliberately run
with GOOGLE_API_KEY unset.
"""
import json
from types import SimpleNamespace
from typing import List

import pytest

import scripts.setup_vector_search as svs
from scripts.setup_vector_search import build_document, get_embeddings


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(svs, "_client", None)


class FakeModels:
    def __init__(self, vectors: List[List[float]]):
        self._vectors = vectors
        self.calls = []

    def embed_content(self, *, model, contents, config):
        self.calls.append(contents)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=v) for v in self._vectors])


class FakeClient:
    def __init__(self, vectors: List[List[float]]):
        self.models = FakeModels(vectors)


def test_import_does_not_build_a_client():
    """Module import must not require a key; the client starts unbuilt."""
    assert svs._client is None


def test_get_embeddings_empty_never_builds_a_client():
    assert get_embeddings([]) == []
    assert svs._client is None


def test_get_embeddings_uses_injected_client():
    fake = FakeClient([[0.1, 0.2], [0.3, 0.4]])
    vectors = get_embeddings(["a", "b"], client=fake)
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert fake.models.calls == [["a", "b"]]
    # Injection must not fall through to the real, keyless client.
    assert svs._client is None


def test_get_client_is_cached(monkeypatch):
    built = []

    def fake_ctor(*, api_key):
        built.append(api_key)
        return SimpleNamespace(api_key=api_key)

    monkeypatch.setattr(svs.genai, "Client", fake_ctor)
    first = svs.get_client()
    second = svs.get_client()
    assert first is second
    assert len(built) == 1


def test_build_document_omits_json_keys_and_includes_steps():
    ingredients = json.dumps([{"name": "Arborio Rice", "amount": 1, "unit": "cup"}])
    steps = json.dumps([{"step_number": 1, "instruction": "Saute the onions."}])
    document = build_document("Mushroom Risotto", ingredients, steps)
    assert "Mushroom Risotto" in document
    assert "Arborio Rice" in document
    assert "Saute the onions." in document
    assert '"name"' not in document
    assert "amount" not in document
