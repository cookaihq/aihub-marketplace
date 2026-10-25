"""Credential-free catalog GET worker, killed by the parent's wall-clock budget."""
import base64
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request

REMOTE = "https://raw.githubusercontent.com/cookaihq/aihub-marketplace/main/setup-aihub/skills/setup-agent-model/data/"
MAX_BYTES = 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(name):
    if name not in ("models.json", "models.manifest.json"):
        return {"error": "invalid_catalog_resource", "transient": False}
    request = urllib.request.Request(REMOTE + name, headers={
        "Accept": "application/json", "User-Agent": "setup-agent-model/catalog"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=3) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return {"error": "catalog_too_large", "transient": False}
            return {"body": base64.b64encode(raw).decode("ascii")}
    except urllib.error.HTTPError as exc:
        return {"error": "catalog_http_error", "status": exc.code,
                "transient": exc.code in (408, 429) or 500 <= exc.code <= 599,
                "retry_after": exc.headers.get("Retry-After")}
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            return {"error": "catalog_tls_certificate_invalid", "transient": False}
        transient = isinstance(reason, (TimeoutError, socket.gaierror, ConnectionError, ssl.SSLError))
        return {"error": "catalog_network_error", "transient": transient}
    except (TimeoutError, ConnectionError):
        return {"error": "catalog_network_error", "transient": True}
    except (OSError, ValueError):
        return {"error": "catalog_transport_invalid", "transient": False}


if __name__ == "__main__":
    print(json.dumps(fetch(sys.argv[1] if len(sys.argv) == 2 else "")))
