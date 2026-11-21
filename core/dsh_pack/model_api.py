"""Portable model connection fields. Never resolve or serialize credentials."""
from __future__ import annotations

import json
import os
import re
import subprocess
from urllib.parse import urlsplit

from .errors import ExportError


def endpoint(value):
    if not isinstance(value, str) or len(value) > 1024 or not re.fullmatch(
            r"[A-Za-z0-9.:/\[\]_-]+", value):
        raise ExportError("Model API address must not contain credentials, query, fragment or escapes")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ExportError("Invalid model API address") from None
    go_endpoint = parsed.netloc == "opencode.ai" and parsed.path.rstrip("/") in {
        "/zen/go/v1", "/inference/go/openai/v1", "/inference/go/anthropic/v1", "/inference/go/google/v1beta",
    }
    if (not parsed.hostname or parsed.scheme not in {"http", "https"}
            or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})
            or port == 0 or parsed.netloc.endswith(":")
            or not (go_endpoint or re.fullmatch(r"(?:/(?:api|openai|anthropic|models|compatible-mode|v[0-9]+(?:beta[0-9]*)?))*/*", parsed.path))):
        raise ExportError("Model API requires HTTPS or a local loopback address")
    return value


def identifier(value):
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,127}", value)
            or value in {"constructor", "prototype"} or re.match(r"(?i)(sk-|ghp_|github_pat_)", value)):
        raise ExportError("Unsupported provider or model identifier")
    return value


def validate(summary):
    if not isinstance(summary, dict) or set(summary) != {"providers", "defaultModel"}:
        raise ExportError("Invalid model API summary")
    providers = summary["providers"]
    if not isinstance(providers, dict) or len(providers) > 128:
        raise ExportError("Invalid model provider list")
    for name, entry in providers.items():
        identifier(name)
        if not isinstance(entry, dict) or set(entry) - {"displayName", "api", "baseURL", "models", "apiKeyEnv"}:
            raise ExportError("Unsupported model provider fields")
        if "displayName" in entry:
            label(entry["displayName"])
        if "baseURL" in entry:
            endpoint(entry["baseURL"])
        if "api" in entry:
            identifier(entry["api"])
        if "apiKeyEnv" in entry:
            secret_name(entry["apiKeyEnv"])
        if "models" in entry:
            models = entry["models"]
            if (not isinstance(models, list) or len(models) > 500 or any(
                    not isinstance(model, dict) or "id" not in model or set(model) - {"name", "id"} for model in models)
                    or len({identifier(model["id"]) for model in models}) != len(models)):
                raise ExportError("Invalid model list")
            for model in models:
                if "name" in model:
                    label(model["name"])
    default = summary["defaultModel"]
    if default is not None and (not isinstance(default, dict) or set(default) != {"provider", "model"}
                                or identifier(default["provider"]) not in providers or not identifier(default["model"])):
        raise ExportError("Invalid default model")
    if default is not None:
        listed = providers[default["provider"]].get("models", [])
        if listed and default["model"] not in {model["id"] for model in listed}:
            raise ExportError("Default model is not in the selected provider's model list")
    return summary


def label(value):
    if (not isinstance(value, str) or not re.fullmatch(r"[\w .():/-]{1,128}", value)
            or re.search(r"(?i)\b(?:bearer |sk-|ghp_|github_pat_)", value)):
        raise ExportError("Invalid model display name")


def project(profile, selected):
    path = profile / "cordis.patch.yml"
    empty = {"providers": {}, "defaultModel": None}
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise ExportError("Linked model configuration is not portable")
    if not path.exists():
        if selected:
            raise ExportError("Model provider selection no longer exists")
        return None, empty, []
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ExportError("Model configuration exceeds size limit")
    original = path.read_bytes()
    command = os.environ.get("DSH_PACK_CONFIG_MERGE_COMMAND")
    if not command:
        if selected or any(marker in original for marker in (b"llm-pi-ai", b"agent-default-model", b"apiKeyEnv", b"providers:", b"\\u", b"\\x")):
            raise ExportError("Static YAML adapter required for model API migration")
        return original, empty, []
    raw = original.decode("utf-8-sig")
    result = subprocess.run(json.loads(command), input=json.dumps({"operation": "model-api", "text": raw,
                            "selected": list(selected)}).encode(), capture_output=True, timeout=30,
                            env=dict(os.environ, ELECTRON_RUN_AS_NODE="1"))
    if result.returncode:
        raise ExportError("Cannot safely project the Profile model configuration")
    value = json.loads(result.stdout)
    names = [identifier(name) for name in value["providers"]]
    if set(selected) - set(names):
        raise ExportError("Model providers changed; refresh the export selection")
    chosen = {name: value["providers"][name] for name in selected}
    default = value.get("defaultModel")
    summary = validate({"providers": chosen, "defaultModel": default if default and default.get("provider") in chosen else None})
    return original if raw == value["text"] else value["text"].encode(), summary, names


def secret_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value):
        raise ExportError("Expected a model API key environment variable name, not a value")
    return value
