import re
from typing import List, Dict, Tuple

import pandas as pd
import streamlit as st

from api_client import fetch_jobs_from_endpoint
from chroma_utils import upsert_jobs_into_chroma
from chroma_search import search_jobs


# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="FindSGJobs Search + Resume Gap Analysis",
    page_icon="🔍",
    layout="wide",
)

# ---------------- SESSION STATE INIT ----------------
for key, default in [
    ("full_jobs", []),           # list of full backend job dicts (inner "job")
    ("flat_jobs", []),           # simplified rows for UI table
    ("selected_job_idx", None),  # index into full_jobs / flat_jobs
    ("resume_text", ""),         # extracted text from uploaded resume
    ("analysis_text", ""),       # gap analysis + course recommendation
    ("job_match_pct", None),     # overall job match %
    ("skill_coverage_pct", None),
    ("keyword_coverage_pct", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------- HELPER FUNCTIONS ----------------
STOPWORDS = {
    "and", "the", "with", "for", "to", "of", "in", "on", "a", "an", "or",
    "be", "as", "by", "is", "are", "will", "able", "etc", "any", "all",
    "job", "role", "responsible", "responsibilities", "requirement",
    "requirements", "candidate", "candidates", "ability", "strong", "good",
    "skills", "experience", "experiences", "year", "years"
}


def extract_keywords(text: str, min_len: int = 3) -> set:
    tokens = re.findall(r"[A-Za-z]{%d,}" % min_len, text.lower())
    return {t for t in tokens if t not in STOPWORDS}


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def get_job_description_text(job: Dict) -> str:
    """Try multiple variants that might hold the job description."""
    candidates = ["JobDescription", "Description", "job_description", "jobDesc"]
    for key in candidates:
        val = job.get(key)
        if val:
            if isinstance(val, dict):
                for sub in ["caption", "value", "text", "description"]:
                    subval = val.get(sub)
                    if isinstance(subval, str) and subval.strip():
                        return subval
            elif isinstance(val, str):
                return val
    return ""


def extract_requirements_from_description(description: str) -> str:
    """Heuristic: pull out the 'Requirements' / 'Qualifications' section from a blob JD."""
    if not description:
        return ""

    text = description.replace("\r", "\n")

    # headings commonly used in SG JDs
    heading_pattern = r"(requirements|requirement|qualifications|about you|what you bring|who you are)"
    parts = re.split(heading_pattern, text, flags=re.IGNORECASE)

    # parts = [before, heading1, after1, heading2, after2, ...]
    if len(parts) < 3:
        return ""

    # take the first heading's content
    requirements_section = parts[2]

    # stop at next all-caps / colon / obvious header style if present
    requirements_section = re.split(r"\n[A-Z][A-Za-z0-9 /&]{3,}:\s*\n", requirements_section)[0]

    return requirements_section.strip()


def get_job_requirement_text(job: Dict) -> str:
    """
    Extract job requirements, prioritising known keys,
    then fuzzy match on any 'require*' / 'qualif*' keys (recursively),
    then fallback to carving them out of JobDescription.
    """
    if not job:
        return ""

    # 1) Prioritise known keys used previously
    for key in ["id_Job_Requirement", "id_Job_Requirements", "Job_Requirement", "Job_Requirements"]:
        val = job.get(key)
        if val:
            if isinstance(val, list):
                parts = []
                for item in val:
                    if isinstance(item, dict):
                        # try common subfields
                        for sub in [
                            "caption", "value", "text", "requirements",
                            "description", "JobRequirement", "JobRequirements"
                        ]:
                            subval = item.get(sub)
                            if isinstance(subval, str) and subval.strip():
                                parts.append(subval.strip())
                                break
                    elif isinstance(item, str) and item.strip():
                        parts.append(item.strip())
                if parts:
                    return "\n".join(parts)
            elif isinstance(val, dict):
                for sub in [
                    "caption", "value", "text", "requirements",
                    "description", "JobRequirement", "JobRequirements"
                ]:
                    subval = val.get(sub)
                    if isinstance(subval, str) and subval.strip():
                        return subval
            elif isinstance(val, str):
                return val

    # 2) Legacy string-style fields
    candidates = ["JobRequirement", "JobRequirements", "Requirement", "Requirements", "job_requirement"]
    for key in candidates:
        val = job.get(key)
        if val:
            if isinstance(val, dict):
                for sub in ["caption", "value", "text", "requirements"]:
                    subval = val.get(sub)
                    if isinstance(subval, str) and subval.strip():
                        return subval
            elif isinstance(val, str):
                return val

    # 3) Fuzzy recursive search: any key that *looks like* requirements / qualifications
    texts: List[str] = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                k_low = k.lower()
                # keys like: id_Job_Requirement, RequirementDetail, candidateRequirements, minQualifications, AboutYou, etc.
                if any(tok in k_low for tok in ["require", "qualif", "about you", "what you bring", "who you are"]):
                    if isinstance(v, str) and v.strip():
                        texts.append(v.strip())
                    elif isinstance(v, (dict, list)):
                        walk(v)
                else:
                    if isinstance(v, (dict, list)):
                        walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(job)

    if texts:
        # de-duplicate while preserving order
        seen = set()
        uniq = []
        for t in texts:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        return "\n".join(uniq)

    # 4) Fallback: carve from JobDescription blob
    desc = get_job_description_text(job)
    return extract_requirements_from_description(desc) or ""


def normalise_skill_text(s: str) -> str:
    """Lowercase and strip most punctuation for matching."""
    return re.sub(r"[^a-z0-9+.# ]", " ", s.lower()).strip()


def match_job_resume_skills(job_skills: List[str], resume_text: str) -> Tuple[List[str], List[str]]:
    """
    Match job skills (from id_Job_Skills) against resume text.
    Returns (matched_skills, missing_skills).
    """
    resume_norm = resume_text.lower()
    matched = []
    missing = []

    for raw_skill in job_skills:
        skill_str = str(raw_skill).strip()
        if not skill_str:
            continue
        skill_norm = normalise_skill_text(skill_str)
        if not skill_norm:
            continue

        # direct phrase match first
        is_match = skill_norm in resume_norm

        # fallback: any token > 2 chars appears
        if not is_match:
            tokens = [t for t in skill_norm.split() if len(t) > 2]
            if any(t in resume_norm for t in tokens):
                is_match = True

        if is_match:
            matched.append(skill_str)
        else:
            missing.append(skill_str)

    return matched, missing


def build_job_resume_overlap(job_text: str, resume_text: str):
    job_kw = extract_keywords(job_text)
    cv_kw = extract_keywords(resume_text)

    overlap = sorted(job_kw & cv_kw)
    gaps = sorted(job_kw - cv_kw)

    return job_kw, overlap, gaps


def generate_gap_analysis_text(
    job: Dict,
    resume_text: str,
    matched_skills: List[str],
    missing_skills: List[str],
    keyword_overlap: List[str],
    keyword_gaps: List[str],
    job_kw_total: int,
    skill_coverage: int,
    keyword_coverage: int,
) -> str:
    """
    More structured analysis based on:
    - JD + JR + Skills keywords
    - Skill matches/gaps
    - Coverage percentages
    """

    title = job.get("Title", "this role")

    total_skills = len(matched_skills) + len(missing_skills)
    # already computed coverage, but we re-use it here
    core_strengths = matched_skills[:5] or keyword_overlap[:5]
    core_gaps = missing_skills[:5] or keyword_gaps[:5]

    strengths_str = ", ".join(core_strengths) if core_strengths else "general related experience"
    gaps_str = ", ".join(core_gaps) if core_gaps else "no obvious gaps based on the text alone"

    lines = []

    # Overview
    lines.append(
        f"For the **{title}** role, your resume appears to cover roughly "
        f"**{skill_coverage}%** of the explicit skills and about "
        f"**{keyword_coverage}%** of the main themes in the job description and requirements."
    )

    # Strengths section
    lines.append("")
    lines.append("**Where you are aligned**")
    if core_strengths:
        lines.append(
            f"- Your profile shows solid exposure to: **{strengths_str}**. "
            "These map well to what the JD and JR emphasise."
        )
    else:
        lines.append(
            "- The text overlap is limited, but there are still some relevant experiences that could be reframed to match the posting more directly."
        )

    # Gaps section
    lines.append("")
    lines.append("**Key gaps or under-emphasised areas**")
    if core_gaps:
        lines.append(
            f"- The job text and skill list highlight: **{gaps_str}**. "
            "These either do not appear clearly in your resume or are only implied."
        )
    else:
        lines.append(
            "- There are no obvious missing keywords, but you may still want to sharpen how specific tools, domains and results are described."
        )

    # Actionable recommendations
    lines.append("")
    lines.append("**How to strengthen your fit**")
    if missing_skills:
        lines.append(
            f"- Add or expand bullet points that explicitly mention the missing skills "
            f"(**{', '.join(missing_skills[:5])}**), ideally with metrics or outcomes "
            "(e.g. response time, revenue, cost savings, satisfaction scores)."
        )
    else:
        lines.append(
            "- Your skill set already lines up closely; focus on clearer impact statements (numbers, scale, complexity) for your strongest achievements."
        )

    if keyword_gaps:
        lines.append(
            f"- Several concepts from the JD/JR (e.g. **{', '.join(keyword_gaps[:5])}**) "
            "do not show up clearly. If you have experience in these, bring them forward with concrete examples; "
            "if not, consider small projects or courses to build and demonstrate them."
        )

    lines.append(
        "- Mirror some of the phrasing from the job posting (where truthful) so that applicant tracking systems (ATS) can recognise the match more easily."
    )

    return "\n".join(lines)


def recommend_course(job: Dict, gaps: List[str]) -> str:
    """Return one simple Singapore course recommendation based on title/skills."""
    title = job.get("Title", "").lower()
    skills_val = job.get("id_Job_Skills", []) or []
    if isinstance(skills_val, list):
        skills_text = " ".join(str(s) for s in skills_val)
    else:
        skills_text = str(skills_val)

    req_text = get_job_requirement_text(job)
    text = f"{title} {skills_text} {req_text} {' '.join(gaps)}".lower()

    if any(k in text for k in ["support", "helpdesk", "customer service", "call centre"]):
        return "‘Customer Service Excellence’ — NTUC LearningHub (Singapore, classroom/online)"
    if any(k in text for k in ["data", "analytics", "excel"]):
        return "‘Excel Skills for Business’ — Coursera (online, SkillsFuture claimable)"
    if any(k in text for k in ["admin", "executive", "coordinator"]):
        return "‘Digital Office Skills with Microsoft 365’ — Singapore Polytechnic PACE (short course)"
    if any(k in text for k in ["it", "network", "technician"]):
        return "‘CompTIA A+ Certification Training’ — NTUC LearningHub (Singapore, blended)"
    if any(k in text for k in ["sales", "marketing", "account manager"]):
        return "‘Professional Selling Skills’ — SMU Academy (short executive programme)"

    return "‘Career Resilience & Future Skills’ — SkillsFuture Singapore (online options available)"


def extract_resume_text(uploaded_file) -> str:
    """Extract text from PDF, DOCX, or TXT resume."""
    if uploaded_file is None:
        return ""

    suffix = uploaded_file.name.lower().split(".")[-1]

    if suffix == "txt":
        return uploaded_file.read().decode("utf-8", errors="ignore").strip()

    if suffix in ("docx", "doc"):
        try:
            from docx import Document  # pip install python-docx

            doc = Document(uploaded_file)
            return "\n".join(p.text for p in doc.paragraphs).strip()
        except Exception as e:
            st.error(f"Error reading DOC/DOCX file: {e}")
            return ""

    if suffix == "pdf":
        try:
            from PyPDF2 import PdfReader  # pip install pypdf2

            reader = PdfReader(uploaded_file)
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n".join(pages).strip()
        except Exception as e:
            st.error(f"Error reading PDF file: {e}")
            return ""

    st.warning("Unsupported file type. Please upload PDF, DOCX, DOC, or TXT.")
    return ""


# ---------------- SIDEBAR – JOB SEARCH ----------------
st.sidebar.markdown("### Job Search")

sidebar_job_title = st.sidebar.text_input("Keyword for Job Title", value="support")
sidebar_company = st.sidebar.text_input("Company", value="")
sidebar_min_salary = st.sidebar.number_input("Min Salary", min_value=0, value=0, step=100)
sidebar_mrt = st.sidebar.text_input("Nearest MRT Station", value="")
sidebar_emp_type = st.sidebar.text_input("Min Employment Type", value="")
sidebar_education = st.sidebar.text_input("Education", value="")

if st.sidebar.button("Fetch & store in Chroma"):
    with st.spinner("Calling FindSGJobs backend…"):
        # backend still only takes a keyword; other filters applied client-side
        raw = fetch_jobs_from_endpoint(
            page=1,
            per_page=50,
            keywords=sidebar_job_title,
        )

    with st.expander("🔍 Debug: Raw backend response"):
        st.json(raw)

    wrapped = raw.get("data", {}).get("result", []) if raw else []

    # Optional debug to inspect requirement-like fields in first job
    if wrapped:
        first_job_full = wrapped[0]               # the whole wrapper (item)
        first_job = first_job_full.get("job", {}) # the “job” dictionary inside

        with st.expander("🔍 Debug: Job fields that may contain requirements"):
            st.write("Job-level keys:", list(first_job.keys()))

            st.write("Possible requirement-like fields inside job:")
            for k, v in first_job.items():
                if any(tok in k.lower() for tok in ["require", "qualif", "about", "responsib"]):
                    st.write(f"• {k} → {type(v).__name__}")
                    st.json(v)

            st.write("Wrapper-level keys:", list(first_job_full.keys()))
            st.write("Possible requirement-like fields in wrapper:")
            for k, v in first_job_full.items():
                if any(tok in k.lower() for tok in ["require", "qualif", "about", "responsib"]):
                    st.write(f"• {k} → {type(v).__name__}")
                    st.json(v)

    if not wrapped:
        st.warning("No jobs found in backend response.")
    else:
        full_jobs = []
        flat_jobs = []

        for row_idx, item in enumerate(wrapped):
            job = item.get("job", {}) or {}
            company_obj = item.get("company", {}) or {}
            full_jobs.append(job)

            title = job.get("Title", "") or ""
            company_name = company_obj.get("CompanyName", "") or ""

            # Nearest MRT
            mrt_list = job.get("id_Job_NearestMRTStation", []) or []
            mrt_caps = []
            if isinstance(mrt_list, list):
                for m in mrt_list:
                    if isinstance(m, dict):
                        cap = m.get("caption", "")
                        if cap:
                            mrt_caps.append(cap)
            nearest_mrt = ", ".join(mrt_caps)

            # Salary
            salary_not_display = job.get("id_Job_Donotdisplaysalary", 0)
            salary_range = ""
            min_salary_numeric = None

            if not salary_not_display:
                sr = job.get("Salaryrange") or {}
                currency_obj = job.get("id_Job_Currency") or {}
                interval_obj = job.get("id_Job_Interval") or {}
                currency = currency_obj.get("caption", "SGD")
                interval = interval_obj.get("caption", "Month")
                if isinstance(sr, dict) and sr.get("caption"):
                    salary_range = f"{currency} {sr['caption']} per {interval}"
                    nums = re.findall(r"\d[\d,]*", sr["caption"])
                    if nums:
                        min_salary_numeric = int(nums[0].replace(",", ""))
                else:
                    min_sal = job.get("id_Job_Salary")
                    max_sal = job.get("id_Job_MaxSalary")
                    if min_sal:
                        try:
                            min_salary_numeric = int(min_sal)
                        except Exception:
                            pass
                    if min_sal and max_sal:
                        salary_range = f"{currency} {min_sal}–{max_sal} per {interval}"
                    elif min_sal:
                        salary_range = f"{currency} {min_sal}+ per {interval}"
                    elif max_sal:
                        salary_range = f"{currency} up to {max_sal} per {interval}"

            # Employment type
            emp_list = job.get("EmploymentType", []) or []
            emp_caps = []
            if isinstance(emp_list, list):
                for et in emp_list:
                    if isinstance(et, dict):
                        cap = et.get("caption", "")
                        if cap:
                            emp_caps.append(cap)
            employment_type = ", ".join(emp_caps)

            # Min education & experience
            min_edu_obj = job.get("MinimumEducationLevel") or {}
            min_exp_obj = job.get("MinimumYearsofExperience") or {}
            min_edu = min_edu_obj.get("caption", "") or ""
            min_exp = min_exp_obj.get("caption", "") or ""

            # Skills from id_Job_Skills
            skills = job.get("id_Job_Skills", []) or []
            if isinstance(skills, list):
                skills_str = ", ".join(str(s) for s in skills)
            else:
                skills_str = str(skills)

            # Separate JD + JR
            desc_html = get_job_description_text(job)
            req_html = get_job_requirement_text(job)
            desc_plain = strip_html(desc_html)
            req_plain = strip_html(req_html)

            flat_jobs.append(
                {
                    "job_id": str(job.get("sid") or job.get("id") or f"job-{row_idx}"),
                    "Title": title,
                    "Company": company_name,
                    "Nearest MRT": nearest_mrt,
                    "Salary Range": salary_range,
                    "Employment Type": employment_type,
                    "Min Education": min_edu,
                    "Min Experience": min_exp,
                    "Skills": skills_str,
                    "Job Description": desc_plain,
                    "Job Requirements": req_plain,
                    "Min Salary (numeric)": min_salary_numeric,
                }
            )

        # Apply sidebar filters client-side
        df_all = pd.DataFrame(flat_jobs)

        if sidebar_company:
            df_all = df_all[
                df_all["Company"].str.contains(sidebar_company, case=False, na=False)
            ]
        if sidebar_min_salary > 0 and "Min Salary (numeric)" in df_all.columns:
            df_all = df_all[
                df_all["Min Salary (numeric)"].fillna(0) >= sidebar_min_salary
            ]
        if sidebar_mrt:
            df_all = df_all[
                df_all["Nearest MRT"].str.contains(sidebar_mrt, case=False, na=False)
            ]
        if sidebar_emp_type:
            df_all = df_all[
                df_all["Employment Type"].str.contains(sidebar_emp_type, case=False, na=False)
            ]
        if sidebar_education:
            df_all = df_all[
                df_all["Min Education"].str.contains(sidebar_education, case=False, na=False)
            ]

        # Push filtered result into session state
        st.session_state["full_jobs"] = full_jobs
        st.session_state["flat_jobs"] = df_all.to_dict(orient="records")
        st.session_state["selected_job_idx"] = None
        st.session_state["analysis_text"] = ""
        st.session_state["job_match_pct"] = None
        st.session_state["skill_coverage_pct"] = None
        st.session_state["keyword_coverage_pct"] = None

        upsert_jobs_into_chroma(full_jobs)
        st.success(f"Stored {len(full_jobs)} jobs (chunked) into Chroma (displaying {len(df_all)} after filters).")


# ---------------- GLOBAL STYLES ----------------
st.markdown(
    """
    <style>
    .big-title {font-size: 40px; font-weight: 700;}
    .job-card {padding: 1rem 1.2rem; border-radius: 0.8rem;
               border: 1px solid #eee; margin-bottom: 0.8rem;
               background-color: #fafafa;}
    .job-title {font-size: 20px; font-weight: 600; margin-bottom: 0.2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="big-title">🔍 FindSGJobs Search + Resume Gap Analysis</div>',
    unsafe_allow_html=True,
)
st.caption("Fetch jobs from the backend API, store them in Chroma, then match them against your resume.")


# ---------------- MAIN LAYOUT ----------------
col_left, col_right = st.columns([2, 1], gap="large")

# ===== LEFT COLUMN: JOB TABLE + SEARCH =====
with col_left:
    st.subheader("Fetched jobs")
    flat_jobs = st.session_state["flat_jobs"]

    if flat_jobs:
        df = pd.DataFrame(flat_jobs)
        display_cols = [
            "Title",
            "Company",
            "Nearest MRT",
            "Salary Range",
            "Employment Type",
            "Min Education",
            "Min Experience",
            "Skills",
            "Job Description",
            "Job Requirements",
        ]
        display_cols = [c for c in display_cols if c in df.columns]

        # show approx 5 rows with scroll
        st.dataframe(
            df[display_cols].fillna(""),
            use_container_width=True,
            hide_index=True,
            height=230,  # tweak if needed
        )

        visible_indices = df.index.tolist()
        selected = st.selectbox(
            "Select job for gap analysis",
            options=visible_indices,
            format_func=lambda i: f"{flat_jobs[i]['Title']} — {flat_jobs[i]['Company']}",
        )
        st.session_state["selected_job_idx"] = selected
    else:
        st.info("Fetch jobs from the sidebar to see them here.")

    # Chroma search (unchanged)
    st.subheader("Search stored jobs (from Chroma)")
    search_kw = st.text_input(
        "Filter by keyword in job title / description",
        value="",
        placeholder="e.g. support, admin, driver…",
    )

    if search_kw.strip():
        search_results = search_jobs(search_kw)
        st.markdown(f"**{len(search_results)} matching jobs found**")
        for md in search_results:
            with st.container():
                st.markdown('<div class="job-card">', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="job-title">{md.get("title", "(No Title)")}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**Company:** {md.get('company', 'N/A')}  \n"
                    f"**Location/MRT:** {md.get('location', 'N/A')}  \n"
                    f"**Salary:** {md.get('salary', 'N/A')}"
                )
                if md.get("url"):
                    st.markdown(f"[View job posting]({md['url']})")
                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("Enter a keyword above to search jobs already stored in Chroma.")


# ===== RIGHT COLUMN: JOB MATCH + GAP ANALYSIS =====
with col_right:
    # --- Job Match % chart ---
    st.subheader("📊 Job Match %")
    match_chart_placeholder = st.empty()

    if isinstance(st.session_state.get("job_match_pct"), int):
        df_match = pd.DataFrame(
            {"Metric": ["Job Match %"], "Value": [st.session_state["job_match_pct"]]}
        ).set_index("Metric")
        match_chart_placeholder.bar_chart(df_match, height=180)
        sc = st.session_state.get("skill_coverage_pct") or 0
        kc = st.session_state.get("keyword_coverage_pct") or 0
        st.caption(f"Skill coverage: {sc}% • Keyword coverage: {kc}%")
    else:
        st.caption("Run a gap analysis to see your Job Match %.")

    st.subheader("📄 Resume Gap Analysis")

    selected_idx = st.session_state["selected_job_idx"]
    full_jobs = st.session_state["full_jobs"]

    if selected_idx is not None and 0 <= selected_idx < len(full_jobs):
        selected_job = full_jobs[selected_idx]
        st.markdown(f"**Selected role:** {selected_job.get('Title', '(No Title)')}")
    else:
        selected_job = None
        st.info("Select a job from the left column first.")

    # Resume upload
    uploaded_resume = st.file_uploader(
        "Upload your resume (PDF / DOCX / DOC / TXT)",
        type=["pdf", "docx", "doc", "txt"],
    )

    if uploaded_resume is not None:
        text = extract_resume_text(uploaded_resume)
        if text:
            st.session_state["resume_text"] = text
            st.success("Resume uploaded and text extracted.")
            with st.expander("Preview extracted resume text"):
                st.text_area("Extracted text", value=text, height=200)
        else:
            st.error("Could not extract text from this resume file.")

    # Run gap analysis
    if selected_job and st.session_state["resume_text"]:
        if st.button("Run gap analysis"):
            with st.spinner("Analysing your resume against the job…"):
                resume_text = st.session_state["resume_text"]

                # Skills
                raw_skills = selected_job.get("id_Job_Skills") or []
                if not isinstance(raw_skills, list):
                    job_skills_list = [str(raw_skills)]
                else:
                    job_skills_list = [str(s) for s in raw_skills]

                matched_skills, missing_skills = match_job_resume_skills(
                    job_skills_list, resume_text
                )

                # Combined JD + JR + Skills for keyword match
                desc_plain = strip_html(get_job_description_text(selected_job))
                req_plain = strip_html(get_job_requirement_text(selected_job))
                combined_job_text = " ".join(
                    [desc_plain, req_plain, " ".join(job_skills_list)]
                )

                job_kw, kw_overlap, kw_gaps = build_job_resume_overlap(
                    combined_job_text, resume_text
                )

                # Coverage metrics
                job_kw_total = len(job_kw)
                total_skills = len(matched_skills) + len(missing_skills)
                skill_coverage = int(
                    round(100 * len(matched_skills) / total_skills)
                ) if total_skills else 0
                keyword_coverage = int(
                    round(100 * len(kw_overlap) / job_kw_total)
                ) if job_kw_total else 0
                match_pct = int(round((skill_coverage + keyword_coverage) / 2))  # simple average

                st.session_state["job_match_pct"] = match_pct
                st.session_state["skill_coverage_pct"] = skill_coverage
                st.session_state["keyword_coverage_pct"] = keyword_coverage

                analysis = generate_gap_analysis_text(
                    selected_job,
                    resume_text,
                    matched_skills,
                    missing_skills,
                    kw_overlap,
                    kw_gaps,
                    job_kw_total=job_kw_total,
                    skill_coverage=skill_coverage,
                    keyword_coverage=keyword_coverage,
                )

                course = recommend_course(selected_job, missing_skills or kw_gaps)

                skills_section = (
                    "**SKILL MATCH OVERVIEW**\n\n"
                    f"- Job skills (from posting): {', '.join(job_skills_list) if job_skills_list else 'Not specified'}\n"
                    f"- Matched skills in your resume: {', '.join(matched_skills) if matched_skills else 'None clearly detected'}\n"
                    f"- Skill gaps to work on: {', '.join(missing_skills) if missing_skills else 'No obvious skill gaps based on text'}\n\n"
                )

                recommendations_section = (
                    "**COURSE RECOMMENDATION**\n\n"
                    f"- Suggested course: {course}\n"
                )

                result = (
                    f"{skills_section}"
                    f"**GAP ANALYSIS (Narrative)**\n\n"
                    f"{analysis}\n\n"
                    f"{recommendations_section}"
                )

                st.session_state["analysis_text"] = result

    if st.session_state["analysis_text"]:
        # Fix f-string with backslash issue by doing replacement outside
        analysis_html = st.session_state["analysis_text"].replace('\n', '<br>')
        st.markdown(
            f"""
            <div style="
                background-color:#f0f7ff;
                padding:20px;
                border-radius:10px;
                border-left:6px solid #2a76d2;
                font-size:15px;
            ">
            {analysis_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.caption("Upload a resume and select a job, then click 'Run gap analysis' to see results here.")
