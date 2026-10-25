"""Versioned public data only. Refresh never edits an installation or client config."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import base64
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from .common import SKILL, SetupError, json_object
from .public_get import REMOTE, MAX_BYTES

PROTOCOLS = {"openai-chat-completions", "openai-responses", "anthropic-messages", "gemini-native"}
REFRESH_BUDGET = 10.0
REQUEST_TIMEOUT = 3.0
MAX_ATTEMPTS = 3  # Includes index, body, retries and one publication recheck.


def validate(data):
    if not isinstance(data, dict) or set(data) != {"schema_version", "catalog_version", "updated_at", "models"}:
        raise SetupError("catalog_schema_invalid")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise SetupError("catalog_schema_unsupported")
    if type(data["catalog_version"]) is not int or data["catalog_version"] < 1:
        raise SetupError("catalog_version_invalid")
    try:
        if datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise SetupError("catalog_date_invalid") from None
    if not isinstance(data["models"], list) or not data["models"] or len(data["models"]) > 1000:
        raise SetupError("catalog_models_invalid")
    ids = set()
    for model in data["models"]:
        required = {"id", "name", "description", "status", "routes"}
        optional = {"key_groups", "sources"}
        if not isinstance(model, dict) or not required <= set(model) or set(model) - required - optional:
            raise SetupError("catalog_model_schema_invalid")
        if (not isinstance(model["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model["id"])
                or model["id"] in ids or model["status"] not in ("active", "deprecated")):
            raise SetupError("catalog_model_id_invalid")
        ids.add(model["id"])
        if any(not isinstance(model[k], str) or not model[k].strip() or len(model[k]) > 500 for k in ("name", "description")):
            raise SetupError("catalog_text_invalid")
        for key in optional:
            if key in model and (not isinstance(model[key], list) or any(not isinstance(v, str) or len(v) > 1000 for v in model[key])):
                raise SetupError("catalog_metadata_invalid")
        if not isinstance(model["routes"], list) or not model["routes"]:
            raise SetupError("catalog_routes_invalid")
        seen = set()
        for route in model["routes"]:
            if not isinstance(route, dict) or set(route) != {"protocol", "capabilities"}:
                raise SetupError("catalog_route_invalid")
            if route["protocol"] not in PROTOCOLS or route["protocol"] in seen:
                raise SetupError("catalog_protocol_invalid")
            seen.add(route["protocol"])
            caps = route["capabilities"]
            if (not isinstance(caps, dict) or not {"tool_calling", "image_input", "reasoning_efforts"} <= set(caps)
                    or set(caps) - {"tool_calling", "image_input", "reasoning_efforts", "context_window", "max_output_tokens"}):
                raise SetupError("catalog_capabilities_invalid")
            for key in ("tool_calling", "image_input"):
                if caps[key] is not None and type(caps[key]) is not bool:
                    raise SetupError("catalog_capability_type")
            efforts = caps["reasoning_efforts"]
            if efforts is not None and (not isinstance(efforts, list) or not efforts or
                    any(not isinstance(e, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", e) for e in efforts) or len(set(efforts)) != len(efforts)):
                raise SetupError("catalog_reasoning_invalid")
            for key in ("context_window", "max_output_tokens"):
                if caps.get(key) is not None and (type(caps[key]) is not int or caps[key] < 1):
                    raise SetupError("catalog_limit_invalid")
    return data


def manifest(raw):
    data = validate(json_object(raw))
    return {"schema_version": 1, "catalog_version": data["catalog_version"], "sha256": hashlib.sha256(raw).hexdigest()}


def validate_manifest(data):
    if (not isinstance(data, dict) or set(data) != {"schema_version", "catalog_version", "sha256"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or type(data["catalog_version"]) is not int or data["catalog_version"] < 1
            or not isinstance(data["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", data["sha256"])):
        raise SetupError("catalog_manifest_invalid")
    return data


def cache_directory():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Caches"
    else:
        raise SetupError("unsupported_os")
    return base / "setup-aihub/setup-agent-model/catalog"


class PublicFetch:
    """One bounded, credential-free GET budget for the whole selection refresh."""
    def __init__(self):
        self.deadline = time.monotonic() + REFRESH_BUDGET
        self.attempts = 0
        self.events = []

    def __call__(self, name):
        while self.attempts < MAX_ATTEMPTS:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                break
            self.attempts += 1
            delay = min(2 ** (self.attempts - 1), 4)
            try:
                # A socket timeout alone permits slow-drip bodies and DNS to
                # exceed the budget. The worker owns no files and is killable.
                process = subprocess.run([sys.executable, str(Path(__file__).with_name("public_get.py")), name],
                                         capture_output=True, timeout=min(REQUEST_TIMEOUT, remaining))
                result = json_object(process.stdout)
                if process.returncode or not isinstance(result, dict):
                    raise SetupError("catalog_worker_failed")
                if "body" in result:
                    raw = base64.b64decode(result["body"], validate=True)
                    if len(raw) > MAX_BYTES or time.monotonic() > self.deadline:
                        raise SetupError("catalog_budget_or_size_exceeded")
                    return raw
                if not result.get("transient"):
                    raise SetupError(result["error"])
            except subprocess.TimeoutExpired:
                result = {"error": "catalog_request_timeout"}
            retry = result.get("retry_after")
            if retry:
                try:
                    delay = float(retry)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds()
                    except (TypeError, ValueError, OverflowError):
                        pass
                if not math.isfinite(delay) or delay < 0:
                    delay = 2 ** (self.attempts - 1)
                delay = min(delay, 60)
            remaining = self.deadline - time.monotonic()
            if self.attempts >= MAX_ATTEMPTS or delay >= remaining:
                break
            self.events.append({"attempt": self.attempts, "maximum": MAX_ATTEMPTS,
                                "retry_in_seconds": delay, "reason": result["error"]})
            sys.stderr.write(json.dumps({"catalog_retry": self.events[-1]}) + "\n")
            time.sleep(delay)
        raise SetupError("catalog_network_unavailable")


def _read_pair(directory):
    raw = (directory / "models.json").read_bytes()
    if len(raw) > MAX_BYTES:
        raise SetupError("catalog_too_large")
    index = validate_manifest(json_object((directory / "models.manifest.json").read_bytes()))
    if manifest(raw) != index:
        raise SetupError("catalog_integrity_failed")
    return raw, index


def _atomic(path, raw):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".catalog-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(*, refresh=True, cache=None, baseline=None, fetch=None):
    cache = Path(cache) if cache else cache_directory()
    baseline = Path(baseline) if baseline else SKILL / "data"
    valid = []
    for directory, source in ((baseline, "packaged"), (cache / "last-valid", "cache"), (cache, "cache")):
        try:
            raw, index = _read_pair(directory)
            valid.append((index["catalog_version"], raw, index, source))
        except (OSError, SetupError):
            continue
    if not valid:
        raise SetupError("no_valid_model_catalog")
    _, raw, index, source = max(valid, key=lambda item: item[0])
    status = "offline" if not refresh else "checked"
    reason = None
    if refresh:
        fetch = fetch or PublicFetch()
        try:
            remote = validate_manifest(json_object(fetch("models.manifest.json")))
            if remote["catalog_version"] == index["catalog_version"] and remote != index:
                raise SetupError("catalog_same_version_changed")
            if remote["catalog_version"] > index["catalog_version"]:
                downloaded = fetch("models.json")
                actual = manifest(downloaded)
                if actual != remote:
                    remote = validate_manifest(json_object(fetch("models.manifest.json")))
                if actual != remote or remote["catalog_version"] <= index["catalog_version"]:
                    raise SetupError("catalog_publication_mismatch")
                cache.mkdir(parents=True, exist_ok=True)
                # Keep one verified generation during the two-file publication.
                # This is public cache data, never a backup of a user's config.
                previous = cache / "last-valid"
                previous.mkdir(exist_ok=True)
                _atomic(previous / "models.json", raw)
                _atomic(previous / "models.manifest.json", (json.dumps(index, indent=2) + "\n").encode())
                # Index is last: interrupted publication yields an invalid cache,
                # never an unchecked body. The packaged baseline remains available.
                _atomic(cache / "models.json", downloaded)
                _atomic(cache / "models.manifest.json", (json.dumps(remote, indent=2) + "\n").encode())
                raw, index, source, status = downloaded, remote, "cache", "refreshed"
        except (SetupError, OSError) as exc:
            status = "fallback"
            reason = exc.reason if isinstance(exc, SetupError) else "catalog_cache_unavailable"
    return {"catalog": validate(json_object(raw)), "manifest": index, "source": source,
            "refresh_status": status, "reason": reason}
