"""Ekstraktor data produk Shopee dari URL publik & link affiliate.
Menerapkan IProductScraper (Single Responsibility & Interface Segregation).
Mengambil foto & video resmi asli dari penjual (REAL SELLER MEDIA, BUKAN AI).
Menggunakan user-agent WhatsApp untuk bypass anti-bot dan mengekstrak OpenGraph metadata resmi.
Dilengkapi proteksi pertahanan SSRF (Server-Side Request Forgery).
"""
import re
import ipaddress
import socket
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional
from core.interfaces import IProductScraper

SHOPEE_CATEGORIES = [
    "Elektronik & Gadget",
    "Komputer & Aksesoris",
    "Pakaian Pria",
    "Pakaian Wanita",
    "Otomotif & Kendaraan",
    "Rumah Tangga & Dekorasi",
    "Kecantikan & Perawatan",
    "Kesehatan",
    "Olahraga & Outdoor",
    "Makanan & Minuman",
    "Ibu & Bayi",
    "Hobi & Koleksi",
]

_CATEGORY_KEYWORDS = {
    "Elektronik & Gadget": [
        "speaker", "tws", "earphone", "headphone", "lampu", "kabel", "charger",
        "powerbank", "kipas", "adaptor", "casing", "case", "holder", "tripod",
        "tongsis", "screen protector", "tempered glass", "hp", "handphone", "fast charging"
    ],
    "Komputer & Aksesoris": [
        "mouse", "keyboard", "laptop", "monitor", "usb", "hub", "mousepad", "stand laptop"
    ],
    "Pakaian Pria": [
        "kaos pria", "kemeja pria", "celana pria", "jaket pria", "hoodie pria",
        "t-shirt", "oversized", "boxer", "polo", "distro", "jogger pria"
    ],
    "Pakaian Wanita": [
        "dress", "blouse", "rok", "tunik", "cardigan", "celana wanita", "tas wanita", "gamis", "hijab"
    ],
    "Otomotif & Kendaraan": [
        "mobil", "motor", "car charger", "cuci mobil", "snow foam", "sprayer",
        "shampoo mobil", "wax", "helm", "holder motor", "parfum mobil", "lap microfiber", "jas hujan"
    ],
    "Rumah Tangga & Dekorasi": [
        "organizer", "rak", "botol minum", "tumbler", "kotak makan", "spatula",
        "wadah", "gantungan", "dekorasi", "alat masak", "sprei", "bor", "cordless drill", "perkakas"
    ],
    "Kecantikan & Perawatan": [
        "serum", "sunscreen", "moisturizer", "sabun", "shampoo", "skincare", "parfum", "lipstik"
    ],
    "Kesehatan": [
        "masker", "duckbill", "vitamin", "suplemen", "timbangan", "alat pijat", "termometer"
    ],
    "Olahraga & Outdoor": [
        "matras yoga", "dumbell", "tenda", "sepatu", "sneakers", "jersey", "short pants", "training"
    ],
    "Makanan & Minuman": [
        "kopi", "snack", "keripik", "basreng", "teh", "madu", "sambal", "kue", "eatsambel"
    ],
}


