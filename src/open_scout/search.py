import re
from threading import Lock
from urllib.parse import urlsplit
from uuid import uuid4

import numpy as np

from .store import chunks


class NeuralUnavailable(RuntimeError):
    pass


class Embedder:
    def __init__(self, settings):
        self.settings = settings
        self.model = None
        self.lock = Lock()

    def load(self):
        if not self.settings.neural:
            raise NeuralUnavailable("Neural search is disabled. Set SCOUT_NEURAL=true and reindex.")
        if self.model is None:
            try:
                from fastembed import TextEmbedding

                self.model = TextEmbedding(
                    model_name=self.settings.model,
                    cache_dir=str(self.settings.data_dir / "models"),
                    threads=2,
                )
            except Exception as exc:
                raise NeuralUnavailable(
                    "Embedding model unavailable. Install the neural extra and run scout reindex."
                ) from exc
        return self.model

    def passages(self, title, text):
        parts = chunks(text)
        with self.lock:
            vectors = list(self.load().passage_embed([f"{title}\n{p}" for p in parts]))
        return list(zip(parts, vectors, strict=True))

    def query(self, text):
        with self.lock:
            return np.asarray(next(self.load().query_embed(text)), dtype=np.float32)


def domain_matches(host, domain):
    domain = domain.strip().lower().rstrip(".")
    if "://" in domain:
        domain = urlsplit(domain).hostname or ""
    return bool(domain) and (host == domain or host.endswith("." + domain))


def highlights(text, query):
    tokens = set(re.findall(r"\w+", query.lower()))
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    ranked = sorted(
        enumerate(sentences),
        key=lambda pair: (-len(tokens.intersection(re.findall(r"\w+", pair[1].lower()))), pair[0]),
    )
    return [s[:500] for _, s in ranked[:3] if s.strip()]


def result(doc, query="", score=0.0, options=None):
    output = {
        "id": doc["id"],
        "url": doc["url"],
        "title": doc["title"],
        "score": round(score, 6),
        "crawledAt": doc["crawled_at"],
    }
    if options is None or options.text:
        output["text"] = doc["text"][: options.maxCharacters if options else 20000]
    if options is None or options.highlights:
        output["highlights"] = highlights(doc["text"], query)
    return output


class Engine:
    def __init__(self, store, settings):
        self.store = store
        self.settings = settings
        self.embedder = Embedder(settings)

    def index(self, doc):
        vectors = (
            self.embedder.passages(doc["title"], doc["text"]) if self.settings.neural else None
        )
        return self.store.put(doc, vectors, self.settings.model)

    def search(self, request, exclude_url=None):
        docs = {
            d["id"]: d
            for d in self.store.documents()
            if d["url"] != exclude_url
            and (
                not request.includeDomains
                or any(domain_matches(d["domain"], host) for host in request.includeDomains)
            )
            and not any(domain_matches(d["domain"], host) for host in request.excludeDomains)
        }
        mode = request.type
        warnings = []
        if mode == "auto":
            mode = "hybrid" if self.settings.neural else "keyword"
        if mode in ("neural", "hybrid"):
            if not self.settings.neural:
                raise NeuralUnavailable(
                    "Neural search is disabled; use keyword or enable the model."
                )
            rows = self.store.vector_rows(self.settings.model)
            covered = {r["document_id"] for r in rows}
            if set(docs) - covered:
                if request.type != "auto":
                    raise NeuralUnavailable("Some pages need embeddings. Run scout reindex first.")
                warnings.append("Some pages lack embeddings; keyword retrieval still covers them.")
        rankings = []
        if mode != "neural":
            rankings.append(self.store.keyword(request.query, docs))
        if mode in ("hybrid", "neural") and docs:
            query = self.embedder.query(request.query)
            query /= max(float(np.linalg.norm(query)), 1e-12)
            scores = {}
            for row in rows:
                doc_id = row["document_id"]
                if doc_id not in docs:
                    continue
                vector = np.frombuffer(row["vector"], dtype=np.float32)
                cosine = float(vector @ query / max(float(np.linalg.norm(vector)), 1e-12))
                scores[doc_id] = max(scores.get(doc_id, -1), cosine)
            rankings.append(sorted(scores, key=lambda key: (-scores[key], key)))
        fused = {}
        for ranking in rankings:
            for rank, doc_id in enumerate(ranking):
                fused[doc_id] = fused.get(doc_id, 0) + 1 / (61 + rank)
        ordered = sorted(fused, key=lambda key: (-fused[key], key))[: request.numResults]
        return {
            "requestId": str(uuid4()),
            "searchType": mode,
            "warnings": warnings,
            "results": [
                result(docs[key], request.query, fused[key], request.contents) for key in ordered
            ],
        }
