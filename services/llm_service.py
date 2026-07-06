"""
LLM Service: Multi-provider LLM integration for TeleNOC AI

Supports:
- OpenRouter API (primary) - free models, no credit card needed
- Groq API (Llama3-70B) - fast inference fallback
- NVIDIA API (Llama/Nemotron) - premium model tier
- HuggingFace Inference API (Mistral-7B) - fallback
- Ollama (local, last resort) - llama2/mistral/phi

Environment variables:
  - OPENROUTER_API_KEY: OpenRouter API key (get free at openrouter.ai)
  - OPENROUTER_MODEL: Model to use (default: meta-llama/llama-3.3-70b-instruct:free)
  - GROQ_API_KEY: Groq API key
  - HF_API_KEY: HuggingFace Inference API key
  - NVIDIA_API_KEY: NVIDIA API key
  - OLLAMA_HOST: Ollama server URL (default: http://ollama:11434)
  - LLM_PROVIDER: Preferred provider (openrouter|groq|huggingface|nvidia|ollama)
  - LLM_MODEL: Model name for Ollama
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
import re
from urllib import error, request

logger = logging.getLogger(__name__)


class LLMService:
    """
    Multi-provider LLM service with automatic fallback.
    Priority: Groq → NVIDIA → HuggingFace → Ollama
    """
    
    def __init__(self, ollama_host: str = None, model_name: str = "llama2"):
        """
        Initialize LLM service with multiple provider support.
        
        Args:
            ollama_host: Ollama server URL (fallback)
            model_name: Ollama model name
        """
        self.ollama_host = ollama_host or os.environ.get("OLLAMA_HOST", "http://ollama:11434")
        self.model_name = os.environ.get("LLM_MODEL", model_name)
        self.preferred_provider = os.environ.get("LLM_PROVIDER", "groq").lower()
        self.chatqna_host = os.environ.get("CHATQNA_SERVICE_HOST", "chatqna")
        self.chatqna_port = int(os.environ.get("CHATQNA_SERVICE_PORT", "8888"))
        self.chatqna_endpoint = os.environ.get(
            "CHATQNA_ENDPOINT",
            f"http://{self.chatqna_host}:{self.chatqna_port}/v1/chatqna",
        )
        
        # API Keys
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.openrouter_model = os.environ.get(
            "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
        )
        # Free model fallback chain — tried in order if the primary fails
        self._openrouter_free_fallbacks = [
            "meta-llama/llama-3.3-70b-instruct:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "qwen/qwen3-coder:free",
            "meta-llama/llama-3.2-3b-instruct:free",
        ]
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.hf_api_key = os.environ.get("HF_API_KEY", "")
        self.nvidia_api_key = os.environ.get("NVIDIA_API_KEY", "")

        logger.info(
            f"Initializing LLM service | Provider: {self.preferred_provider} | "
            f"Ollama fallback: {self.model_name} | "
            f"OpenRouter: {'✓' if self.openrouter_api_key else '✗'} | "
            f"Groq: {'✓' if self.groq_api_key else '✗'} | "
            f"NVIDIA: {'✓' if self.nvidia_api_key else '✗'} | "
            f"HF: {'✓' if self.hf_api_key else '✗'} | "
            f"ChatQnA: {self.chatqna_endpoint}"
        )

    def _post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        timeout: int = 60,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Call an OPEA-style JSON endpoint using the standard library."""
        body = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        http_request = request.Request(
            url,
            data=body,
            headers=request_headers,
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                content = response.read().decode("utf-8")
                try:
                    return json.loads(content)
                except Exception:
                    return {"response": content}
        except error.HTTPError as exc:
            logger.warning("HTTP error calling %s: %s", url, exc)
        except Exception as exc:
            logger.warning("Request error calling %s: %s", url, exc)
        return None

    def _get_health(self, url: str, timeout: int = 5) -> bool:
        try:
            http_request = request.Request(url, method="GET")
            with request.urlopen(http_request, timeout=timeout) as response:
                return response.status == 200
        except Exception:
            return False

    def _call_opea_chatqna(self, prompt: str) -> Dict[str, Any]:
        """Call the OPEA ChatQnA orchestration pipeline for RAG prompts."""
        payload = {
            "messages": prompt,
            "stream": False,
        }
        # OPEA ChatQnA orchestrates embedding, retrieval, and answer generation.
        response = self._post_json(self.chatqna_endpoint, payload, timeout=120)
        if not response:
            return {"error": "ChatQnA is unavailable"}

        content = (
            response.get("response")
            or response.get("answer")
            or response.get("message")
            or response.get("output")
            or ""
        )
        if not content and isinstance(response.get("data"), dict):
            data = response["data"]
            content = data.get("response") or data.get("answer") or data.get("message") or ""

        if not content:
            return {"error": "ChatQnA returned no response", "raw_response": response}

        return {
            "response": content,
            "provider": "opea-chatqna",
            "raw_response": response,
        }

    def _chatqna_available(self) -> bool:
        """Check whether the OPEA ChatQnA service is reachable."""
        health_candidates = [
            f"http://{self.chatqna_host}:{self.chatqna_port}/health",
            f"http://{self.chatqna_host}:{self.chatqna_port}/v1/health",
        ]
        return any(self._get_health(url) for url in health_candidates)

    def is_available(self) -> bool:
        """Check if any LLM provider is available."""
        # Check API-based providers first
        if self.openrouter_api_key:
            return True
        if self.groq_api_key:
            return True
        if self.nvidia_api_key:
            return True
        if self.hf_api_key:
            return True
        # Fallback to Ollama
        return self._get_health(f"{self.ollama_host}/api/tags")

    def generate_response(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate response from the best available LLM provider.
        Tries providers in priority order, falls back on failure.
        
        Args:
            prompt: Input prompt
            temperature: Creativity level (0.0-1.0)
            max_tokens: Maximum response length
            provider: Force a specific provider (groq|nvidia|huggingface|ollama)
        
        Returns:
            Dict with response text and metadata
        """
        provider = provider or self.preferred_provider
        
        # Try providers in priority order
        providers_to_try = self._get_provider_order(provider)
        
        last_error = None
        for prov in providers_to_try:
            try:
                result = self._call_provider(prov, prompt, temperature, max_tokens)
                if result and not result.get("error"):
                    result["provider"] = prov
                    return result
                last_error = result.get("error") if result else "No response"
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Provider {prov} failed: {e}")
                continue
        
        # All providers failed
        logger.error(f"All LLM providers failed. Last error: {last_error}")
        return {
            "error": f"All providers failed: {last_error}",
            "response": "",
            "provider": "none"
        }

    def _get_provider_order(self, preferred: str) -> List[str]:
        """Get ordered list of providers to try."""
        priority = ["openrouter", "groq", "nvidia", "huggingface", "ollama"]

        # Remove providers without API keys
        available = []
        for p in priority:
            if p == "openrouter" and self.openrouter_api_key:
                available.append(p)
            elif p == "groq" and self.groq_api_key:
                available.append(p)
            elif p == "nvidia" and self.nvidia_api_key:
                available.append(p)
            elif p == "huggingface" and self.hf_api_key:
                available.append(p)
            elif p == "ollama":
                available.append(p)  # Always try Ollama as last resort

        # If preferred is available, move it to front
        if preferred in available:
            available.remove(preferred)
            available.insert(0, preferred)

        return available

    def _call_provider(
        self, provider: str, prompt: str, temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Call a specific LLM provider."""
        if provider == "openrouter":
            return self._call_openrouter(prompt, temperature, max_tokens)
        elif provider == "groq":
            return self._call_groq(prompt, temperature, max_tokens)
        elif provider == "nvidia":
            return self._call_nvidia(prompt, temperature, max_tokens)
        elif provider == "huggingface":
            return self._call_huggingface(prompt, temperature, max_tokens)
        elif provider == "ollama":
            return self._call_ollama(prompt, temperature, max_tokens)
        else:
            return {"error": f"Unknown provider: {provider}"}

    def _call_openrouter(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Call OpenRouter API using free models with automatic fallback chain."""
        if not self.openrouter_api_key:
            return {"error": "No OpenRouter API key configured"}

        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "HTTP-Referer": "https://github.com/telenoc-ai",
            "X-Title": "TeleNOC AI",
        }

        models_to_try = [self.openrouter_model] + [
            m for m in self._openrouter_free_fallbacks if m != self.openrouter_model
        ]

        for model in models_to_try:
            data = self._post_json(
                "https://openrouter.ai/api/v1/chat/completions",
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=60,
                headers=headers,
            )
            if not data:
                logger.warning("OpenRouter: no response from model %s, trying next", model)
                continue
            if "error" in data:
                logger.warning("OpenRouter model %s error: %s, trying next", model, data["error"])
                continue
            choices = data.get("choices") or []
            if not choices:
                logger.warning("OpenRouter model %s returned empty choices, trying next", model)
                continue
            content = choices[0]["message"]["content"]
            if model != self.openrouter_model:
                logger.info("OpenRouter: fell back to free model %s", model)
            return {
                "response": content,
                "model": model,
                "stop_reason": choices[0].get("finish_reason", "stop"),
                "usage": data.get("usage", {}),
            }

        return {"error": f"All OpenRouter free models failed. Tried: {models_to_try}"}

    def _call_groq(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Call Groq API with Llama3-70B."""
        if not self.groq_api_key:
            return {"error": "No Groq API key configured"}

        data = self._post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": "llama3-70b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60,
            headers={"Authorization": f"Bearer {self.groq_api_key}"},
        )
        if not data:
            return {"error": "Groq returned no response"}
        content = data["choices"][0]["message"]["content"]
        
        return {
            "response": content,
            "stop_reason": data["choices"][0].get("finish_reason", "stop"),
            "usage": data.get("usage", {}),
        }

    def _call_nvidia(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Call NVIDIA API for premium LLM inference."""
        if not self.nvidia_api_key:
            return {"error": "No NVIDIA API key configured"}

        data = self._post_json(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            {
                "model": "meta/llama3-70b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": 0.9,
            },
            timeout=60,
            headers={"Authorization": f"Bearer {self.nvidia_api_key}"},
        )
        if not data:
            return {"error": "NVIDIA returned no response"}
        content = data["choices"][0]["message"]["content"]
        
        return {
            "response": content,
            "stop_reason": data["choices"][0].get("finish_reason", "stop"),
            "usage": data.get("usage", {}),
        }

    def _call_huggingface(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Call HuggingFace Inference API with Mistral-7B."""
        if not self.hf_api_key:
            return {"error": "No HuggingFace API key configured"}
        
        # Format prompt for Mistral-7B-Instruct
        formatted_prompt = f"<s>[INST] {prompt} [/INST]"

        data = self._post_json(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2",
            {
                "inputs": formatted_prompt,
                "parameters": {
                    "max_new_tokens": max_tokens,
                    "temperature": temperature,
                    "return_full_text": False,
                    "top_p": 0.9,
                },
            },
            timeout=60,
            headers={"Authorization": f"Bearer {self.hf_api_key}"},
        )
        if not data:
            return {"error": "HuggingFace returned no response"}
        
        # HuggingFace returns list of dicts
        if isinstance(data, list) and len(data) > 0:
            content = data[0].get("generated_text", "")
        else:
            content = str(data)
        
        return {
            "response": content,
            "stop_reason": "stop",
        }

    def _call_ollama(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Call local Ollama instance as fallback."""
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "temperature": temperature,
                "num_predict": max_tokens,
                "stream": False,
            }
            
            response = self._post_json(f"{self.ollama_host}/api/generate", payload, timeout=120)
            if not response:
                return {"error": "Ollama returned no response"}
            return {
                "response": response.get("response", ""),
                "stop_reason": response.get("stop_reason", "stop"),
                "eval_count": response.get("eval_count", 0),
                "eval_duration": response.get("eval_duration", 0),
            }
        
        except Exception as e:
            return {"error": str(e)}

    def structured_reasoning(
        self,
        incident: str,
        context: str,
        temperature: float = 0.5,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate structured reasoning output for incident analysis.
        Parses JSON from LLM response.
        
        Args:
            incident: Incident description
            context: Retrieved context (manuals, logs, past incidents)
            temperature: Lower temperature for more deterministic output
            provider: Force a specific LLM provider
        
        Returns:
            Parsed structured response
        """
        
        prompt = f"""You are a telecom operations expert with deep knowledge of network infrastructure.

INCIDENT:
{incident}

RETRIEVED CONTEXT (manuals, logs, and past incidents):
{context}

Analyze this incident and provide your response in the following JSON format:
{{
    "root_cause": "Clear, concise root cause analysis",
    "evidence": ["List of evidence points from the context"],
    "recommended_actions": [
        {{"step": 1, "action": "First action to take", "rationale": "Why this action"}},
        {{"step": 2, "action": "Second action to take", "rationale": "Why this action"}},
        {{"step": 3, "action": "Third action to take", "rationale": "Why this action"}}
    ],
    "severity": "Critical|High|Medium|Low",
    "similar_incidents": ["Any similar incidents mentioned in context"],
    "confidence_score": 0.85,
    "notes": "Any additional observations or caveats"
}}

Provide ONLY the JSON response, no other text."""

        # OPEA ChatQnA is the first-choice RAG path for incident reasoning.
        response = self._call_opea_chatqna(prompt) if self._chatqna_available() else {"error": "ChatQnA unavailable"}

        if response.get("error"):
            logger.warning("Falling back from OPEA ChatQnA: %s", response["error"])
            response = self.generate_response(
                prompt,
                temperature=temperature,
                max_tokens=2048,
                provider=provider,
            )
        
        if response.get("error"):
            logger.error(f"Error in structured reasoning: {response['error']}")
            return {
                "error": response["error"],
                "structured_response": None,
                "provider": response.get("provider", "unknown"),
            }
        
        # Try to parse JSON from response
        response_text = response.get("response", "")
        try:
            # Extract JSON from response (in case model adds extra text)
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                structured = json.loads(json_match.group(0))
            else:
                structured = json.loads(response_text)
            
            return {
                "error": None,
                "structured_response": structured,
                "raw_response": response_text,
                "provider": response.get("provider", "unknown"),
            }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from LLM response: {e}")
            return {
                "error": "JSON parsing error",
                "structured_response": None,
                "raw_response": response_text,
                "provider": response.get("provider", "unknown"),
            }


# Singleton instance
_llm_service = None


def get_llm_service(ollama_host: str = None, model_name: str = "llama2") -> LLMService:
    """Get or create LLM service singleton"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService(ollama_host, model_name)
    return _llm_service
