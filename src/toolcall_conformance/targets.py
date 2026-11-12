"""Targets: what to check (base URL, model, optional key and headers)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .i18n import t


class TargetsError(Exception):
    """Invalid target definition; the message says how to fix it.

    ``str(err)`` is always the English text. Errors raised by this package also carry ``code`` and
    ``params`` so the CLI can show the message in the selected screen language.
    """

    def __init__(self, message: str, code: str = "", params: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.params = params or {}


def _err(code: str, **params: object) -> TargetsError:
    return TargetsError(t(f"err.{code}", "en", **params), code, params)


@dataclass
class Target:
    name: str
    base_url: str
    model: str
    api_key_env: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    mock: bool = False  # set when the server identifies itself as the built-in mock
    unavailable: str = ""  # why the target cannot be checked (e.g. key variable unset); empty if usable
    unavailable_error: TargetsError | None = None  # the same reason with code/params, for localized output

    @property
    def api_key(self) -> str | None:
        """The key value, read from the environment variable named by ``api_key_env``."""
        return os.environ.get(self.api_key_env) if self.api_key_env else None


def validate_url(url: str, where: str, target_name: str | None = None) -> str:
    """Check the scheme. ``target_name`` (instead of ``where``) lets the CLI localize the location."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        if target_name is not None:
            raise TargetsError(t("err.url_scheme", "en", where=f"target {target_name!r}", url=url),
                               "url_scheme_target", {"name": target_name, "url": url})
        raise _err("url_scheme", where=where, url=url)
    return url.rstrip("/")


def make_target(name: str, base_url: str, model: str, api_key_env: str = "",
                headers: dict[str, str] | None = None, notes: str = "",
                require_key: bool = True) -> Target:
    base_url = validate_url(base_url, "", target_name=name)
    if not model:
        raise _err("model_empty", name=name)
    unavailable, unavailable_error = "", None
    if api_key_env and not os.environ.get(api_key_env):
        error = _err("key_unset", name=name, env=api_key_env)
        if require_key:
            raise error
        unavailable, unavailable_error = str(error), error
    return Target(name, base_url, model, api_key_env, dict(headers or {}), notes,
                  unavailable=unavailable, unavailable_error=unavailable_error)


def load_targets(path: str | Path) -> list[Target]:
    """Load ``[[target]]`` tables from a TOML file."""
    p = Path(path)
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise _err("file_missing", path=p) from None
    except tomllib.TOMLDecodeError as err:
        raise _err("toml_invalid", path=p, detail=err) from None
    entries = data.get("target")
    if not isinstance(entries, list) or not entries:
        raise _err("no_targets", path=p)
    targets, seen = [], set()
    for i, entry in enumerate(entries, 1):
        for key in ("name", "base_url", "model"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise _err("target_field", path=p, index=i, key=key)
        if entry["name"] in seen:
            raise _err("target_dup", path=p, name=entry["name"])
        seen.add(entry["name"])
        headers = entry.get("headers", {})
        if not isinstance(headers, dict) or not all(isinstance(v, str) for v in headers.values()):
            raise _err("headers_type", path=p, name=entry["name"])
        targets.append(make_target(entry["name"], entry["base_url"], entry["model"],
                                   entry.get("api_key_env", ""), headers, entry.get("notes", ""),
                                   require_key=False))
    return targets
