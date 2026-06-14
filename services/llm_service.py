"""
LLM Service: Multi-provider LLM integration for TeleNOC AI

Supports:
- Ollama (local, fallback) - llama2/mistral/phi
- Groq API (Llama3-70B) - primary for agent reasoning
- HuggingFace Inference API (Mistral-7B) - fallback
- NVIDIA API (Llama/Nemotron) - premium model tier

Environment variables:
  - GROQ_API_KEY: Groq API key
  - HF_API_KEY: HuggingFace Inference API key
  - NVIDIA_API_KEY: NVIDIA API key
  - OLLAMA_HOST: Ollama server URL (default: http://ollama:11434)
  - LLM_PROVIDER: Preferred provider (groq|huggingface|nvidia|ollama)
  - LLM_MODEL: Model name for Ollama
"""

import os
import requests
import json
import logging
from typing import Dict, Any, Optional, List
import re

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
        
        # API Keys
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.hf_api_key = os.environ.get("HF_API_KEY", "") 
        self.nvidia_api_key = os.environ.get("NVIDIA_API_KEY", "")
        
        logger.info(
            f"Initializing LLM service | Provider: {self.preferred_provider} | "
            f"Ollama fallback: {self.model_name} | "
            f"Groq: {'✓' if self.groq_api_key else '✗'} | "
            f"NVIDIA: {'✓' if self.nvidia_api_key else '✗'} | "
            f"HF: {'✓' if self.hf_api_key else '✗'}"
        )

    def is_available(self) -> bool:
        """Check if any LLM provider is available."""
        # Check API-based providers first
        if self.groq_api_key:
            return True
        if self.nvidia_api_key:
            return True
        if self.hf_api_key:
            return True
        # Fallback to Ollama
        try:
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

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
        priority = ["groq", "nvidia", "huggingface", "ollama"]
        
        # Remove providers without API keys
        available = []
        for p in priority:
            if p == "groq" and self.groq_api_key:
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
        if provider == "groq":
            return self._call_groq(prompt, temperature, max_tokens)
        elif provider == "nvidia":
            return self._call_nvidia(prompt, temperature, max_tokens)
        elif provider == "huggingface":
            return self._call_huggingface(prompt, temperature, max_tokens)
        elif provider == "ollama":
            return self._call_ollama(prompt, temperature, max_tokens)
        else:
            return {"error": f"Unknown provider: {provider}"}

    def _call_groq(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> Dict[str, Any]:
        """Call Groq API with Llama3-70B."""
        if not self.groq_api_key:
            return {"error": "No Groq API key configured"}
        
        import httpx
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama3-70b-8192",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
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
        
        import httpx
        response = httpx.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.nvidia_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "meta/llama3-70b-instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": 0.9,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
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
        
        import httpx
        
        # Format prompt for Mistral-7B-Instruct
        formatted_prompt = f"<s>[INST] {prompt} [/INST]"
        
        response = httpx.post(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2",
            headers={"Authorization": f"Bearer {self.hf_api_key}"},
            json={
                "inputs": formatted_prompt,
                "parameters": {
                    "max_new_tokens": max_tokens,
                    "temperature": temperature,
                    "return_full_text": False,
                    "top_p": 0.9,
                },
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        
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
            
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json=payload,
                timeout=120,
            )
            
            if response.status_code != 200:
                return {"error": f"Ollama returned {response.status_code}"}
            
            result = response.json()
            return {
                "response": result.get("response", ""),
                "stop_reason": result.get("stop_reason", "stop"),
                "eval_count": result.get("eval_count", 0),
                "eval_duration": result.get("eval_duration", 0),
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
