"""Targets: what to check (base URL, model, optional key and headers)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


class TargetsError(Exception):
    """Invalid target definition; the message says how to fix it."""


@dataclass
class Target:
    name: str
    base_url: str
    model: str
    api_key_env: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    mock: bool = False  # set when the server identifies itself as the built-in mock

    @property
    def api_key(self) -> str | None:
        """The key value, read from the environment variable named by ``api_key_env``."""
        return os.environ.get(self.api_key_env) if self.api_key_env else None


def validate_url(url: str, where: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise TargetsError(
            f"{where}: base URL {url!r} must start with http:// or https:// "
            "(example: http://localhost:11434/v1)")
    return url.rstrip("/")


def make_target(name: str, base_url: str, model: str, api_key_env: str = "",
                headers: dict[str, str] | None = None, notes: str = "") -> Target:
    base_url = validate_url(base_url, f"target {name!r}")
    if not model:
        raise TargetsError(f"target {name!r}: model must not be empty (pass --model or set `model`)")
    if api_key_env and not os.environ.get(api_key_env):
        raise TargetsError(
            f"target {name!r}: environment variable {api_key_env} is not set. "
            f"Export it (export {api_key_env}=...) or drop api_key_env for servers without auth.")
    return Target(name, base_url, model, api_key_env, dict(headers or {}), notes)


def load_targets(path: str | Path) -> list[Target]:
    """Load ``[[target]]`` tables from a TOML file."""
    p = Path(path)
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TargetsError(f"targets file not found: {p}") from None
    except tomllib.TOMLDecodeError as err:
        raise TargetsError(f"{p}: invalid TOML: {err}") from None
    entries = data.get("target")
    if not isinstance(entries, list) or not entries:
        raise TargetsError(f"{p}: add at least one [[target]] table with name, base_url and model")
    targets, seen = [], set()
    for i, entry in enumerate(entries, 1):
        for key in ("name", "base_url", "model"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise TargetsError(f"{p}: [[target]] #{i} needs a non-empty string `{key}`")
        if entry["name"] in seen:
            raise TargetsError(f"{p}: duplicate target name {entry['name']!r}")
        seen.add(entry["name"])
        headers = entry.get("headers", {})
        if not isinstance(headers, dict) or not all(isinstance(v, str) for v in headers.values()):
            raise TargetsError(f"{p}: target {entry['name']!r}: `headers` must be a table of strings")
        targets.append(make_target(entry["name"], entry["base_url"], entry["model"],
                                   entry.get("api_key_env", ""), headers, entry.get("notes", "")))
    return targets
