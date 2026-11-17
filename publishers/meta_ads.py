"""Modul Meta Marketing API untuk persiapan otomatisasi iklan (Facebook & Instagram Ads).
Menerapkan IAdsManager (Single Responsibility & Interface Segregation).
Endpoint: https://graph.facebook.com/v25.0/act_<AD_ACCOUNT_ID>
"""
import requests
from typing import Dict, Any, Optional
from core.interfaces import IAdsManager

GRAPH_VERSION = "v25.0"
FB_GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


class MetaAdsError(Exception):
    pass


class MetaAdsManager(IAdsManager):
    """Pengelola kampanye iklan Meta Marketing API."""

    def __init__(self, ad_account_id: str, access_token: str):
        clean_id = ad_account_id.strip()
        if not clean_id.startswith("act_"):
            clean_id = f"act_{clean_id}"
        self.ad_account_id = clean_id
        self.access_token = access_token.strip()

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        params = params or {}
        params["access_token"] = self.access_token
        url = f"{FB_GRAPH_BASE}/{path}"
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if resp.status_code >= 400 or "error" in data:
            raise MetaAdsError(f"Meta Ads API Error: {data.get('error', {}).get('message', resp.text)}")
        return data

    def _post(self, path: str, payload: dict) -> dict:
        payload["access_token"] = self.access_token
        url = f"{FB_GRAPH_BASE}/{path}"
        resp = requests.post(url, data=payload, timeout=30)
        data = resp.json()
        if resp.status_code >= 400 or "error" in data:
            raise MetaAdsError(f"Meta Ads API Error: {data.get('error', {}).get('message', resp.text)}")
        return data

    def get_account_status(self) -> Dict[str, Any]:
        """Memeriksa status akun iklan dan mata uang / saldo yang terdaftar."""
        return self._get(
            self.ad_account_id,
            {"fields": "id,name,account_status,currency,amount_spent,spend_cap"}
        )

    def list_campaigns(self, limit: int = 10) -> list:
        """Mengambil daftar kampanye aktif."""
        data = self._get(
            f"{self.ad_account_id}/campaigns",
            {"fields": "id,name,status,objective,start_time,daily_budget", "limit": limit}
        )
        return data.get("data", [])

    def create_traffic_campaign(self, name: str, daily_budget_idr: int = 50000) -> str:
        """Membuat kampanye iklan traffic / katalog baru (status PAUSED untuk keamanan)."""
        payload = {
            "name": name,
            "objective": "OUTCOME_TRAFFIC",
            "status": "PAUSED",
            "special_ad_categories": "NONE"
        }
        res = self._post(f"{self.ad_account_id}/campaigns", payload)
        return str(res.get("id", ""))
