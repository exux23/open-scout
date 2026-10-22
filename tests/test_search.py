import numpy as np
import pytest

from open_scout.schemas import SearchRequest
from open_scout.search import NeuralUnavailable, domain_matches
from open_scout.store import Store


def test_keyword_and_persistence(engine, docs, settings):
    found = engine.search(SearchRequest(query="Python"))
    assert {r["url"] for r in found["results"]} == {d["url"] for d in docs[:2]}
    assert found["searchType"] == "keyword"
    assert Store(settings.data_dir).get(docs[0]["url"])["text"] == docs[0]["text"]


def test_filter_before_limit(engine, docs):
    found = engine.search(
        SearchRequest(query="Python", includeDomains=["docs.python.org"], numResults=1)
    )
    assert found["results"][0]["url"] == docs[1]["url"]
    found = engine.search(SearchRequest(query="Python", excludeDomains=["python.org"]))
    assert found["results"] == []
    assert domain_matches("docs.python.org", "python.org")
    assert not domain_matches("evilpython.org", "python.org")


@pytest.mark.parametrize("query", ['" OR * NOT : ( )', "---", "🙂", "' OR 1=1 --"])
def test_untrusted_fts_syntax(engine, docs, query):
    assert isinstance(engine.search(SearchRequest(query=query))["results"], list)


def test_upsert_and_delete_remove_stale_index(engine, docs):
    old = docs[0]
    engine.index(
        {
            **old,
            "text": "Completely revised page about sailing and marine navigation.",
            "title": "Sailing",
        }
    )
    assert len(engine.search(SearchRequest(query="Python"))["results"]) == 1
    assert engine.store.delete(old["id"])
    assert engine.search(SearchRequest(query="sailing"))["results"] == []


def test_neural_does_not_silently_fallback(engine, docs):
    with pytest.raises(NeuralUnavailable):
        engine.search(SearchRequest(query="programming", type="neural"))


def test_neural_retrieval_and_hybrid_fusion(engine, docs, monkeypatch):
    engine.settings.neural = True
    model = engine.settings.model
    for i, doc in enumerate(docs):
        vector = np.array([1, 0] if i < 2 else [0, 1], dtype=np.float32)
        engine.store.put(doc, [(doc["text"], vector)], model)
    monkeypatch.setattr(engine.embedder, "query", lambda _: np.array([0, 1], dtype=np.float32))
    found = engine.search(SearchRequest(query="growing food", type="neural"))
    assert found["results"][0]["url"] == docs[2]["url"]
    hybrid = engine.search(SearchRequest(query="tomato", type="hybrid"))
    assert hybrid["results"][0]["url"] == docs[2]["url"]
    assert hybrid["results"][0]["score"] > hybrid["results"][1]["score"]
    engine.store.delete(docs[2]["id"])
    assert len(engine.store.vector_rows(model)) == 2


def test_incomplete_neural_index_is_explicit(engine, docs):
    engine.settings.neural = True
    with pytest.raises(NeuralUnavailable, match="reindex"):
        engine.search(SearchRequest(query="test", type="hybrid"))


def test_contents_options_and_source_exclusion(engine, docs):
    request = SearchRequest(query="Python", contents={"text": False, "highlights": False})
    data = engine.search(request, exclude_url=docs[0]["url"])
    assert len(data["results"]) == 1
    assert "text" not in data["results"][0]
    assert "highlights" not in data["results"][0]
