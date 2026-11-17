"""Klien Shopee Affiliate Open API (GraphQL).

CATATAN: nama argumen/field GraphQL di bawah berdasarkan dokumentasi publik dan
SDK komunitas. Cocokkan dengan dokumentasi Open API di dashboard afiliasi Anda
sebelum dipakai rutin.
"""
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

DEFAULT_ENDPOINT = "https://open-api.affiliate.shopee.co.id/graphql"
RATE_LIMIT_CODE = "10030"


class ShopeeError(RuntimeError):
    pass


class ShopeeAffiliateClient:
    def __init__(
        self,
        app_id: Optional[str] = None,
        secret: Optional[str] = None,
        endpoint: Optional[str] = None,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
        db=None,
    ):
        db_app_id = db.get_setting("shopee_app_id") if db else None
        db_secret = db.get_setting("shopee_app_secret") if db else None

        self.app_id = app_id or db_app_id or os.getenv("SHOPEE_APP_ID", "")
        self.secret = secret or db_secret or os.getenv("SHOPEE_APP_SECRET", "")
        self.endpoint = endpoint or os.getenv("SHOPEE_GRAPHQL_URL", DEFAULT_ENDPOINT)
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._sleep = time.sleep
        if not self.app_id or not self.secret:
            raise ValueError(
                "SHOPEE_APP_ID dan SHOPEE_APP_SECRET belum dikonfigurasi. "
                "Silakan atur di Tab Pengaturan Dashboard (/admin) atau file .env"
            )

    def _sign(self, payload_str: str, timestamp: str) -> str:
        factor = f"{self.app_id}{timestamp}{payload_str}{self.secret}"
        return hashlib.sha256(factor.encode("utf-8")).hexdigest()

    def _headers(self, payload_str: str) -> Dict[str, str]:
        timestamp = str(int(time.time()))
        signature = self._sign(payload_str, timestamp)
        return {
            "Content-Type": "application/json",
            "Authorization": (
                f"SHA256 Credential={self.app_id}, "
                f"Timestamp={timestamp}, Signature={signature}"
            ),
        }

    def _execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        # String yang ditandatangani harus identik dengan body yang dikirim.
        payload_str = json.dumps(payload, separators=(",", ":"))

        last_error = "tidak diketahui"
        for attempt in range(self.max_retries + 1):
            resp = self.session.post(
                self.endpoint,
                data=payload_str.encode("utf-8"),
                headers=self._headers(payload_str),
                timeout=20,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                self._sleep(2 ** attempt)
                continue
            resp.raise_for_status()

            body = resp.json()
            errors = body.get("errors")
            if errors:
                if RATE_LIMIT_CODE in json.dumps(errors):
                    last_error = "rate limit (10030)"
                    self._sleep(2 ** attempt)
                    continue
                raise ShopeeError(f"Shopee GraphQL error: {errors}")
            return body.get("data") or {}

        raise ShopeeError(f"Gagal setelah {self.max_retries + 1} percobaan: {last_error}")

    def search_products(
        self,
        keyword: str = "",
        page: int = 1,
        limit: int = 20,
        sort_type: int = 2,  # 2 = terlaris, 5 = komisi tertinggi
    ) -> List[Dict[str, Any]]:
        query = """
        query ProductSearch($keyword: String, $page: Int, $limit: Int, $sortType: Int) {
          productOfferV2(keyword: $keyword, page: $page, limit: $limit, sortType: $sortType) {
            nodes {
              itemId productName productLink offerLink imageUrl
              priceMin priceMax priceDiscountRate sales ratingStar
              commissionRate commission shopName
            }
            pageInfo { page limit hasNextPage }
          }
        }
        """
        variables: Dict[str, Any] = {"page": page, "limit": limit, "sortType": sort_type}
        if keyword:
            variables["keyword"] = keyword
        data = self._execute(query, variables)
        return (data.get("productOfferV2") or {}).get("nodes") or []

    def generate_affiliate_link(self, origin_url: str, sub_ids: Optional[List[str]] = None) -> str:
        """Short link afiliasi dengan sub-ID (maks 5) agar konversi bisa dilacak per posting."""
        mutation = """
        mutation GenerateLink($input: ShortLinkInput!) {
          generateShortLink(input: $input) { shortLink }
        }
        """
        variables = {"input": {"originUrl": origin_url, "subIds": (sub_ids or [])[:5]}}
        data = self._execute(mutation, variables)
        link = (data.get("generateShortLink") or {}).get("shortLink") or ""
        if not link:
            raise ShopeeError("generateShortLink tidak mengembalikan shortLink")
        return link
