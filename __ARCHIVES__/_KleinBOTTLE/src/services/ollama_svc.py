"""Ollama API client for text generation."""

from __future__ import annotations

from typing import Callable, List, Optional
import threading
import ollama


class OllamaService:
    """Wraps all Ollama API interactions."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    def is_online(self) -> bool:
        try:
            ollama.list()
            return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        try:
            return [m["name"] for m in ollama.list()["models"]]
        except Exception:
            return []

    def generate(self, model: str, prompt: str) -> str:
        """Synchronous single-prompt generation. Returns response text."""
        response = ollama.generate(model=model, prompt=prompt)
        return response["response"]

    def chat(self, model: str, messages: List[dict]) -> str:
        """Synchronous chat-style generation. Returns assistant message text."""
        response = ollama.chat(model=model, messages=messages)
        return response["message"]["content"].strip()

    def generate_async(self, model: str, prompt: str,
                       on_success: Callable[[str], None],
                       on_error: Callable[[str], None],
                       scheduler: Optional[Callable] = None):
        """Run generation in a background thread.

        Args:
            scheduler: A function like root.after(0, fn) to dispatch callbacks
                       on the main thread. If None, callbacks run on the worker thread.
        """
        def _dispatch(fn, *args):
            if scheduler:
                scheduler(0, lambda: fn(*args))
            else:
                fn(*args)

        def worker():
            try:
                result = self.generate(model, prompt)
                _dispatch(on_success, result)
            except Exception as e:
                _dispatch(on_error, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def chat_async(self, model: str, messages: List[dict],
                   on_success: Callable[[str], None],
                   on_error: Callable[[str], None],
                   scheduler: Optional[Callable] = None):
        """Run chat in a background thread."""
        def _dispatch(fn, *args):
            if scheduler:
                scheduler(0, lambda: fn(*args))
            else:
                fn(*args)

        def worker():
            try:
                result = self.chat(model, messages)
                _dispatch(on_success, result)
            except Exception as e:
                _dispatch(on_error, str(e))

        threading.Thread(target=worker, daemon=True).start()
