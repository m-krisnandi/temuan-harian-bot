"""Layanan integrasi stok foto komersial bebas royalti (Unsplash & Pexels).
Prinsip: 100% Foto Nyata Fotografer Manusia (BUKAN GENERATE AI).
Aman dari sistem deteksi AI Meta ("Made with AI") dan bebas untuk penggunaan komersial.
"""
import urllib.request
import urllib.parse
import json
from typing import List, Dict, Any, Optional


class StockPhotoService:
    """Mengambil foto komersial nyata dari Unsplash dan Pexels."""

    @staticmethod
    def search_unsplash(query: str, access_key: str, per_page: int = 6) -> List[Dict[str, str]]:
        """Mencari foto di Unsplash via API resmi."""
        if not access_key:
            return []
        
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.unsplash.com/search/photos?query={encoded_query}&per_page={per_page}&orientation=squarish"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Client-ID {access_key.strip()}",
                "User-Agent": "TemuanHarianBot/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for item in data.get("results", []):
                    results.append({
                        "id": item.get("id", ""),
                        "thumb": item.get("urls", {}).get("small", ""),
                        "url": item.get("urls", {}).get("regular", ""),
                        "title": item.get("alt_description") or item.get("description") or query,
                        "photographer": item.get("user", {}).get("name", "Unsplash Creator"),
                        "source": "Unsplash"
                    })
                return results
        except Exception:
            return []

    @staticmethod
    def search_pexels(query: str, api_key: str, per_page: int = 6) -> List[Dict[str, str]]:
        """Mencari foto di Pexels via API resmi."""
        if not api_key:
            return []

        encoded_query = urllib.parse.quote(query)
        url = f"https://api.pexels.com/v1/search?query={encoded_query}&per_page={per_page}&orientation=square"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": api_key.strip(),
                "User-Agent": "TemuanHarianBot/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for item in data.get("photos", []):
                    results.append({
                        "id": str(item.get("id", "")),
                        "thumb": item.get("src", {}).get("medium", ""),
                        "url": item.get("src", {}).get("large", ""),
                        "title": item.get("alt", "") or query,
                        "photographer": item.get("photographer", "Pexels Creator"),
                        "source": "Pexels"
                    })
                return results
        except Exception:
            return []

    @classmethod
    def search(cls, query: str, db: Any = None) -> List[Dict[str, str]]:
        """Mencari foto menggunakan API key yang tersimpan di database."""
        unsplash_key = ""
        pexels_key = ""
        if db:
            unsplash_key = db.get_setting("unsplash_access_key", "") or ""
            pexels_key = db.get_setting("pexels_api_key", "") or ""

        results = []
        if unsplash_key:
            results.extend(cls.search_unsplash(query, unsplash_key, per_page=6))
        if pexels_key and len(results) < 6:
            results.extend(cls.search_pexels(query, pexels_key, per_page=6))

        return results