def is_safe_url(url: str) -> bool:
    """Proteksi SSRF: Validasi skema, host, dan larang akses ke private/loopback IP."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        hostname_lower = hostname.lower()
        if hostname_lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "169.254.169.254"):
            return False

        # Verifikasi IP address apakah berada dalam range private RFC 1918 / loopback
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for addr in addr_info:
                ip_str = addr[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                    return False
        except Exception:
            return False
        return True
    except Exception:
        return False


def detect_category(title: str) -> str:
    """Mendeteksi kategori produk berdasarkan kata kunci di judul."""
    title_lower = title.lower()
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in title_lower:
                return cat
    return "Rumah Tangga & Dekorasi"


def extract_item_id(url: str) -> str:
    """Mengekstrak ID produk unik dari URL Shopee."""
    match = re.search(r"-i\.(\d+)\.(\d+)", url)
    if match:
        return match.group(2)
    match2 = re.search(r"/product/(\d+)/(\d+)", url)
    if match2:
        return match2.group(2)
    clean_path = url.split("?")[0].rstrip("/")
    slug = clean_path.split("/")[-1]
    return re.sub(r"[^a-zA-Z0-9_]", "", slug) or "item_manual"


def resolve_url(url: str, timeout: int = 10) -> str:
    """Mengikuti redirect URL pendek jika aman dari SSRF."""
    if not is_safe_url(url):
        return url

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "WhatsApp/2.21.12.21 A"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.geturl()
            return final_url if is_safe_url(final_url) else url
    except Exception:
        return url


class ShopeePublicScraper(IProductScraper):
    """Implementasi scraper publik untuk link Shopee menggunakan WhatsApp bot preview.
    Mengambil cover resmi penjual (og:image) dan video asli jika tersedia.
    """

    def scrape_preview(self, url: str) -> Dict[str, Any]:
        if not is_safe_url(url):
            raise ValueError("URL yang dimasukkan tidak valid atau mengarah ke target jaringan privat/terlarang.")

        resolved = resolve_url(url)
        item_id = extract_item_id(resolved)

        # Gunakan WhatsApp UA yang sudah terbukti lolos dari anti-bot Shopee
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "WhatsApp/2.21.12.21 A",
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

        title = ""
        image_url = ""
        video_url = ""
        description = ""

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")

                # Judul Resmi
                m_title = re.search(r'property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.I)
                if not m_title:
                    m_title = re.search(r'<title>(.*?)</title>', html, re.I)
                if m_title:
                    raw_title = m_title.group(1).strip()
                    title = re.sub(r'^(Jual\s+|Beli\s+)', '', raw_title, flags=re.I)
                    title = title.replace(" | Shopee Indonesia", "").strip()

                # Foto Cover Resmi Penjual
                m_img = re.search(r'property=["\']og:image["\']\s+content=["\'](.*?)["\']', html, re.I)
                if m_img:
                    image_url = m_img.group(1).strip()

                # Video Asli Penjual (jika ada, prioritaskan video dari CDN resmi Shopee)
                clean_html = html.replace(r'\/', '/')
                m_vid = re.search(r'property=["\']og:video["\']\s+content=["\'](.*?)["\']', clean_html, re.I)
                if not m_vid:
                    m_vid = re.search(r'property=["\']og:video:url["\']\s+content=["\'](.*?)["\']', clean_html, re.I)
                if not m_vid:
                    m_vid = re.search(r'https://cvf\.shopee\.co\.id/[^\s\"\'<>]+', clean_html)
                if not m_vid:
                    m_vid = re.search(r'https://[a-zA-Z0-9_\-\.]*vod\.susercontent\.com/[^\s\"\'<>]+\.(?:mp4|mov)[^\s\"\'<>]*', clean_html, re.I)
                if not m_vid:
                    m_vid = re.search(r'https://[a-zA-Z0-9_\-\.]*vod\.susercontent\.com/[^\s\"\'<>]+', clean_html)
                if not m_vid:
                    m_vid = re.search(r'\"video_url\"\s*:\s*\"(https:[^\"]+)\"', clean_html)
                if not m_vid:
                    m_vid = re.search(r'\"(https://[^\"]+?\.(?:mp4|mov)[^\"]*)\"', clean_html, re.I)
                if m_vid:
                    video_url = m_vid.group(1) if hasattr(m_vid, 'group') and m_vid.lastindex else m_vid.group(0)

                # Deskripsi & Harga
                m_desc = re.search(r'property=["\']og:description["\']\s+content=["\'](.*?)["\']', html, re.I)
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
        media_type = "VIDEO" if video_url else "IMAGE"

        return {
            "item_id": item_id,
            "product_name": title or "Produk Shopee Pilihan",
            "product_url": resolved,
            "image_url": image_url,
            "video_url": video_url,
            "media_type": media_type,
            "price": price,
            "category": detected_cat,
            "description": description
        }


def fetch_shopee_preview(url: str) -> Dict[str, Any]:
    """Helper fungsi backward-compatibility."""
    scraper = ShopeePublicScraper()
    return scraper.scrape_preview(url)
