# resumeiq-ai

AI microservice for resume analysis, RAG-based Q&A, interview question generation, and answer evaluation using FastAPI, ChromaDB, and LLMs (Gemini or local Ollama).

## Prerequisites

- **Python 3.12** — required because `chromadb` depends on `onnxruntime`, which no longer ships wheels for Intel Macs (or other platforms) on newer Python versions. Python 3.14 on an Intel Mac cannot install it.
  - If you don't have Python 3.12, install it with `uv` (no sudo needed):
    ```sh
    curl -LsSf https://astral.sh/uv/install.sh | sh
    uv python install 3.12
    ```

## Setup

```sh
# 1. Create the virtual environment (use Python 3.12)
uv venv --python 3.12 .venv

# 2. Install dependencies
uv pip install --python .venv/bin/python -r requirements.txt

# 3. Configure environment (edit values for your account)
cp -n .env.example .env  # or create .env manually (see below)
```

`.env` lives at the project root (gitignored). Required settings:

```ini
MONGODB_URI=mongodb://localhost:27017
DATABASE_NAME=resumeiq
RESUME_COLLECTION=resumes

S3_BUCKET_NAME=your-bucket
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1

COGNITO_REGION=
COGNITO_USER_POOL_ID=

GEMINI_API_KEY=            # if set, LLM calls use Gemini; otherwise local Ollama
GEMINI_MODEL=gemini-3.6-flash
```

If `COGNITO_REGION` / `COGNITO_USER_POOL_ID` are empty, auth is skipped and a
dev user is injected so endpoints work locally. The LLM falls back to a local
Ollama server (`http://localhost:11434`, model `llama3.2`) when no
`GEMINI_API_KEY` is set.

## Start the server

From the project root:

```sh
.venv/bin/uvicorn app.main:app --reload
```

Or from inside `app/`:

```sh
cd app && ../.venv/bin/uvicorn main:app --reload
```

- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## API

| Method | Path         | Description                              |
| ------ | ------------ | ---------------------------------------- |
| POST   | `/process`   | Process a resume (PDF from S3), store analysis + chunks |
| POST   | `/ask`       | Ask a question about a processed resume  |
| POST   | `/job-match` | Match a resume against a job description |
| GET    | `/health`    | Health check                             |