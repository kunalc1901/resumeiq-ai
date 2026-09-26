"""Generate answers from an LLM.

Uses Gemini (REST API) when ``GEMINI_API_KEY`` is set in the environment
or .env; otherwise falls back to a local Ollama server
(https://ollama.com, model ``llama3.2`` by default).
"""

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from core.config import settings

OLLAMA_HOST = "http://localhost:11434"

GEMINI_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

DEFAULT_NUM_CTX = 8192
DEFAULT_NUM_PREDICT = 4096
DEFAULT_TIMEOUT = 1800

SYSTEM_MESSAGE = "You answer questions concisely based on provided context."


def _now() -> str:
    """Current local time as a readable timestamp for logs."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token for English text)."""
    return len(text) // 4


def _provider() -> str:
    return "gemini" if settings.GEMINI_API_KEY else "ollama"


# Transient HTTP statuses to retry with backoff (free tier is often busy).
GEMINI_RETRY_STATUSES = {429, 500, 502, 503}
GEMINI_MAX_RETRIES = 5
GEMINI_RETRY_BASE_DELAY = 2  # seconds; doubled on each retry


def _gemini_chat(
    prompt: str,
    model: str,
    num_predict: int,
    timeout: int,
) -> str:
    """Send a single prompt to Gemini and return the answer text.

    Transient errors (429/500/502/503) are retried with exponential
    backoff, since the free tier is frequently under high demand.
    """
    body = json.dumps(
        {
            "system_instruction": {"parts": [{"text": SYSTEM_MESSAGE}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": num_predict,
            },
        }
    ).encode()

    attempt = 0

    while True:
        attempt += 1

        req = urllib.request.Request(
            GEMINI_GENERATE_URL.format(model=model, key=settings.GEMINI_API_KEY),
            data=body,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
                break
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode(errors="replace")
            if exc.code in GEMINI_RETRY_STATUSES and attempt <= GEMINI_MAX_RETRIES:
                delay = GEMINI_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(
                    f"[llm] {_now()} Gemini HTTP {exc.code} on attempt "
                    f"{attempt}/{GEMINI_MAX_RETRIES}, retrying in {delay}s...",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise RuntimeError(
                f"Gemini request failed with HTTP {exc.code}: {error_body}"
            ) from exc
        except TimeoutError as exc:
            if attempt <= GEMINI_MAX_RETRIES:
                delay = GEMINI_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(
                    f"[llm] {_now()} Gemini timeout on attempt "
                    f"{attempt}/{GEMINI_MAX_RETRIES}, retrying in {delay}s...",
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise TimeoutError(
                f"Gemini request timed out after {timeout}s "
                f"(model={model}, num_predict={num_predict})."
            ) from exc

    try:
        candidate = result["candidates"][0]
        parts = candidate.get("content", {}).get("parts", [])
        if not parts:
            finish = candidate.get("finishReason", "UNKNOWN")
            raise RuntimeError(
                f"Gemini returned no text content (finishReason={finish}). "
                f"The model likely exhausted maxOutputTokens on thinking. "
                f"Increase num_predict for this call. Response: "
                f"{json.dumps(result)[:500]}"
            )
        return parts[0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected Gemini response: {json.dumps(result)[:500]}"
        ) from exc


def _ollama_chat(
    prompt: str,
    model: str,
    num_ctx: int,
    num_predict: int,
    timeout: int,
) -> str:
    """Send a single prompt to Ollama and return the answer text."""
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
        }
    ).encode()

    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"Ollama request failed with HTTP {exc.code}: {error_body}"
        ) from exc
    except TimeoutError as exc:
        elapsed = time.time() - started
        raise TimeoutError(
            f"Ollama request timed out after {elapsed:.0f}s "
            f"(model={model}, num_ctx={num_ctx}, num_predict={num_predict}, "
            f"prompt_tokens={_estimate_tokens(prompt)}). "
            f"Increase the timeout or reduce num_predict/prompt size."
        ) from exc

    return result["message"]["content"].strip()


def _chat(
    prompt: str,
    model: str = "llama3.2",
    num_ctx: int = DEFAULT_NUM_CTX,
    num_predict: int = DEFAULT_NUM_PREDICT,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Send a single prompt to the active LLM and return the answer text."""
    provider = _provider()
    effective_model = settings.GEMINI_MODEL if provider == "gemini" else model

    if provider == "gemini":
        print(
            f"[llm] {_now()} >>> USING GEMINI (model '{effective_model}') "
            f"because GEMINI_API_KEY is configured <<<",
            flush=True,
        )
    else:
        print(
            f"[llm] {_now()} >>> USING LOCAL OLLAMA (model '{model}') "
            f"because no GEMINI_API_KEY is configured <<<",
            flush=True,
        )

    print(
        f"[llm] {_now()} provider={provider}, model={effective_model}, "
        f"num_ctx={num_ctx if provider == 'ollama' else 'n/a'}, "
        f"num_predict={num_predict}, prompt_chars={len(prompt)}, "
        f"est_prompt_tokens={_estimate_tokens(prompt)}",
        flush=True,
    )

    started = time.time()

    if provider == "gemini":
        answer = _gemini_chat(prompt, effective_model, num_predict, timeout)
    else:
        answer = _ollama_chat(prompt, model, num_ctx, num_predict, timeout)

    elapsed = time.time() - started

    print(
        f"[llm] {_now()} response_chars={len(answer)}, est_response_tokens="
        f"{_estimate_tokens(answer)}, elapsed={elapsed:.1f}s",
        flush=True,
    )

    return answer


def build_prompt(question: str, chunks: list[dict]) -> str:
    context_parts = []
    for c in chunks:
        page = c["meta"]["page"]
        context_parts.append(f"[Page {page}] {c['content']}")

    context_str = "\n\n---\n\n".join(context_parts)

    return f"""You are a helpful assistant. Answer the question based **only** on the context below. If the context does not contain enough information, say "I cannot answer this from the provided document."

Context:
{context_str}

Question: {question}

Answer:"""


def ask_llm(
    question: str,
    chunks: list[dict],
    model: str = "llama3.2",
    num_ctx: int = DEFAULT_NUM_CTX,
    num_predict: int = DEFAULT_NUM_PREDICT,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Send a QA prompt to the LLM and return the answer."""
    return _chat(
        build_prompt(question, chunks),
        model,
        num_ctx=num_ctx,
        num_predict=num_predict,
        timeout=timeout,
    )


def ask_llm_full_text(
    instruction: str,
    full_text: str,
    model: str = "llama3.2",
    num_ctx: int = DEFAULT_NUM_CTX,
    num_predict: int = DEFAULT_NUM_PREDICT,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Send an instruction together with the full document text to the LLM.

    Use this for extraction tasks where the whole document must be seen
    at once (retrieval would lose context like which company a project
    belongs to).
    """
    prompt = f"""{instruction}

FULL RESUME TEXT:
{full_text}

Return ONLY the requested dictionary and nothing else."""
    return _chat(
        prompt,
        model,
        num_ctx=num_ctx,
        num_predict=num_predict,
        timeout=timeout,
    )
