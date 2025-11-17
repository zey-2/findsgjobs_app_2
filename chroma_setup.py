# chroma_setup.py - Simplified version without sentence-transformers
import sqlite3
import os

DB_PATH = "chroma_jobs/jobs.db"

# Ensure directory exists
os.makedirs("chroma_jobs", exist_ok=True)

# Initialize SQLite database
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# Create table if it doesn't exist
cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        job_id TEXT,
        title TEXT,
        company TEXT,
        location TEXT,
        salary TEXT,
        url TEXT,
        document TEXT,
        UNIQUE(job_id, id)
    )
""")
conn.commit()

# Simple in-memory collection interface to match the old API
class SimpleJobsCollection:
    def __init__(self, db_conn):
        self.conn = db_conn
        self.cursor = db_conn.cursor()
    
    def query(self, query_texts, n_results=50):
        """
        Simple keyword-based search instead of semantic embeddings.
        Searches in title, company, and document text.
        """
        if not query_texts or not query_texts[0].strip():
            return {"metadatas": [[]]}
        
        search_term = query_texts[0].lower().strip()
        
        # Simple keyword search using LIKE
        self.cursor.execute("""
            SELECT DISTINCT job_id, title, company, location, salary, url
            FROM jobs
            WHERE LOWER(title) LIKE ? OR LOWER(company) LIKE ? OR LOWER(document) LIKE ?
            LIMIT ?
        """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%", n_results))
        
        rows = self.cursor.fetchall()
        
        # Format results to match ChromaDB's structure
        metadatas = []
        for row in rows:
            metadatas.append({
                "job_id": row[0],
                "title": row[1] or "",
                "company": row[2] or "",
                "location": row[3] or "",
                "salary": row[4] or "",
                "url": row[5] or "",
            })
        
        return {"metadatas": [metadatas]}
    
    def upsert(self, ids, documents, metadatas):
        """
        Insert or update job records in SQLite.
        """
        for doc_id, document, metadata in zip(ids, documents, metadatas):
            self.cursor.execute("""
                INSERT OR REPLACE INTO jobs (id, job_id, title, company, location, salary, url, document)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                metadata.get("job_id", ""),
                metadata.get("title", ""),
                metadata.get("company", ""),
                metadata.get("location", ""),
                metadata.get("salary", ""),
                metadata.get("url", ""),
                document
            ))
        self.conn.commit()

jobs_collection = SimpleJobsCollection(conn)
