"""Small Responses API adapter shared by the four AI-owned editorial components."""

import json
import os
import pathlib
import uuid

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]


def generate_json(run, stage, instructions, payload, max_output_tokens=5000):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for AI editorial stages")
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    request = {
        "model": model,
        "instructions": instructions + "\nReturn one valid JSON object and no surrounding text.",
        "input": "Return a JSON object for this task:\n" + json.dumps(payload, ensure_ascii=False),
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    folder = run / "model_calls" / stage
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("request") != request or cached.get("response", {}).get("status") != "completed":
                continue
            result = cached["response"]
            body = "".join(part.get("text", "") for output in result.get("output", []) for part in output.get("content", []) if part.get("type") == "output_text")
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return parsed, model, result.get("usage"), path.relative_to(ROOT).as_posix()
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        json=request,
        timeout=240,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Responses API HTTP {response.status_code}: {response.text[:600]}")
    result = response.json()
    if result.get("status") != "completed":
        raise RuntimeError(f"Responses API did not complete: {result.get('status')}")
    text = "".join(part.get("text", "") for output in result.get("output", []) for part in output.get("content", []) if part.get("type") == "output_text")
    if not text:
        raise RuntimeError("Responses API returned no output text")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Model did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Model output must be a JSON object")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (uuid.uuid4().hex + ".json")
    path.write_text(json.dumps({"request": request, "response": result}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return parsed, model, result.get("usage"), path.relative_to(ROOT).as_posix()
