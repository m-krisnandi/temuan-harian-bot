"""Ekstraktor data produk Shopee dari URL publik.
Menerapkan IProductScraper (Single Responsibility & Interface Segregation).
Mengambil data resmi yang diizinkan untuk social share preview (OpenGraph metadata: og:title, og:image, og:description).
Mendukung unshortening (s.shopee.co.id, shope.ee) dan klasifikasi kategori Shopee otomatis.
"""
import re
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional
from core.interfaces import IProductScraper

SHOPEE_CATEGORIES = [
    "Elektronik",
    "Komputer & Aksesoris",
    "Handphone & Aksesoris",
    "Pakaian Pria",
    "Pakaian Wanita",
    "Fashion Muslim",
    "Rumah Tangga & Dekorasi",
    "Kecantikan & Perawatan",
    "Kesehatan",
    "Ibu & Bayi",
    "Hobi & Koleksi",
    "Olahraga & Outdoor",
    "Otomotif",
    "Makanan & Minuman",
    "Buku & Alat Tulis",
]

_CATEGORY_KEYWORDS = {
    "Elektronik": ["speaker", "tws", "earphone", "headphone", "lampu", "kabel", "charger", "powerbank", "kipas", "adaptor"],
    "Komputer & Aksesoris": ["mouse", "keyboard", "laptop", "monitor", "usb", "hub", "mousepad", "stand laptop"],
    "Handphone & Aksesoris": ["casing", "case", "holder", "tripod", "screen protector", "tempered glass", "hp"],
    "Pakaian Pria": ["kemeja pria", "kaos pria", "celana pria", "jaket pria", "hoodie pria", "dompet pria"],
    "Pakaian Wanita": ["dress", "blouse", "rok", "tunik", "cardigan", "celana wanita", "tas wanita"],
    "Fashion Muslim": ["hijab", "jilbab", "gamis", "pashmina", "mukena", "baju koko", "sarung", "sajadah"],
    "Rumah Tangga & Dekorasi": ["organizer", "rak", "botol minum", "tumbler", "kotak makan", "spatula", "wadah", "gantungan", "dekorasi", "alat masak", "sprei", "selimut"],
    "Kecantikan & Perawatan": ["serum", "sunscreen", "moisturizer", "sabun", "shampoo", "skincare", "parfum", "lipstik"],
    "Kesehatan": ["masker", "vitamin", "suplemen", "timbangan", "alat pijat", "termometer"],
    "Ibu & Bayi": ["popok", "dot", "stroller", "baju bayi", "mainan edukasi"],
    "Hobi & Koleksi": ["action figure", "lego", "gundam", "diecast", "alat musik", "stiker"],
    "Olahraga & Outdoor": ["matras yoga", "dumbell", "tenda", "sepatu lari", "jersey", "tali skipping"],
    "Otomotif": ["helm", "holder motor", "parfum mobil", "lap microfiber", "sarung motor", "jas hujan"],
    "Makanan & Minuman": ["kopi", "snack", "keripik", "teh", "madu", "sambal", "kue"],
    "Buku & Alat Tulis": ["buku", "pulpen", "agenda", "notebook", "spidol", "pencil"]
}


def detect_category(title: str) -> str:
    title_lower = title.lower()
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in title_lower:
                return cat
    return "Rumah Tangga & Dekorasi"


def extract_item_id(url: str) -> str:
    match = re.search(r"-i\.(\d+)\.(\d+)", url)
    if match:
        return f"{match.group(1)}_{match.group(2)}"
    match2 = re.search(r"/product/(\d+)/(\d+)", url)
    if match2:
        return f"{match2.group(1)}_{match2.group(2)}"
    clean_path = url.split("?")[0].rstrip("/")
    slug = clean_path.split("/")[-1]
    return re.sub(r"[^a-zA-Z0-9_]", "", slug) or "item_manual"


def resolve_url(url: str, timeout: int = 10) -> str:
    """Mengikuti redirect URL pendek jika ada."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl()
    except Exception:
        return url


class ShopeePublicScraper(IProductScraper):
    """Implementasi scraper publik untuk link Shopee menggunakan OpenGraph preview."""

    def scrape_preview(self, url: str) -> Dict[str, Any]:
        resolved = resolve_url(url)
        item_id = extract_item_id(resolved)

        req = urllib.request.Request(
            resolved,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 FacebookExternalHit/1.1",
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

        title = ""
        image_url = ""
        description = ""

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

                m_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.I)
                if not m_title:
                    m_title = re.search(r'<title>(.*?)</title>', html, re.I)
                if m_title:
                    title = m_title.group(1).replace(" | Shopee Indonesia", "").strip()

                m_img = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']', html, re.I)
                if m_img:
                    image_url = m_img.group(1).strip()

                m_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', html, re.I)
                if m_desc:
                    description = m_desc.group(1).strip()
        except Exception:
            pass

        price = 0
        if description:
            m_price = re.search(r"Rp\s?([\d\.]+)", description)
            if m_price:
                try:
                    price = int(m_price.group(1).replace(".", ""))
                except ValueError:
                    price = 0

        detected_cat = detect_category(title)

        return {
            "item_id": item_id,
            "product_name": title or "Produk Shopee",
            "product_url": resolved,
            "image_url": image_url,
            "price": price,
            "category": detected_cat,
            "description": description
        }


def fetch_shopee_preview(url: str) -> Dict[str, Any]:
    """Helper fungsi backward-compatibility."""
    scraper = ShopeePublicScraper()
    return scraper.scrape_preview(url)
