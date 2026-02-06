"""
hana.wordpress — WordPress REST API client.

Handles all WordPress interactions: posts, media, taxonomy.
"""

import hashlib
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

from hana.config import HanaConfig
from hana.errors import (
    AuthError,
    ConflictError,
    MediaError,
    NotFoundError,
    TaxonomyError,
    TransportError,
)
from hana.logger import get_logger
from hana.retry import RetryHandler


class WordPressClient:
    """REST API client for WordPress."""

    CATALOG_ENDPOINT = "/wp-json/wp/v2/catalog-items"
    MEDIA_ENDPOINT = "/wp-json/wp/v2/media"
    TAXONOMY_ENDPOINT = "/wp-json/wp/v2/item-category"

    def __init__(self, config: HanaConfig):
        self._config = config
        self._base_url = config.wp.base_url.rstrip("/")
        self._auth = HTTPBasicAuth(config.wp.user, config.wp.app_password)
        self._session = requests.Session()
        self._session.auth = self._auth
        self._logger = get_logger()
        self._retry = RetryHandler(config.retry)

    def _url(self, endpoint: str) -> str:
        """Build full URL for an endpoint."""
        return urljoin(self._base_url, endpoint)

    def _request_once(
        self,
        method: str,
        url: str,
        sku: str,
        stage: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Make a single HTTP request with error handling (no retry)."""
        try:
            response = self._session.request(method, url, timeout=30, **kwargs)
        except requests.exceptions.Timeout:
            raise TransportError(
                sku=sku,
                stage=stage,
                message=f"Request timeout: {url}",
                payload={"url": url, "method": method},
                retryable=True,
            )
        except requests.exceptions.ConnectionError:
            raise TransportError(
                sku=sku,
                stage=stage,
                message=f"Connection error: {url}",
                payload={"url": url, "method": method},
                retryable=True,
            )
        except requests.exceptions.RequestException as e:
            raise TransportError(
                sku=sku,
                stage=stage,
                message=f"Request error: {e}",
                payload={"url": url, "method": method},
                retryable=False,
            )

        # 5xx errors are retryable (server-side issues)
        if 500 <= response.status_code < 600:
            raise TransportError(
                sku=sku,
                stage=stage,
                message=f"Server error: {response.status_code}",
                http_status=response.status_code,
                payload={"url": url, "method": method},
                retryable=True,
            )

        # 429 Too Many Requests is retryable
        if response.status_code == 429:
            raise TransportError(
                sku=sku,
                stage=stage,
                message="Rate limited (429)",
                http_status=429,
                payload={"url": url, "method": method},
                retryable=True,
            )

        if response.status_code == 401:
            raise AuthError(
                sku=sku,
                stage=stage,
                message="Authentication failed",
                http_status=401,
                payload={"url": url},
            )

        if response.status_code == 403:
            raise AuthError(
                sku=sku,
                stage=stage,
                message="Authorization denied",
                http_status=403,
                payload={"url": url},
            )

        return response

    def _request(
        self,
        method: str,
        endpoint: str,
        sku: str = "",
        stage: str = "request",
        **kwargs: Any,
    ) -> requests.Response:
        """Make an HTTP request with error handling and automatic retry."""
        url = self._url(endpoint)

        return self._retry.execute(
            self._request_once,
            method,
            url,
            sku,
            stage,
            sku=sku,
            stage=stage,
            **kwargs,
        )

    def health_check(self) -> dict[str, Any]:
        """Validate WordPress connection and endpoints."""
        results = {
            "authentication": False,
            "rest_available": False,
            "endpoints": {
                "catalog-items": False,
                "media": False,
                "item-category": False,
            },
        }

        try:
            response = self._request("GET", "/wp-json/", stage="health_check")
            results["rest_available"] = response.status_code == 200
            results["authentication"] = True
        except AuthError:
            results["rest_available"] = True
            return results
        except TransportError:
            return results

        for name, endpoint in [
            ("catalog-items", self.CATALOG_ENDPOINT),
            ("item-category", self.TAXONOMY_ENDPOINT),
            ("media", self.MEDIA_ENDPOINT),
        ]:
            try:
                response = self._request("GET", endpoint, stage="health_check")
                results["endpoints"][name] = response.status_code in (200, 400)
            except Exception:
                pass

        return results

    def find_post_by_sku(self, sku: str) -> dict[str, Any] | None:
        """Find a post by SKU using meta query."""
        page = 1
        per_page = 100

        while True:
            params = {
                "per_page": per_page,
                "page": page,
                "status": "any",
                "meta_key": "sku",
                "meta_value": sku,
            }

            response = self._request(
                "GET",
                self.CATALOG_ENDPOINT,
                sku=sku,
                stage="lookup",
                params=params,
            )

            if response.status_code == 400:
                params_alt = {
                    "per_page": per_page,
                    "page": page,
                    "status": "any",
                    "search": sku,
                }
                response = self._request(
                    "GET",
                    self.CATALOG_ENDPOINT,
                    sku=sku,
                    stage="lookup",
                    params=params_alt,
                )

            if response.status_code != 200:
                return None

            posts = response.json()
            if not posts:
                return None

            for post in posts:
                meta = post.get("meta", {})
                if meta.get("sku") == sku:
                    return post

            total_pages = int(response.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                return None

            page += 1

        return None

    def create_post(
        self,
        sku: str,
        title: str,
        slug: str | None,
        status: str,
        meta_fields: dict[str, Any],
        taxonomy_terms: dict[str, list[int]],
    ) -> dict[str, Any]:
        """Create a new post."""
        payload: dict[str, Any] = {
            "title": title,
            "status": status,
            "meta": meta_fields,
        }

        if slug:
            payload["slug"] = slug

        for taxonomy, term_ids in taxonomy_terms.items():
            payload[taxonomy] = term_ids

        response = self._request(
            "POST",
            self.CATALOG_ENDPOINT,
            sku=sku,
            stage="create_post",
            json=payload,
        )

        if response.status_code == 201:
            return response.json()

        if response.status_code == 400:
            error_data = response.json()
            if "slug" in str(error_data):
                raise ConflictError(
                    sku=sku,
                    stage="create_post",
                    message=f"Slug conflict: {slug}",
                    http_status=400,
                    payload={"slug": slug, "error": error_data},
                )

        raise TransportError(
            sku=sku,
            stage="create_post",
            message=f"Failed to create post: {response.status_code}",
            http_status=response.status_code,
            payload={"response": response.text[:500]},
        )

    def update_post(
        self,
        sku: str,
        post_id: int,
        title: str | None = None,
        slug: str | None = None,
        status: str | None = None,
        meta_fields: dict[str, Any] | None = None,
        taxonomy_terms: dict[str, list[int]] | None = None,
        featured_media: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing post."""
        payload: dict[str, Any] = {}

        if title is not None:
            payload["title"] = title
        if slug is not None:
            payload["slug"] = slug
        if status is not None:
            payload["status"] = status
        if meta_fields is not None:
            payload["meta"] = meta_fields
        if taxonomy_terms is not None:
            for taxonomy, term_ids in taxonomy_terms.items():
                payload[taxonomy] = term_ids
        if featured_media is not None:
            payload["featured_media"] = featured_media

        if not payload:
            return {"id": post_id}

        response = self._request(
            "POST",
            f"{self.CATALOG_ENDPOINT}/{post_id}",
            sku=sku,
            stage="update_post",
            json=payload,
        )

        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            raise NotFoundError(
                sku=sku,
                stage="update_post",
                message=f"Post not found: {post_id}",
                http_status=404,
                payload={"post_id": post_id},
            )

        raise TransportError(
            sku=sku,
            stage="update_post",
            message=f"Failed to update post: {response.status_code}",
            http_status=response.status_code,
            payload={"post_id": post_id, "response": response.text[:500]},
        )

    def delete_post(self, sku: str, post_id: int, force: bool = True) -> bool:
        """Delete a post."""
        params = {"force": "true"} if force else {}

        response = self._request(
            "DELETE",
            f"{self.CATALOG_ENDPOINT}/{post_id}",
            sku=sku,
            stage="delete_post",
            params=params,
        )

        return response.status_code in (200, 204)

    def get_taxonomy_term(
        self, sku: str, taxonomy: str, term_slug: str
    ) -> dict[str, Any] | None:
        """Get a taxonomy term by slug."""
        params = {"slug": term_slug}

        endpoint = f"/wp-json/wp/v2/{taxonomy}"
        response = self._request(
            "GET",
            endpoint,
            sku=sku,
            stage="taxonomy_lookup",
            params=params,
        )

        if response.status_code != 200:
            return None

        terms = response.json()
        if terms:
            return terms[0]

        return None

    def resolve_taxonomy_terms(
        self, sku: str, taxonomy: str, term_slugs: list[str], fallback: str | None = None
    ) -> tuple[list[int], list[str]]:
        """
        Resolve taxonomy term slugs to IDs.

        Returns:
            Tuple of (resolved_term_ids, warnings)
        """
        term_ids = []
        warnings = []

        for slug in term_slugs:
            term = self.get_taxonomy_term(sku, taxonomy, slug)
            if term:
                term_ids.append(term["id"])
            else:
                warnings.append(f"Term not found: {taxonomy}/{slug}")
                if fallback:
                    fallback_term = self.get_taxonomy_term(sku, taxonomy, fallback)
                    if fallback_term and fallback_term["id"] not in term_ids:
                        term_ids.append(fallback_term["id"])
                        warnings.append(f"Using fallback term: {fallback}")

        return term_ids, warnings

    def upload_media(
        self,
        sku: str,
        file_path: Path,
        checksum: str | None = None,
    ) -> dict[str, Any]:
        """Upload a media file."""
        if not file_path.exists():
            raise MediaError(
                sku=sku,
                stage="media_upload",
                message=f"File not found: {file_path}",
                payload={"file_path": str(file_path)},
            )

        filename = file_path.name
        content_type = self._guess_content_type(filename)

        with open(file_path, "rb") as f:
            file_data = f.read()

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": content_type,
        }

        response = self._request(
            "POST",
            self.MEDIA_ENDPOINT,
            sku=sku,
            stage="media_upload",
            headers=headers,
            data=file_data,
        )

        if response.status_code == 201:
            media = response.json()

            if checksum:
                self._set_media_meta(sku, media["id"], "hana_checksum", checksum)

            return media

        raise MediaError(
            sku=sku,
            stage="media_upload",
            message=f"Failed to upload media: {response.status_code}",
            http_status=response.status_code,
            payload={"file_path": str(file_path), "response": response.text[:500]},
        )

    def find_media_by_checksum(self, sku: str, checksum: str) -> dict[str, Any] | None:
        """Find media by checksum stored in meta."""
        params = {
            "meta_key": "hana_checksum",
            "meta_value": checksum,
            "per_page": 1,
        }

        response = self._request(
            "GET",
            self.MEDIA_ENDPOINT,
            sku=sku,
            stage="media_lookup",
            params=params,
        )

        if response.status_code != 200:
            return None

        media = response.json()
        return media[0] if media else None

    def find_media_by_filename(self, sku: str, filename: str) -> dict[str, Any] | None:
        """Find media by filename."""
        params = {
            "search": filename,
            "per_page": 100,
        }

        response = self._request(
            "GET",
            self.MEDIA_ENDPOINT,
            sku=sku,
            stage="media_lookup",
            params=params,
        )

        if response.status_code != 200:
            return None

        for media in response.json():
            if media.get("source_url", "").endswith(filename):
                return media
            if media.get("title", {}).get("rendered", "") == filename:
                return media

        return None

    def delete_media(self, sku: str, media_id: int, force: bool = True) -> bool:
        """Delete a media attachment."""
        params = {"force": "true"} if force else {}

        response = self._request(
            "DELETE",
            f"{self.MEDIA_ENDPOINT}/{media_id}",
            sku=sku,
            stage="media_delete",
            params=params,
        )

        return response.status_code in (200, 204)

    def _set_media_meta(
        self, sku: str, media_id: int, key: str, value: str
    ) -> bool:
        """Set a meta value on media."""
        payload = {"meta": {key: value}}

        response = self._request(
            "POST",
            f"{self.MEDIA_ENDPOINT}/{media_id}",
            sku=sku,
            stage="media_meta",
            json=payload,
        )

        return response.status_code == 200

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        """Guess content type from filename."""
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
            "svg": "image/svg+xml",
            "pdf": "application/pdf",
        }
        return types.get(ext, "application/octet-stream")

    def close(self) -> None:
        """Close the session."""
        self._session.close()
