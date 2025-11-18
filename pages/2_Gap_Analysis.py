"""Job Match and Gap Analysis page."""
import re
import io
from typing import List, Dict, Tuple

import streamlit as st
import os
from dotenv import load_dotenv
from smart_gap_analysis import get_smart_gap_analysis


# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="Gap Analysis - FindSGJobs",
    page_icon="📊",
    layout="wide",
)

# ---------------- SESSION STATE INIT ----------------
# Load .env file so GEMINI/TAVILY keys can be read
load_dotenv()

for key, default in [
    ("full_jobs", []),           # list of full backend job dicts (inner "job")
    ("flat_jobs", []),           # simplified rows for UI table
    ("selected_job_idx", None),  # index into full_jobs / flat_jobs
    ("resume_text", ""),         # extracted text from uploaded resume
    ("analysis_text", ""),       # gap analysis + course recommendation
    ("job_match_pct", None),     # overall job match %
    ("keyword_coverage_pct", None),
    # Removed AI config keys (no sidebar AI settings)
    ("gemini_api_key", os.getenv("GEMINI_API_KEY", "")),
    ("tavily_api_key", os.getenv("TAVILY_API_KEY", "")),
    ("search_tool", "tavily" if os.getenv("TAVILY_API_KEY") else "duckduckgo"),
    ("course_recommendations", ""), # course recommendations
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
    """Extract keywords from text, excluding stopwords."""
    tokens = re.findall(r"[A-Za-z]{%d,}" % min_len, text.lower())
    return {t for t in tokens if t not in STOPWORDS}


def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
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


def build_job_resume_overlap(job_text: str, resume_text: str):
    """Build keyword overlap and gaps between job and resume."""
    job_kw = extract_keywords(job_text)
    cv_kw = extract_keywords(resume_text)

    overlap = sorted(job_kw & cv_kw)
    gaps = sorted(job_kw - cv_kw)

    return job_kw, overlap, gaps


def generate_keyword_only_analysis_text(
    job: Dict,
    resume_text: str,
    keyword_overlap: List[str],
    keyword_gaps: List[str],
    job_kw_total: int,
    keyword_coverage: int,
) -> str:
    """Generate a narrative analysis that focuses purely on
    keyword overlap between the job description and the resume.

    This avoids referencing skills or requirement fields which may
    not be present in the API response.
    """

    title = job.get("Title", "this role")
    core_strengths = keyword_overlap[:5]
    core_gaps = keyword_gaps[:5]

    strengths_str = ", ".join(core_strengths) if core_strengths else "related experience"
    gaps_str = ", ".join(core_gaps) if core_gaps else "no obvious gaps based on text"

    lines: List[str] = []

    # Overview
    lines.append(
        f"For the **{title}** role, your resume covers about **{keyword_coverage}%** "
        f"of the prominent keywords found in the job description."
    )

    # Strengths
    lines.append("")
    lines.append("**Where you are aligned**")
    if core_strengths:
        lines.append(f"- Strong overlap on: **{strengths_str}**.")
    else:
        lines.append("- Limited direct keyword overlap detected. Consider mirroring key terms from the JD where truthful.")

    # Gaps
    lines.append("")
    lines.append("**Potential gaps**")
    if core_gaps:
        lines.append(f"- Missing or under-emphasised: **{gaps_str}**.")
    else:
        lines.append("- No clear gaps from keywords alone. Focus on clearer impact statements and outcomes.")

    # Tips
    lines.append("")
    lines.append("**How to strengthen your fit**")
    if core_gaps:
        lines.append(
            "- If you have experience in the above, bring them forward explicitly with quantifiable examples."
        )
    lines.append(
        "- Mirror relevant phrasing from the JD (truthfully) so that ATS and reviewers can recognise the match."
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
        return "'Customer Service Excellence' — NTUC LearningHub (Singapore, classroom/online)"
    if any(k in text for k in ["data", "analytics", "excel"]):
        return "'Excel Skills for Business' — Coursera (online, SkillsFuture claimable)"
    if any(k in text for k in ["admin", "executive", "coordinator"]):
        return "'Digital Office Skills with Microsoft 365' — Singapore Polytechnic PACE (short course)"
    if any(k in text for k in ["it", "network", "technician"]):
        return "'CompTIA A+ Certification Training' — NTUC LearningHub (Singapore, blended)"
    if any(k in text for k in ["sales", "marketing", "account manager"]):
        return "'Professional Selling Skills' — SMU Academy (short executive programme)"

    return "'Career Resilience & Future Skills' — SkillsFuture Singapore (online options available)"


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


def generate_pdf_bytes(title: str, subtitle: str, analysis_md: str, courses_md: str):
    """Generate a PDF from the analysis and course recommendation content.

    Returns (pdf_bytes, error_message). If error_message is not None, PDF couldn't be generated.
    """
    try:
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT
    except Exception as e:
        return None, (
            "ReportLab is required to export PDF. Install with:\n"
            "pip install reportlab\n\n"
            f"Details: {e}"
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title=title,
    )

    styles = getSampleStyleSheet()
    style_title = styles["Title"]
    style_sub = ParagraphStyle("SubTitle", parent=styles["Normal"], fontSize=11, leading=14, spaceAfter=12)
    style_h2 = styles["Heading2"]
    style_body = styles["BodyText"]

    def md_to_html(s: str) -> str:
        # Convert basic markdown bold to HTML for Paragraph
        # Replace **bold** with <b>bold</b>
        import re
        # Use regex to properly match **text** and replace with <b>text</b>
        out = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
        # Newlines to <br/>
        out = out.replace("\n", "<br/>")
        return out

    story = []
    story.append(Paragraph(title, style_title))
    if subtitle:
        story.append(Paragraph(subtitle, style_sub))
    story.append(Spacer(1, 8))

    if analysis_md:
        story.append(Paragraph("Analysis", style_h2))
        for block in analysis_md.split("\n\n"):
            story.append(Paragraph(md_to_html(block.strip()), style_body))
            story.append(Spacer(1, 6))

    if courses_md:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Course Recommendations", style_h2))
        for block in courses_md.split("\n\n"):
            story.append(Paragraph(md_to_html(block.strip()), style_body))
            story.append(Spacer(1, 6))

    doc.build(story)
    buf.seek(0)
    return buf.read(), None


# ---------------- GLOBAL STYLES ----------------
st.markdown(
    """
    <style>
    .big-title {font-size: 40px; font-weight: 700;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="big-title">📊 Job Match & Gap Analysis</div>',
    unsafe_allow_html=True,
)
st.caption("Upload your resume and analyze your fit against the selected job.\n\nAI-powered analysis will be used automatically if GEMINI_API_KEY is set in your .env file.")
if st.session_state.get("gemini_api_key"):
    st.info("✅ GEMINI_API_KEY found in environment: AI-powered analysis will run when available")
else:
    st.info("ℹ️ No GEMINI_API_KEY found in environment: running keyword-only analysis")

# Allow user to choose web search tool
st.sidebar.markdown("### Web search settings")
search_tool_choice = st.sidebar.selectbox(
    "Search tool",
    options=["tavily", "duckduckgo"],
    index=0 if st.session_state.get("search_tool") == "tavily" else 1,
    help="Choose the web search tool used to find course recommendations. Tavily requires an API key (TAVILY_API_KEY in .env). DuckDuckGo (langchain_community) doesn't require a key.",
)
st.session_state["search_tool"] = search_tool_choice
# If duckduckgo is selected, check if ddgs is installed; otherwise prompt the user
if st.session_state["search_tool"] == "duckduckgo":
    try:
        import importlib
        if importlib.util.find_spec("ddgs") is None:
            st.sidebar.warning("DuckDuckGo tool requires the 'ddgs' package. Install with: pip install ddgs or add ddgs to your conda env.")
    except Exception:
        st.sidebar.warning("DuckDuckGo tool requires the 'ddgs' package. Install with: pip install ddgs or add ddgs to your conda env.")
elif st.session_state["search_tool"] == "tavily" and not st.session_state.get("tavily_api_key"):
    st.sidebar.info("Tavily selected but no TAVILY_API_KEY set; web search will be disabled unless you provide a Tavern API key in the .env or sidebar.")



# ---------------- MAIN CONTENT ----------------

full_jobs = st.session_state["full_jobs"]
flat_jobs = st.session_state["flat_jobs"]

if not full_jobs:
    st.warning("⚠️ No jobs loaded. Please go to the **Job Search** page first to fetch jobs.")
    st.stop()

# ===== RESUME UPLOAD SECTION =====
st.subheader("📄 Upload Resume")

uploaded_resume = st.file_uploader(
    "Upload your resume (PDF / DOCX / DOC / TXT)",
    type=["pdf", "docx", "doc", "txt"],
)

if uploaded_resume is not None:
    text = extract_resume_text(uploaded_resume)
    if text:
        st.session_state["resume_text"] = text
        st.success("✅ Resume uploaded and text extracted.")
        with st.expander("Preview extracted resume text"):
            st.text_area("Extracted text", value=text, height=200)
    else:
        st.error("Could not extract text from this resume file.")
        
st.markdown("---")

# ===== JOB SELECTION =====
st.subheader("📋 Select Job for Analysis")

import pandas as pd
df = pd.DataFrame(flat_jobs)
visible_indices = df.index.tolist()

if visible_indices:
    selected = st.selectbox(
        "Choose a job to analyze",
        options=visible_indices,
        index=st.session_state["selected_job_idx"] if st.session_state["selected_job_idx"] in visible_indices else 0,
        format_func=lambda i: f"{flat_jobs[i]['Title']} — {flat_jobs[i]['Company']}",
    )
    st.session_state["selected_job_idx"] = selected
    selected_job = full_jobs[selected]
    st.info(f"**Selected role:** {selected_job.get('Title', '(No Title)')} at {selected_job.get('Company', 'N/A')}")
else:
    st.warning("⚠️ No jobs available. Please go to the **Job Search** page and fetch jobs first.")
    st.stop()



# ===== GAP ANALYSIS SECTION =====
st.markdown("---")
st.subheader("🔍 Gap Analysis")

if st.session_state["resume_text"]:
    if st.button("Run Gap Analysis", type="primary"):
        with st.spinner("Analysing your resume against the job…"):
            resume_text = st.session_state["resume_text"]

            # Use job description only for keyword-based comparison
            desc_plain = strip_html(get_job_description_text(selected_job))
            combined_job_text = desc_plain

            job_kw, kw_overlap, kw_gaps = build_job_resume_overlap(
                combined_job_text, resume_text
            )

            # Coverage metrics (keywords only)
            job_kw_total = len(job_kw)
            keyword_coverage = int(
                round(100 * len(kw_overlap) / job_kw_total)
            ) if job_kw_total else 0
            match_pct = keyword_coverage

            st.session_state["job_match_pct"] = match_pct
            st.session_state["keyword_coverage_pct"] = keyword_coverage

            # === ANALYSIS ===
            # If GEMINI_API_KEY is present in .env, attempt to use AI analysis (if packages installed).
            if st.session_state.get("gemini_api_key"):
                try:
                    # Use the AI/LLM powered analysis
                    st.info("🤖 Gemini API key detected — attempting AI-powered analysis...")
                    analysis, courses = get_smart_gap_analysis(
                        job=selected_job,
                        resume_text=resume_text,
                        keyword_overlap=kw_overlap,
                        keyword_gaps=kw_gaps,
                        gemini_api_key=st.session_state.get("gemini_api_key"),
                        tavily_api_key=st.session_state.get("tavily_api_key"),
                        use_web_search=not (st.session_state.get("search_tool") is None) and (
                            st.session_state.get("search_tool") == "duckduckgo" or bool(st.session_state.get("tavily_api_key"))
                        ),
                        search_tool=st.session_state.get("search_tool"),
                    )
                except Exception as e:
                    # Fall back to keyword-only analysis if the AI path fails
                    st.warning(f"AI analysis failed: {e}. Using keyword-only analysis instead.")
                    analysis = generate_keyword_only_analysis_text(
                        selected_job,
                        resume_text,
                        kw_overlap,
                        kw_gaps,
                        job_kw_total=job_kw_total,
                        keyword_coverage=keyword_coverage,
                    )
                    courses = None
            else:
                # No API key set; use keyword-only analysis
                analysis = generate_keyword_only_analysis_text(
                    selected_job,
                    resume_text,
                    kw_overlap,
                    kw_gaps,
                    job_kw_total=job_kw_total,
                    keyword_coverage=keyword_coverage,
                )
                courses = None
            # Generate keyword-only analysis narrative and simple course recommendation
            analysis = generate_keyword_only_analysis_text(
                selected_job,
                resume_text,
                kw_overlap,
                kw_gaps,
                job_kw_total=job_kw_total,
                keyword_coverage=keyword_coverage,
            )

            course = recommend_course(selected_job, kw_gaps)

            overview_section = (
                "**📊 MATCH OVERVIEW**\n\n"
                f"- Keyword overlap: {len(kw_overlap)} of {job_kw_total} unique keywords\n"
                f"- Coverage: {keyword_coverage}%\n\n"
            )

            result = (
                f"{overview_section}"
                f"**GAP ANALYSIS (Narrative)**\n\n"
                f"{analysis}\n\n"
            )

            st.session_state["analysis_text"] = result
            # If AI returned courses, use them; others wise use local recommendation
            if courses:
                st.session_state["course_recommendations"] = courses
            else:
                st.session_state["course_recommendations"] = (
                    "**COURSE RECOMMENDATION**\n\n"
                    f"- Suggested course: {recommend_course(selected_job, kw_gaps)}\n"
                )
        
        st.rerun()

if st.session_state["analysis_text"]:
    st.markdown("---")
    st.markdown("## 📊 Analysis Results")
    
    analysis_text = st.session_state["analysis_text"]
    
    # Parse and display match overview section
    if "MATCH OVERVIEW" in analysis_text:
        # Extract overview section
        overview_match = analysis_text.split("**GAP ANALYSIS")[0] if "**GAP ANALYSIS" in analysis_text else analysis_text
        with st.expander("📊 **Match Overview**", expanded=True):
            st.markdown(overview_match)

    # Display main analysis
    if "**GAP ANALYSIS" in analysis_text:
        gap_analysis = analysis_text.split("**GAP ANALYSIS")[1].strip()
        with st.expander("📈 **Gap Analysis**", expanded=True):
            st.markdown(gap_analysis)
    
    # Display course recommendations (dedupe repeated paragraphs)
    if st.session_state["course_recommendations"]:
        st.markdown("---")
        
        with st.expander("📚 **Course Recommendations**", expanded=True):
            # Remove repeated paragraphs in recommendations (sometimes LLM returns duplicates)
            def _dedupe_paragraphs(s: str) -> str:
                if not s:
                    return s
                import re
                parts = [p.strip() for p in re.split(r"\n\s*\n", s) if p.strip()]
                seen = set(); uniq = []
                for p in parts:
                    if p not in seen:
                        seen.add(p); uniq.append(p)
                return "\n\n".join(uniq)

            cleaned = _dedupe_paragraphs(st.session_state["course_recommendations"])
            st.markdown(cleaned)
    
    # Export as PDF
    st.markdown("---")
    pdf_title = f"Gap Analysis - {selected_job.get('Title', 'Role')}"
    pdf_subtitle = f"{selected_job.get('Company', '')}"
    pdf_bytes, pdf_err = generate_pdf_bytes(
        title=pdf_title,
        subtitle=pdf_subtitle,
        analysis_md=st.session_state["analysis_text"],
        courses_md=st.session_state.get("course_recommendations", ""),
    )
    cols = st.columns([1, 5])
    with cols[0]:
        if pdf_bytes:
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name=f"{pdf_title}.pdf",
                mime="application/pdf",
            )
        elif pdf_err:
            st.info(pdf_err)
    
    # (Quick AI insights removed)
            
else:
    if not st.session_state["resume_text"]:
        st.info("💡 Please upload your resume above to proceed with gap analysis.")
    else:
        st.info("💡 Click 'Run Gap Analysis' to see detailed results.")
