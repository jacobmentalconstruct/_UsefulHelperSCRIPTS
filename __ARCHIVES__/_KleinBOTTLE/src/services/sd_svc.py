"""Stable Diffusion (AUTOMATIC1111 WebUI) API client."""

from __future__ import annotations

import base64
import threading
from typing import Callable, List, Optional

import requests


class StableDiffusionService:
    """Wraps all Stable Diffusion WebUI API interactions."""

    def __init__(self, base_url: str = "http://127.0.0.1:7860"):
        self.base_url = base_url

    def is_online(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def get_models(self) -> List[dict]:
        """Fetch available SD models."""
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def get_current_model(self) -> str:
        """Get currently loaded SD model checkpoint name."""
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/options", timeout=10)
            if r.status_code == 200:
                return r.json().get("sd_model_checkpoint", "")
        except Exception:
            pass
        return ""

    def set_model(self, model_title: str):
        """Switch the active SD model (blocking, can take 30-120s)."""
        requests.post(
            f"{self.base_url}/sdapi/v1/options",
            json={"sd_model_checkpoint": model_title},
            timeout=120,
        )

    def txt2img(self, prompt: str, negative_prompt: str = "",
                width: int = 640, height: int = 400,
                steps: int = 25, cfg_scale: float = 7.5,
                sampler: str = "Euler a") -> bytes:
        """Generate an image and return raw PNG bytes."""
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": steps,
            "width": width,
            "height": height,
            "cfg_scale": cfg_scale,
            "sampler_name": sampler,
        }
        response = requests.post(f"{self.base_url}/sdapi/v1/txt2img", json=payload, timeout=120)
        if response.status_code != 200:
            raise Exception(f"SD API returned status {response.status_code}")
        b64_data = response.json()["images"][0]
        return base64.b64decode(b64_data)

    def txt2img_async(self, prompt: str,
                      on_success: Callable[[bytes], None],
                      on_error: Callable[[str], None],
                      scheduler: Optional[Callable] = None,
                      negative_prompt: str = "",
                      width: int = 640, height: int = 400,
                      steps: int = 25, cfg_scale: float = 7.5,
                      sampler: str = "Euler a"):
        """Run txt2img in a background thread."""
        def _dispatch(fn, *args):
            if scheduler:
                scheduler(0, lambda: fn(*args))
            else:
                fn(*args)

        def worker():
            try:
                img_bytes = self.txt2img(
                    prompt, negative_prompt=negative_prompt,
                    width=width, height=height,
                    steps=steps, cfg_scale=cfg_scale, sampler=sampler,
                )
                _dispatch(on_success, img_bytes)
            except Exception as e:
                _dispatch(on_error, str(e))

        threading.Thread(target=worker, daemon=True).start()
