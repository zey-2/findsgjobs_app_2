# FindSGJobs Application

A Streamlit-based job search and career gap analysis application that helps users discover job opportunities in Singapore and analyze how well their skills match job requirements.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Smart AI Gap Analysis](#smart-ai-gap-analysis)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Dependencies](#dependencies)
- [API Integration](#api-integration)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Features

### 🏠 Overview

- Welcome page with application introduction
- Feature highlights and navigation guide

### 🔍 Job Search

- Search and filter job listings from FindSGJobs.com
- Advanced filtering options:
  - Keywords
  - Employment types
  - Job categories
  - Education levels
  - Years of experience
  - MRT stations
  - Salary range
  - Interactive job results table
  - Detailed job description viewer
  - Backend supports pagination; the Streamlit UI fetches a single page by default (configurable).

### 📊 Gap Analysis

- Upload your resume (PDF, DOCX, DOC, or TXT format)
- **NEW: AI-powered smart gap analysis** using LangChain + Google Gemini
- Compare your qualifications against job requirements
- Keyword matching and coverage metrics
- **NEW: Web-enhanced course recommendations** with real-time search (Tavily)
- **NEW: Quick AI insights** for instant feedback
- Job match percentage calculation

## Quick Start

### 5-Minute Setup

1. **Create environment:**

   ```bash
   conda env create -f environment.yml
   conda activate findsgjobs_tmp
   ```

2. **Get API keys (for AI features):**

   - **Gemini API**: Visit https://ai.google.dev/ (Required for AI)
   - **Tavily API**: Visit https://tavily.com/ (Optional for web search)
   - **DuckDuckGo (community)**: Optionally use the DuckDuckGo search tool via `langchain_community` (no API key required). Install `ddgs` if you plan to use DuckDuckGo.

3. **Configure keys:**

   ```bash
   copy .env.example .env
   # Edit .env and add your keys
   ```

4. **Run the app:**

   ```bash
   streamlit run Overview.py
   ```

5. **Use Smart Analysis:**
   - Upload resume → Select job → Enable AI in sidebar → Run analysis

## Installation

### Prerequisites

- Anaconda or Miniconda
- Python 3.12 (as specified in `environment.yml`)

### Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd findsgjobs_app_2
```

2. Create the conda environment:

```bash
conda env create -f environment.yml
```

3. Activate the environment:

```bash
conda activate findsgjobs_tmp
```

## Smart AI Gap Analysis

### Overview

The application now includes **AI-powered smart gap analysis** using LangChain and Google's Gemini API, with optional web search capabilities via Tavily.

### Features

#### 🤖 Smart AI Analysis

-- **Intelligent Gap Analysis**: Uses Google's Gemini model (configured in code as `gemini-2.5-flash`) for comprehensive, contextual analysis

- **Structured Insights**:
  - Match Strength Assessment
  - Key Strengths Identification
  - Skill Gaps Analysis
  - Actionable Recommendations
- **Singapore-focused**: Tailored for the Singapore job market

#### 🌐 Web-Enhanced Course Recommendations

- **Real-time Course Search**: Integrates Tavily web search to find current, relevant courses
- **SkillsFuture Integration**: Prioritizes SkillsFuture-claimable courses
- **Diverse Options**: Includes online, classroom, and blended learning formats
- **Reputable Providers**: Focuses on established Singapore institutions

#### 💡 Quick AI Insights

- Instant 3-point assessment (Strength, Gap, Tip)
- Fast feedback for quick decisions

### Setup for AI Features

#### 1. Install Required Packages

Exact pinned package versions are provided in `environment.yml`; use that file to create the environment:

```bash
conda env update -f environment.yml
```

If you prefer to install dependencies with `pip` (not recommended for reproducible installs), a representative command is:

```bash
pip install streamlit PyPDF2 python-docx \
   langchain==1.0.7 langchain-google-genai==3.0.3 langchain-community==0.4.1 langchain-tavily \
   google-ai-generativelanguage==0.9.0 tavily-python ddgs python-dotenv
```

#### 2. Get API Keys

**Gemini API Key (Required for AI)**

1. Visit [Google AI Studio](https://aistudio.google.com/)
2. Sign in with your Google account
3. Click "Get API Key"
4. Create or select a project
5. Copy your API key

**Web Search Options (Optional, for Web Search)**

You can use either:

1. **Tavily** (requires API key): Visit [Tavily](https://tavily.com/), sign up, and copy your API key.
2. **DuckDuckGo** (no API key required): Uses the `langchain_community` DuckDuckGo tool with the `ddgs` package.

#### 3. Configure API Keys

1. Copy the example file:

   ```bash
   copy .env.example .env
   ```

2. Edit `.env` and add your keys:
   ```
   GEMINI_API_KEY=your_actual_gemini_key_here
   TAVILY_API_KEY=your_actual_tavily_key_here
   ```

### Using Smart Gap Analysis

1. **Upload Resume**: Upload your resume (PDF, DOCX, or TXT)
2. **Select Job**: Choose a job from the dropdown
3. **Enable Smart Analysis** (Sidebar):
   - (Optional) Choose which web search tool to use for course recommendations:
     - In the Streamlit sidebar, open **Web search settings** and select **tavily** or **duckduckgo**.
     - If you run the CLI tool, pass `--search-tool tavily` or `--search-tool duckduckgo`.
4. **Run Analysis**: Click "Run Gap Analysis"
5. **Review Results**:
   - **Match Overview**: Keyword statistics
   - **AI-Powered Gap Analysis**: Comprehensive analysis with structured insights
   - **Course Recommendations**: Web-searched or AI-generated courses
   - **Quick AI Insights**: Expandable section with rapid feedback

### Analysis Modes

#### Basic Mode (Default fallback)

- Keyword-based matching
- Simple gap identification
- Pre-defined course recommendations
- No API keys required

#### Smart AI Mode

- Context-aware analysis
- Personalized recommendations
- Web-based course search (with Tavily)
- Requires Gemini API key

### Architecture

```
┌─────────────────────────────────────────────────┐
│         2_Gap_Analysis.py (UI Layer)            │
│  - Resume upload                                │
│  - Job selection                                │
│  - API key configuration                        │
│  - Results display                              │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│      smart_gap_analysis.py (Logic Layer)        │
│  - get_smart_gap_analysis()                     │
│  - get_quick_insights()                         │
│  - LangChain integration                        │
└────────────────┬────────────────────────────────┘
                 │
      ┌──────────┴──────────┐
      ▼                     ▼
┌─────────────┐      ┌─────────────┐
│   Gemini    │      │   Tavily    │
│     API     │      │     API     │
│  (Analysis) │      │ (Web Search)│
└─────────────┘      └─────────────┘
```

### Cost Considerations

**Gemini API**

- Model: `gemini-2.5-flash`
- Free tier: 15 requests per minute
- Very affordable pricing

**Tavily API**

- Free tier: 1000 searches/month
- Sufficient for most users

### Example Output

```
📊 MATCH OVERVIEW
- Keyword overlap: 45 of 120 unique keywords
- Coverage: 38%

🤖 AI-POWERED GAP ANALYSIS

**MATCH STRENGTH**
Your resume shows relevant experience in project coordination and
stakeholder management, which aligns well with this Business Analyst
role. However, there are notable gaps in technical skills.

**KEY STRENGTHS**
✓ Strong project management experience with clear deliverables
✓ Excellent communication and stakeholder engagement
✓ Proven analytical thinking and problem-solving abilities

**SKILL GAPS**
⚠ Limited exposure to SQL and database querying
⚠ No mention of data visualization tools (Tableau, Power BI)
⚠ Agile/Scrum certification not evident

**RECOMMENDATIONS**
1. Complete SQL fundamentals course (SkillsFuture eligible)
2. Obtain Tableau Desktop Specialist certification
3. Add metrics/KPIs to your project descriptions
4. Consider PSM I or similar Agile certification
```

**Course Recommendations (with Web Search)**

```
📚 COURSE RECOMMENDATIONS
🌐 Recommendations based on web search results

1. **SQL for Business Analysts** - NTUC LearningHub
   Directly addresses database querying gap.
   Format: Blended (online + classroom)
   SkillsFuture: Eligible

2. **Tableau Desktop Fundamentals** - Coursera
   Covers essential data visualization skills.
   Format: Online, self-paced
   SkillsFuture: Yes

3. **Agile Business Analysis** - Singapore Polytechnic PACE
   Combines Agile methodology with BA techniques.
   Format: Classroom
   SkillsFuture: Check with provider
```

## Usage

1. Start the Streamlit application:

```bash
streamlit run Overview.py
```

2. The application will open in your default web browser at `http://localhost:8501`

3. Navigate through the pages:
   - **Home (Overview.py)**: Introduction and feature overview
   - **Job Search**: Search and browse available job listings
   - **Gap Analysis**: Upload your resume and analyze skill gaps

## Project Structure

```
findsgjobs_app_2/
├── Overview.py              # Main entry point and home page
├── api_client.py           # API client for fetching job data
├── smart_gap_analysis.py   # AI-powered gap analysis logic
├── environment.yml         # Conda environment configuration
├── .env.example            # API keys template
├── .env                    # API keys (create from .env.example)
├── pages/
│   ├── 1_Job_Search.py    # Job search and filtering interface
│   └── 2_Gap_Analysis.py  # Resume analysis and gap analysis
└── __pycache__/           # Python cache files
```

## Dependencies

Exact, tested package versions are provided in `environment.yml`. Use that file to create the conda environment for reproducible installs.

### Core Dependencies (representative)

- `streamlit` - Web application framework
- `pandas` - Data manipulation and analysis
- `requests` - HTTP library for API calls
- `PyPDF2` - PDF file parsing
- `python-docx` - DOCX file parsing

### AI/ML Dependencies (representative)

- `langchain` and `langchain-google-genai` - Gemini integration
- `langchain-community` / DuckDuckGo tools - optional web search helpers
- `google-ai-generativelanguage` - Google Gemini client
- `tavily-python` - Tavily web search API (optional)
- `python-dotenv` - Environment variable management

Refer to `environment.yml` for the exact pinned versions included in this project.

## API Integration

The application integrates with the FindSGJobs API endpoint:

- Base URL: `https://www.findsgjobs.com/apis/job/searchable`
- Supports various filtering parameters
- Returns paginated job results

## Features in Detail

### Job Search Filters

- **Keywords**: Free-text search across job listings
- **Employment Type**: Full-time, Part-time, Contract, etc.
- **Job Category**: IT, Finance, Healthcare, etc.
- **Education Level**: Minimum education requirements
- **Experience**: Years of experience required
- **Location**: Filter by MRT station proximity
- **Salary Range**: Set minimum and maximum salary expectations

### Gap Analysis Workflow

1. Upload your resume (PDF, DOCX, DOC, or TXT)
2. Select a job from your search results
3. View automated analysis comparing:
   - Your skills vs. job requirements
   - Keyword coverage percentage
   - Overall job match score
4. Receive AI-powered, personalized course recommendations to bridge skill gaps

## Troubleshooting

### AI Features

**"Missing required packages"**

```bash
# Use the pinned environment.yml for reproducible installs:
conda env update -f environment.yml

# Or (less reproducible) install representative pip packages:
pip install streamlit PyPDF2 python-docx \
   langchain==1.0.7 langchain-google-genai==3.0.3 langchain-community==0.4.1 \
   google-ai-generativelanguage==0.9.0 tavily-python python-dotenv
```

**"Gemini API key not found"**

- Check `.env` file exists and contains `GEMINI_API_KEY=...`
- Or enter key in Streamlit sidebar

**"Web search unavailable"**

- Tavily API key not configured (optional feature)
- Falls back to LLM-only recommendations

**Import Errors**

```bash
conda env update -f environment.yml
```

### General Issues

**Application won't start**

- Ensure conda environment is activated: `conda activate findsgjobs_tmp`
- Check all dependencies are installed: `conda list`

**Resume upload fails**

- Supported formats: PDF, DOCX, DOC, TXT
- Check file is not corrupted
- Try re-saving the file in a compatible format

## Session State Management

The application uses Streamlit's session state to maintain:

- Job search results
- Selected job details
- Uploaded resume content
- Analysis results
- Match percentages
- API keys (session-only, not persisted)

## Security Notes

⚠️ **Important**:

- Never commit `.env` file to version control
- API keys are sensitive - keep them secure
- `.env` is already in `.gitignore`
- Use environment variables in production
- Consider secret management services for production deployments

## Future Enhancements

- [ ] Support for multiple resume formats
- [ ] Batch analysis for multiple jobs
- [ ] Historical analysis tracking
- [ ] Custom AI prompts/templates
- [ ] Additional LLM providers
- [ ] Resume improvement suggestions
- [ ] ATS optimization tips
- [ ] Save/export analysis reports

## Contributing

This project is part of the NTU Data Science & AI Capstone project.

## Acknowledgments

- NTU SCTP Data Science & AI Course
- FindSGJobs.com API
- Glenis Law (for the original code base)
