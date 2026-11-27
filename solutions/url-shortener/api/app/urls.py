"""URL validation and normalization: the only path to the INSERT."""

from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048
_DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidUrl(ValueError):
    """Raised with a message that is safe to show to the client."""


def normalize_url(raw: object) -> str:
    if not isinstance(raw, str):
        raise InvalidUrl("URL must be a string")
    url = raw.strip()
    if not url:
        raise InvalidUrl("URL must not be empty")
    if len(url) > MAX_URL_LENGTH:
        raise InvalidUrl(f"URL must be at most {MAX_URL_LENGTH} characters")
    # Raw-string check before parsing: urlsplit silently strips tab/CR/LF.
    if any(ord(c) < 32 or ord(c) == 127 or c.isspace() for c in url):
        raise InvalidUrl("URL must not contain whitespace or control characters")
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in _DEFAULT_PORTS or url[len(scheme) : len(scheme) + 3] != "://":
            raise InvalidUrl("URL must start with http:// or https://")
        if not parts.hostname:
            raise InvalidUrl("URL must contain a host")
        if "@" in parts.netloc:
            raise InvalidUrl("URL must not contain credentials")
        port = parts.port  # raises ValueError when invalid
    except InvalidUrl:
        raise
    except ValueError as exc:
        raise InvalidUrl("URL is malformed or has an invalid port") from exc
    host = parts.netloc.lower()
    cut = host.rfind(":")
    if cut > host.rfind("]"):  # strip ":port" (or a dangling ":")
        host = host[:cut]
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        host = f"{host}:{port}"
    return urlunsplit((scheme, host, parts.path or "/", parts.query, parts.fragment))
