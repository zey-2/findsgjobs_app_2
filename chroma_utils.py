# chroma_utils.py

from typing import List, Dict
from chroma_setup import jobs_collection


def _chunk_text(text: str, max_chars: int = 800) -> list[str]:
    text = text or ""
    if not text:
        return [""]

    chunks = [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
    return chunks or [""]


def upsert_jobs_into_chroma(jobs: List[Dict]) -> None:
    """
    Upsert a list of FULL job dicts (inner 'job' objects from backend) into Chroma.

    We:
      - Derive a logical job_id from sid / job_sid / id / JobID (NO Title fallback).
      - If those are missing, use a synthetic 'job-{row_index}'.
      - Use job_id ONLY in metadata.
      - Build UNIQUE document IDs using job_id + row index + chunk index.
    """

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[Dict] = []

    for row_idx, job in enumerate(jobs):
        # ---------- Logical job_id for metadata ----------
        logical_id = (
            job.get("sid")
            or job.get("job_sid")
            or job.get("id")
            or job.get("JobID")
        )
        if logical_id is None:
            logical_id = f"job-{row_idx}"  # synthetic but unique per call

        job_id = str(logical_id)  # stored in metadata only

        # ---------- Basic fields ----------
        title = job.get("Title") or job.get("JobTitle") or ""
        company = (
            job.get("CompanyName")
            or job.get("company_name")
            or job.get("company")
            or ""
        )
        location = job.get("JobLocation") or job.get("Location") or ""
        salary = (
            job.get("SalaryDisplay") or job.get("SalaryText") or job.get("salary") or ""
        )
        url = job.get("JobURL") or job.get("JobUrl") or job.get("url") or ""

        description = job.get("JobDescription") or job.get("Description") or ""
        requirements = job.get("JobRequirement") or job.get("Requirement") or ""

        full_text = f"""
        {title}
        Company: {company}
        Location: {location}
        Salary: {salary}

        Requirements:
        {requirements}

        Description:
        {description}
        """

        chunks = _chunk_text(full_text)

        for chunk_idx, chunk in enumerate(chunks):
            # ---------- UNIQUE document ID ----------
            # row_idx ensures uniqueness even if two jobs share the same sid.
            doc_id = f"{job_id}-row{row_idx}-chunk{chunk_idx}"

            ids.append(doc_id)
            documents.append(chunk.strip())
            metadatas.append(
                {
                    "job_id": job_id,   # logical job id
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary": salary,
                    "url": url,
                }
            )

    if ids:
        jobs_collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
