"""HTTP client for the BodySpec API.

Holds no credential. Every method takes an access token as an argument, uses it
for one request, and forgets it - see docs/plans/0008-bodyspec-integration.md
§3. The token is a 60-minute session artifact obtained interactively from
BodySpec's own docs; it is never stored in `helf.db` (the MCP `query` tool has
unrestricted read across the schema), never written to config, and never
logged.

**Nothing in this module may log a token, a header, or a full request object.**
`mqtt_service` logs whole payloads at INFO, so the codebase has no reflex for
this. Log URLs and status codes only.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://app.bodyspec.com"
API_ROOT = "/api/v1/users/me"

# A sync is a few dozen small GETs. Generous enough for a cold upstream,
# short enough that a hung request surfaces well inside the token's lifetime.
TIMEOUT_SECONDS = 30.0

# BodySpec caps page_size at 100. Scans happen ~4 times a year, so one page is
# the whole history for the foreseeable future; pagination is implemented
# anyway because assuming otherwise is how imports silently truncate.
PAGE_SIZE = 100

# The six per-scan sub-resources, keyed by the name they take in the stored
# document. `document.raw` is the merged object, so these keys are what
# `json_extract` paths in later queries will use - changing one is a breaking
# change to stored data, not a rename.
SCAN_SECTIONS = {
    "scan_info": "dexa/scan-info",
    "composition": "dexa/composition",
    "bone_density": "dexa/bone-density",
    "visceral_fat": "dexa/visceral-fat",
    "rmr": "dexa/rmr",
    "percentiles": "dexa/percentiles",
}


class BodySpecError(RuntimeError):
    """Any failure talking to BodySpec."""


class BodySpecAuthError(BodySpecError):
    """The token was rejected.

    Separated from every other failure because it is the one the user will
    actually hit - tokens live 60 minutes - and because the remedy is specific:
    paste a fresh one. Matched on the 401 status, never on the response body,
    which currently reads `{"detail": "Invalid token: Signature has expired"}`
    but is not a contract.
    """


class BodySpecClient:
    """The handful of GETs a sync needs."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = TIMEOUT_SECONDS):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _get(self, token: str, path: str, params: dict | None = None) -> dict:
        url = f"{self._base_url}{API_ROOT}/{path.lstrip('/')}"
        try:
            response = httpx.get(
                url,
                # Constructed here and discarded with the request. Never stored
                # on the client, never returned, never logged.
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # str(exc) on a transport error carries the URL, not the headers.
            raise BodySpecError(f"BodySpec request to {path} failed: {exc}") from exc

        if response.status_code == 401:
            raise BodySpecAuthError(
                "BodySpec rejected the token. They expire after 60 minutes - "
                "paste a fresh one from app.bodyspec.com/docs."
            )
        if response.status_code >= 400:
            # Deliberately not `response.request`: repr'ing a request prints
            # its headers, and the Authorization header is in them.
            raise BodySpecError(
                f"BodySpec returned {response.status_code} for {path}"
            )

        logger.info("BodySpec GET %s -> %s", path, response.status_code)
        return response.json()

    def list_results(self, token: str) -> list[dict]:
        """Every scan, oldest page first, following `has_more`."""
        results: list[dict] = []
        page = 1
        while True:
            payload = self._get(
                token, "results/", params={"page": page, "page_size": PAGE_SIZE}
            )
            results.extend(payload.get("results") or [])
            pagination = payload.get("pagination") or {}
            if not pagination.get("has_more"):
                return results
            page += 1

    def fetch_scan(self, token: str, result_id: str) -> dict:
        """All six sub-resources for one scan, merged into one object.

        Stored whole. Promotion takes thirteen scalars out of well over a
        hundred, so anything not promoted is only recoverable from this.
        """
        return {
            key: self._get(token, f"results/{result_id}/{path}")
            for key, path in SCAN_SECTIONS.items()
        }
