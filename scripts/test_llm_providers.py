#!/usr/bin/env python3
"""
Quick diagnostic: test each configured LLM provider in isolation.

Usage:
    python3 scripts/test_llm_providers.py

Loads .env automatically (if python-dotenv installed) and tries
Groq, NVIDIA, HuggingFace, and Ollama one at a time, printing
exactly what each one returns or fails with.
"""

import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("(tip: pip install python-dotenv to auto-load .env)")

import httpx

PROMPT = "Reply with exactly the word: OK"


def test_groq():
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        print("GROQ_API_KEY  : not set, skipping")
        return
    try:
        t0 = time.time()
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "llama3-70b-8192", "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 10},
            timeout=30,
        )
        print(f"GROQ          : HTTP {r.status_code} in {time.time()-t0:.1f}s")
        print(f"  body        : {r.text[:300]}")
    except Exception as e:
        print(f"GROQ          : EXCEPTION -> {e}")


def test_nvidia():
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        print("NVIDIA_API_KEY: not set, skipping")
        return
    model = os.environ.get("NVIDIA_MODEL", "meta/llama3-70b-instruct")
    try:
        t0 = time.time()
        r = httpx.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 10},
            timeout=60,
        )
        print(f"NVIDIA        : HTTP {r.status_code} in {time.time()-t0:.1f}s  (model={model})")
        print(f"  body        : {r.text[:300]}")
    except Exception as e:
        print(f"NVIDIA        : EXCEPTION -> {e}")


def test_hf():
    key = os.environ.get("HF_API_KEY", "")
    if not key:
        print("HF_API_KEY    : not set, skipping")
        return
    try:
        t0 = time.time()
        r = httpx.post(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2",
            headers={"Authorization": f"Bearer {key}"},
            json={"inputs": f"<s>[INST] {PROMPT} [/INST]", "parameters": {"max_new_tokens": 10}},
            timeout=60,
        )
        print(f"HUGGINGFACE   : HTTP {r.status_code} in {time.time()-t0:.1f}s")
        print(f"  body        : {r.text[:300]}")
    except Exception as e:
        print(f"HUGGINGFACE   : EXCEPTION -> {e}")


def test_ollama():
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama2")
    try:
        t0 = time.time()
        r = httpx.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": PROMPT, "stream": False},
            timeout=60,
        )
        print(f"OLLAMA        : HTTP {r.status_code} in {time.time()-t0:.1f}s  ({host}, model={model})")
        print(f"  body        : {r.text[:300]}")
    except Exception as e:
        print(f"OLLAMA        : EXCEPTION -> {e} ({host})")


if __name__ == "__main__":
    print("=" * 60)
    print("LLM Provider Diagnostic")
    print("=" * 60)
    test_groq()
    print()
    test_nvidia()
    print()
    test_hf()
    print()
    test_ollama()
    print("=" * 60)
