# chroma_search.py

from typing import List, Dict


def search_jobs(keyword: str, top_k: int = 50) -> List[Dict]:
    """
    Keyword-based search using SQLite database.
    Returns unique job records (deduped by job_id).
    """

    # Lazy import so that this file can be imported
    # even if chroma_setup has a problem.
    try:
        from chroma_setup import jobs_collection
    except Exception as e:
        # This makes the REAL error visible in Streamlit
        raise RuntimeError(f"Error importing jobs_collection from chroma_setup: {e}")

    keyword = (keyword or "").strip()
    if not keyword:
        return []

    # Query Chroma for semantic similarity
    result = jobs_collection.query(
        query_texts=[keyword],
        n_results=top_k,
    )

    # When no results exist
    if "metadatas" not in result or not result["metadatas"]:
        return []

    metadatas = result["metadatas"][0]  # First query

    seen = set()
    jobs: List[Dict] = []

    for md in metadatas:
        job_id = md.get("job_id")
        if not job_id:
            continue

        if job_id in seen:
            continue

        seen.add(job_id)

        jobs.append({
            "job_id": job_id,
            "title": md.get("title", ""),
            "company": md.get("company", ""),
            "location": md.get("location", ""),
            "salary": md.get("salary", ""),
            "url": md.get("url", ""),
        })

    return jobs
