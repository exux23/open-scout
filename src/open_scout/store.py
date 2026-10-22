import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime


def now():
    return datetime.now(UTC).isoformat()


def chunks(text, size=1200, overlap=180):
    return [text[i : i + size] for i in range(0, len(text), size - overlap)][:100]


class Store:
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "scout.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                    text TEXT NOT NULL, domain TEXT NOT NULL, crawled_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
                    id UNINDEXED, title, text, tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS vectors (
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, text TEXT NOT NULL, model TEXT NOT NULL,
                    vector BLOB NOT NULL, PRIMARY KEY(document_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, document, vectors=None, model=""):
        doc = dict(document)
        doc["id"] = hashlib.sha256(doc["url"].encode()).hexdigest()[:24]
        doc["crawled_at"] = now()
        with self.connect() as db:
            db.execute("DELETE FROM search WHERE id=?", (doc["id"],))
            db.execute("DELETE FROM vectors WHERE document_id=?", (doc["id"],))
            db.execute(
                """INSERT INTO documents VALUES
                (:id, :url, :title, :text, :domain, :crawled_at)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title, text=excluded.text,
                crawled_at=excluded.crawled_at""",
                doc,
            )
            db.execute(
                "INSERT INTO search VALUES (?, ?, ?)", (doc["id"], doc["title"], doc["text"])
            )
            if vectors:
                db.executemany(
                    "INSERT INTO vectors VALUES (?, ?, ?, ?, ?)",
                    [
                        (doc["id"], i, passage, model, vector.astype("float32").tobytes())
                        for i, (passage, vector) in enumerate(vectors)
                    ],
                )
        return doc

    def get(self, url):
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE url=?", (url,)).fetchone()
            return dict(row) if row else None

    def documents(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM documents ORDER BY url")]

    def delete(self, doc_id):
        with self.connect() as db:
            db.execute("DELETE FROM search WHERE id=?", (doc_id,))
            return db.execute("DELETE FROM documents WHERE id=?", (doc_id,)).rowcount > 0

    def keyword(self, query, allowed):
        tokens = re.findall(r"\w+", query, flags=re.UNICODE)[:64]
        if not tokens:
            return []
        # Quote every token. FTS operators and punctuation are never executable query syntax.
        match = " OR ".join('"' + token + '"' for token in tokens)
        with self.connect() as db:
            rows = db.execute(
                "SELECT id FROM search WHERE search MATCH ? ORDER BY bm25(search, 0, 4, 1)",
                (match,),
            )
            return [r["id"] for r in rows if r["id"] in allowed]

    def vector_rows(self, model):
        with self.connect() as db:
            return list(db.execute("SELECT * FROM vectors WHERE model=?", (model,)))

    def save_job(self, job):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?)", (job["id"], json.dumps(job)))

    def jobs(self):
        with self.connect() as db:
            return [
                json.loads(r["payload"])
                for r in db.execute("SELECT payload FROM jobs ORDER BY rowid DESC LIMIT 100")
            ]

    def stats(self, model):
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM documents").fetchone()[0]
            indexed = db.execute(
                "SELECT count(DISTINCT document_id) FROM vectors WHERE model=?", (model,)
            ).fetchone()[0]
            domains = [
                dict(r)
                for r in db.execute(
                    "SELECT domain, count(*) AS pages FROM documents "
                    "GROUP BY domain ORDER BY pages DESC"
                )
            ]
        return {"documents": total, "embeddedDocuments": indexed, "domains": domains}
