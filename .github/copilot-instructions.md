# GitHub Copilot Instructions for arxiv-daily-researcher

## 🧭 Repo purpose
`arxiv-daily-researcher` is a Python-based research assistant that:
- periodically scans ArXiv/OpenAlex (and related sources) for new papers matching configured keywords
- scores, summarizes, and analyzes papers using LLMs
- generates reports (Markdown/HTML) and sends notifications via webhook/email/etc.

The project is primarily a CLI app with optional Docker+Streamlit web UI.

---

## ✅ What to do as an AI assistant
When the user asks for help, focus on: 
- **How to run the tool** (local Python, Docker, and the provided scripts)
- **Where configuration lives** (`.env`, `configs/config.json`) and how to adjust it
- **How to interpret output** (reports under `data/reports/`, logs under `logs/`, etc.)
- **How to extend/trace behavior** (e.g., follow `src/modes/*`, `src/agents/*`, and `src/sources/*`)

Always be conservative: only describe behavior that is implemented in code, not assumptions.

---

## 🛠️ Common tasks
### Run locally
```bash
python main.py
```

### Run trend analysis mode
```bash
python main.py --mode trend_research --keywords "quantum error correction"
```

### Run via provided scripts
- macOS: `scripts/run_daily_mac.sh`
- POSIX: `scripts/run_daily.sh`
- Windows: `scripts/run_daily.ps1`

### Run with Docker
```bash
docker compose -f docker/docker-compose.yml up -d
```

---

## 🔍 Where to look for key concepts
- `main.py` — CLI entry point and mode dispatch
- `src/config.py` — configuration loader + pydantic settings
- `src/modes/` — core workflows (daily vs trend)
- `src/sources/` — data fetching (ArXiv/OpenAlex/etc.)
- `src/agents/` — LLM orchestration and analysis logic
- `src/report/` — markdown/html report generation
- `src/notifications/` — notification delivery logic

---

## 🧠 Conventions & Cautions
- Config priority: `configs/config.json` > `.env` > code defaults
- Data artifacts live under `data/` (PDFs, reports, history)
- The `run_lock` mechanism ensures only one run happens at a time

---

## ✍️ How to ask for help
For clearer assistance, users should provide:
1. The command they ran (or script used)
2. The relevant config snippet (if applicable)
3. Any error output or unexpected behavior

---

## 🧩 Files to update if this repo grows
- `README.md` for high-level usage and requirements
- `docs/` for detailed how-tos (if added)
- `scripts/` for repeatable run patterns
- `.github/workflows/` if CI is added
