"""Multimodal observation capture from Playwright pages.

Three modalities:
  - a11y_tree (text): Indexed accessibility tree — primary observation, always captured
  - dom (text): Cleaned HTML snapshot — supplementary structural info
  - screenshot (PNG): Page screenshot — supplementary visual info

Usage:
    from shared.observation import capture_observation

    obs = capture_observation(page)                     # a11y tree only (fast)
    obs = capture_observation(page, include_dom=True)   # + DOM HTML
    obs = capture_observation(page, include_screenshot=True)  # + PNG
    obs = capture_observation(page, include_dom=True, include_screenshot=True)  # all three

    # Backward-compatible text output
    text = obs.to_text(instruction="Find the email...")

    # Multimodal dict output
    data = obs.to_dict(instruction="Find the email...")
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Observation:
    """Multimodal observation from a browser page."""

    a11y_tree: str
    ref_map: dict[int, Any]
    dom: str = ""
    screenshot_base64: str = ""
    screenshot_bytes: bytes = field(default=b"", repr=False)
    url: str = ""
    viewport: dict[str, int] = field(default_factory=dict)

    def to_text(self, instruction: str = "", status: str = "") -> str:
        """Format as text-only observation (backward compatible with agent.py)."""
        from shared.format import build_initial_message, build_step_message

        if instruction:
            return build_initial_message(instruction, self.a11y_tree)
        if status:
            return build_step_message(status, self.a11y_tree)
        return self.a11y_tree

    def to_dict(self, instruction: str = "", status: str = "") -> dict[str, Any]:
        """Format as multimodal observation dict."""
        result: dict[str, Any] = {
            "a11y_tree": self.a11y_tree,
            "url": self.url,
            "viewport": self.viewport,
        }
        if self.dom:
            result["dom"] = self.dom
        if self.screenshot_base64:
            result["screenshot"] = self.screenshot_base64
        if instruction:
            result["instruction"] = instruction
        if status:
            result["status"] = status
        return result


def capture_observation(
    page: Any,
    *,
    include_dom: bool = False,
    include_screenshot: bool = False,
    dom_max_length: int = 50_000,
) -> Observation:
    """Capture multimodal observation from a Playwright page.

    The a11y tree is always captured. DOM and screenshot are optional.
    """
    from shared.playwright_adapter import page_to_indexed_tree

    tree_text, ref_map = page_to_indexed_tree(page)

    dom = ""
    if include_dom:
        try:
            dom = _clean_dom(page.content(), dom_max_length)
        except Exception:
            pass

    screenshot_b64 = ""
    screenshot_bytes = b""
    if include_screenshot:
        try:
            screenshot_bytes = page.screenshot(type="png")
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("ascii")
        except Exception:
            pass

    url = ""
    viewport: dict[str, int] = {}
    try:
        url = page.url
        viewport = page.evaluate(
            """() => ({
            width: window.innerWidth,
            height: window.innerHeight,
            scrollTop: document.documentElement.scrollTop || document.body.scrollTop,
            scrollHeight: document.documentElement.scrollHeight,
        })"""
        )
    except Exception:
        pass

    return Observation(
        a11y_tree=tree_text,
        ref_map=ref_map,
        dom=dom,
        screenshot_base64=screenshot_b64,
        screenshot_bytes=screenshot_bytes,
        url=url,
        viewport=viewport,
    )


def _clean_dom(html: str, max_length: int) -> str:
    """Strip scripts, styles, and SVGs from HTML; truncate to max_length."""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<svg[^>]*>.*?</svg>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'\s+on\w+="[^"]*"', "", html)
    html = re.sub(r'\s+data-[a-z-]+="[^"]*"', "", html)
    html = re.sub(r"\s+", " ", html).strip()
    if len(html) > max_length:
        html = html[:max_length] + "\n<!-- DOM truncated -->"
    return html
