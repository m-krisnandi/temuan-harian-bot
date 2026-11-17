"""Scout Produk Unik & Viral Shopee Otomatis (Web / Playwright Engine).
Dapat berjalan tanpa Open API Shopee dengan memanfaatkan pelacakan an_redir Shopee.
Seluruh konfigurasi dibaca dinamis dari database settings dan .env (tanpa hardcode).
"""
import os
import sys
import time
import re
import urllib.parse
from typing import List, Dict, Any, Optional

from database import ProductQueueDB
from captions import build_caption


def create_affiliate_link(product_url: str, affiliate_id: str, sub_id: str = "temuanharian") -> str:
    """
    Mengonversi link produk Shopee menjadi link affiliate universal tanpa Open API.
    Format resmi Shopee: an_redir?origin_link=<ENCODED_URL>?&affiliate_id=<ID>&sub_id=<SUB_ID>
    """
    if not affiliate_id:
        return product_url
    clean_url = product_url.split("?")[0] if "?" in product_url else product_url
    encoded_url = urllib.parse.quote(clean_url, safe="")
    return f"https://s.shopee.co.id/an_redir?origin_link={encoded_url}?&affiliate_id={affiliate_id}&sub_id={sub_id}"


def parse_sales_count(text: str) -> int:
    """Mengubah format '1,2RB terjual' atau '10RB+ terjual' menjadi integer."""
    if not text:
        return 0
    t = text.lower().replace("+", "").replace("terjual", "").strip()
    try:
        if "rb" in t or "k" in t:
            num = t.replace("rb", "").replace("k", "").replace(",", ".").strip()
            return int(float(num) * 1000)
        return int(re.sub(r"[^\d]", "", t))
    except Exception:
        return 0


def parse_price(text: str) -> float:
    """Mengubah format 'Rp45.000' atau 'Rp 15.000 - Rp 35.000' menjadi float (harga minimal)."""
    if not text:
        return 0.0
    t = text.split("-")[0].strip()
    digits = re.sub(r"[^\d]", "", t)
    try:
        return float(digits)
    except Exception:
        return 0.0


def scrape_viral_products_playwright(
    keyword: str,
    limit: int = 10,
    min_sales: int = 300,
    min_rating: float = 4.8
) -> List[Dict[str, Any]]:
    """
    Membuka Shopee Web pencarian produk terlaris dengan Playwright headless browser,
    mengekstrak data barang viral secara otomatis.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[WARN] Playwright belum terpasang. Jalankan: pip install playwright && playwright install chromium")
        return []

    results = []
    search_url = f"https://shopee.co.id/search?keyword={urllib.parse.quote(keyword)}&sortBy=sales"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="id-ID",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        print(f"[SCOUT] Membuka pencarian Shopee: '{keyword}' (sort: terlaris)...")
        try:
            page.goto(search_url, timeout=40000, wait_until="domcontentloaded")
            time.sleep(3)

            for _ in range(4):
                page.mouse.wheel(0, 800)
                time.sleep(1)

            items = page.locator("a[href*='-i.']").all()
            print(f"[SCOUT] Ditemukan {len(items)} calon produk di halaman...")

            for item in items:
                if len(results) >= limit:
                    break

                href = item.get_attribute("href") or ""
                if not href:
                    continue

                full_url = f"https://shopee.co.id{href}" if href.startswith("/") else href
                match = re.search(r"-i\.(\d+)\.(\d+)", href)
                if not match:
                    continue

                item_id = match.group(2)
                text_content = item.inner_text() or ""
                lines = [l.strip() for l in text_content.split("\n") if l.strip()]

                if not lines:
                    continue

                img_el = item.locator("img").first
                img_url = ""
                if img_el.count() > 0:
                    img_url = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

                sales = 0
                for line in lines:
                    if "terjual" in line.lower():
                        sales = parse_sales_count(line)
                        break

                price = 0.0
                for line in lines:
                    if "rp" in line.lower():
                        price = parse_price(line)
                        break

                product_name = ""
                for line in lines:
                    if len(line) > 15 and "rp" not in line.lower() and "terjual" not in line.lower():
                        product_name = line
                        break

                if not product_name:
                    product_name = lines[0]

                if sales < min_sales:
                    continue

                results.append({
                    "item_id": item_id,
                    "product_name": product_name,
                    "product_url": full_url,
                    "image_url": img_url,
                    "price": price,
                    "rating": min_rating,
                    "sales": sales,
                    "discount_rate": 0
                })

        except Exception as e:
            print(f"[ERROR] Scraping Playwright: {e}")
        finally:
            browser.close()

    return results


def run_viral_discovery(auto_approve: bool = False, limit_per_keyword: Optional[int] = None):
    """
    Menjalankan proses kurasi produk unik & viral.
    Semua parameter dibaca dinamis dari database / environment.
    """
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temuan_harian.db")
    db = ProductQueueDB(os.getenv("TEMUAN_DB", db_path))

    # Ambil konfigurasi dinamis dari database settings / .env
    affiliate_id = db.get_setting("shopee_affiliate_id") or os.getenv("SHOPEE_AFFILIATE_ID", "")
    sub_tag = db.get_setting("affiliate_sub_id") or os.getenv("AFFILIATE_SUB_ID", "fb-temuanharian")

    # Ambil daftar kata kunci dari database
    keywords_setting = db.get_setting("auto_scout_keywords") or os.getenv(
        "AUTO_SCOUT_KEYWORDS",
        "barang unik rumah tangga, alat dapur unik viral, gadget unik murah"
    )
    keywords = [k.strip() for k in keywords_setting.split(",") if k.strip()]

    min_sales = int(db.get_setting("min_sales") or os.getenv("MIN_SALES", "300"))
    min_rating = float(db.get_setting("min_rating") or os.getenv("MIN_RATING", "4.8"))
    limit_kw = limit_per_keyword or int(db.get_setting("scout_limit_per_kw") or os.getenv("SCOUT_LIMIT_PER_KW", "5"))

    if db.get_setting("auto_approve_scouted") == "1":
        auto_approve = True

    total_added = 0
    db.log_activity("SCOUT_START", f"Memulai auto-scout produk viral. Kata kunci: {len(keywords)} kategori.")

    for kw in keywords:
        print(f"[SCOUT] Menelusuri kategori: '{kw}'...")
        products = scrape_viral_products_playwright(
            keyword=kw,
            limit=limit_kw,
            min_sales=min_sales,
            min_rating=min_rating
        )

        for p in products:
            if db.exists(p["item_id"]):
                continue

            p["affiliate_link"] = create_affiliate_link(
                p["product_url"],
                affiliate_id=affiliate_id,
                sub_id=f"{sub_tag}-i{p['item_id']}"
            )
            p["caption"] = build_caption(p)

            if db.insert_product(p):
                if auto_approve:
                    db.approve(p["item_id"])
                total_added += 1
                print(f"[SUCCESS] Ditambahkan: {p['product_name'][:45]}... (Terjual: {p['sales']})")

    db.log_activity("SCOUT_DONE", f"Auto-scout selesai. {total_added} produk baru berhasil dimasukkan.")
    print(f"\n[DONE] Total {total_added} produk viral baru berhasil dimasukkan ke sistem.")


if __name__ == "__main__":
    auto = "--approve" in sys.argv
    run_viral_discovery(auto_approve=auto)
