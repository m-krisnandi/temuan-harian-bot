"""Orkestrasi: scout -> review -> publish (-> retry-comments) + manual-add.
Mendukung multi-platform: Shopee & TikTok Shop.
Mendukung multi-channel social: Facebook Page, Threads, dan Instagram.
Menerapkan Prinsip SOLID & Dependency Injection (DI).

Pemakaian:
  python pipeline.py scout --viral             # Otomatis cari barang unik viral
  python pipeline.py manual-add --name "..." --url "..." --image "..." --category "Elektronik" --gemini
  python pipeline.py review
  python pipeline.py publish [--dry-run]
"""
import argparse
import os
import sys
import time

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda *args, **kwargs: None

from captions import build_comment
from database import ProductQueueDB
from dependencies import (
    get_db,
    get_caption_generator,
    get_publisher_dispatcher,
)
from shopee_client import ShopeeAffiliateClient, ShopeeError


def _num(value, cast=float):
    try:
        return cast(value or 0)
    except (TypeError, ValueError):
        return cast(0)


def cmd_scout(args) -> int:
    db = get_db()
    shopee_app_id = db.get_setting("shopee_app_id") or os.getenv("SHOPEE_APP_ID")

    # Jika flag --viral disetel atau Shopee App ID belum ada di konfigurasi, jalankan web discovery otomatis
    if getattr(args, "viral", False) or not shopee_app_id:
        print("[SCOUT] Menjalankan Auto-Scout Produk Unik & Viral (Web Engine)...")
        from scout_viral import run_viral_discovery
        run_viral_discovery(auto_approve=getattr(args, "approve", False))
        return 0

    shopee = ShopeeAffiliateClient(db=db)
    caption_gen = get_caption_generator(db=db, use_ai=True)
    added = 0
    for page in range(1, args.pages + 1):
        products = shopee.search_products(
            keyword=args.keyword, page=page, limit=args.limit, sort_type=args.sort
        )
        if not products:
            break
        for p in products:
            item_id = str(p.get("itemId") or "")
            if not item_id or db.exists(item_id):
                continue
            sales = _num(p.get("sales"), int)
            rating = _num(p.get("ratingStar"))
            if sales < args.min_sales or rating < args.min_rating:
                continue
            if not p.get("productLink") or not p.get("imageUrl"):
                continue
            try:
                sub_tag = db.get_setting("affiliate_sub_id") or os.getenv("AFFILIATE_SUB_ID", "temuanharian")
                link = shopee.generate_affiliate_link(
                    p["productLink"], ["fb", sub_tag, f"i{item_id}"]
                )
            except ShopeeError as exc:
                link = p.get("offerLink") or ""
                if not link:
                    print(f"[WARN] Lewati {item_id}: {exc}")
                    continue
                print(f"[WARN] {item_id}: pakai offerLink (tanpa sub-ID): {exc}")
            item = {
                "item_id": item_id,
                "product_name": p.get("productName") or "",
                "product_url": p["productLink"],
                "affiliate_link": link,
                "image_url": p["imageUrl"],
                "category": getattr(args, "category", "Elektronik & Gadget"),
                "price": _num(p.get("priceMin")),
                "discount_rate": _num(p.get("priceDiscountRate")),
                "rating": rating,
                "sales": sales,
                "commission_rate": _num(p.get("commissionRate")),
                "platform": "SHOPEE",
                "tiktok_link": "",
            }
            item["caption"] = caption_gen.generate(item)
            if db.insert_product(item):
                added += 1
            time.sleep(args.delay)
    print(f"[SUCCESS] {added} produk baru masuk antrean (status PENDING).")
    return 0


def cmd_manual_add(args) -> int:
    """Menambahkan produk kurasi manual (Shopee, TikTok Shop, atau Keduanya) via DI."""
    db = get_db()
    item_id = args.item_id or f"m_{int(time.time())}"
    item = {
        "item_id": item_id,
        "product_name": args.name,
        "product_url": args.url,
        "affiliate_link": args.url,
        "image_url": args.image,
        "category": args.category or "Rumah Tangga & Dekorasi",
        "price": _num(args.price),
        "discount_rate": _num(args.discount),
        "rating": _num(args.rating or 5.0),
        "sales": _num(args.sales or 100, int),
        "commission_rate": _num(args.commission or 0.0),
        "platform": args.platform.upper(),
        "tiktok_link": args.tiktok_url or "",
    }
    use_ai = getattr(args, "gemini", True)
    caption_gen = get_caption_generator(db=db, use_ai=use_ai)
    item["caption"] = args.caption or caption_gen.generate(item)
    if db.insert_product(item):
        if args.approve:
            db.approve(item_id)
            print(f"[SUCCESS] Produk [{item['platform']}] ({item['category']}) berhasil ditambahkan & APPROVED:\n   {item['product_name']}")
        else:
            print(f"[SUCCESS] Produk [{item['platform']}] ({item['category']}) masuk ke antrean PENDING:\n   {item['product_name']}")
        return 0
    else:
        print(f"[WARN] Produk dengan ID {item_id} sudah ada di database.")
        return 1


def cmd_review(args) -> int:
    db = get_db()
    pending = db.list_pending(limit=args.limit)
    if not pending:
        print("Tidak ada produk PENDING.")
        return 0
    for item in pending:
        print("\n" + "=" * 60)
        print(f"[{item.get('platform', 'SHOPEE')}] [{item.get('category', 'Umum')}] {item['product_name']}")
        print(
            f"harga {item['price']:.0f} | rating {item['rating']} | "
            f"terjual {item['sales']} | platform {item.get('platform')}"
        )
        print(f"shopee link: {item['affiliate_link']}")
        if item.get("tiktok_link"):
            print(f"tiktok link: {item['tiktok_link']}")
        print("-" * 60)
        print(item["caption"])
        while True:
            choice = input("\n[a]setujui  [r]tolak  [e]dit caption  [s]kip  [q]uit > ").strip().lower()
            if choice == "a":
                db.approve(item["item_id"])
                break
            if choice == "r":
                db.reject(item["item_id"])
                break
            if choice == "e":
                print("Ketik caption baru, akhiri dengan baris kosong:")
                lines = []
                while True:
                    line = input()
                    if not line:
                        break
                    lines.append(line)
                if lines:
                    db.update_caption(item["item_id"], "\n".join(lines))
                    item["caption"] = "\n".join(lines)
                    print("Caption diperbarui. Pilih [a] untuk menyetujui.")
                continue
            if choice == "s":
                break
            if choice == "q":
                return 0
    return 0


def cmd_publish(args) -> int:
    """Mempublikasikan produk ke seluruh channel aktif via PublisherDispatcher (Dependency Inversion)."""
    db = get_db()
    settings = db.get_all_settings()
    max_per_day = int(settings.get("post_frequency_per_day") or settings.get("max_posts_per_day") or os.getenv("MAX_POSTS_PER_DAY", str(args.max_per_day)))
    if db.count_posted_today() >= max_per_day:
        print(f"Batas {max_per_day} posting/hari sudah tercapai.")
        return 0
    item = db.next_approved()
    if not item:
        print("Tidak ada produk APPROVED. Jalankan review atau aktifkan auto-approve.")
        return 0
    if args.dry_run:
        print("[dry-run] Akan memposting ke channel aktif:\n" + item["caption"])
        print("[dry-run] Komentar:\n" + build_comment(item))
        return 0

    dispatcher = get_publisher_dispatcher(db=db)
    result = dispatcher.dispatch(
        image_url=item["image_url"],
        caption=item["caption"],
        comment_text=build_comment(item)
    )

    if result.is_success:
        fb_id = result.post_ids.get("Facebook Page")
        th_id = result.post_ids.get("Threads")
        ig_id = result.post_ids.get("Instagram")
        db.mark_posted_multi(item["item_id"], fb_id, th_id, ig_id)
        db.mark_comment_done(item["item_id"])
        print(f"[SUCCESS] {result.summary()}")
        return 0
    else:
        print(f"[FAILED] {result.summary()}")
        db.set_error(item["item_id"], result.summary())
        return 1


def cmd_retry_comments(args) -> int:
    db = get_db()
    items = db.list_comment_pending()
    if not items:
        print("Tidak ada komentar yang tertunda.")
        return 0

    dispatcher = get_publisher_dispatcher(db=db)
    success = 0
    for it in items:
        comment_text = build_comment(it)
        if it.get("fb_post_id"):
            for pub in dispatcher.publishers:
                if pub.platform_name == "Facebook Page":
                    try:
                        pub.add_comment(it["fb_post_id"], comment_text)
                        db.mark_comment_done(it["item_id"])
                        success += 1
                    except Exception as e:
                        db.set_error(it["item_id"], f"retry komentar gagal: {e}")

    print(f"[INFO] {success}/{len(items)} komentar berhasil.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bot Temuan Harian Multi-Platform & Multi-Channel (SOLID & DI)")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scout", help="ambil produk dari Shopee ke antrean")
    s.add_argument("--viral", action="store_true", help="Scout produk viral langsung dari web tanpa butuh Open API")
    s.add_argument("--approve", action="store_true", help="Langsung setujui produk yang ditemukan")
    s.add_argument("--keyword", default="")
    s.add_argument("--category", default="Elektronik & Gadget")
    s.add_argument("--min-sales", type=int, default=200)
    s.add_argument("--min-rating", type=float, default=4.7)
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--pages", type=int, default=1)
    s.add_argument("--sort", type=int, default=2)
    s.add_argument("--delay", type=float, default=1.0)
    s.set_defaults(func=cmd_scout)

    m = sub.add_parser("manual-add", help="tambah produk manual (Shopee, TikTok, Keduanya)")
    m.add_argument("--name", required=True, help="Nama produk")
    m.add_argument("--url", required=True, help="Link affiliate utama (Shopee atau TikTok)")
    m.add_argument("--image", required=True, help="URL gambar produk")
    m.add_argument("--category", default="Rumah Tangga & Dekorasi", help="Kategori produk standar Shopee")
    m.add_argument("--platform", default="SHOPEE", choices=["SHOPEE", "TIKTOK", "BOTH"], help="Platform sumber")
    m.add_argument("--tiktok-url", default="", help="Link TikTok Shop (jika platform BOTH)")
    m.add_argument("--price", type=float, default=0, help="Harga barang (Rp)")
    m.add_argument("--discount", type=float, default=0, help="Diskon dalam persen (%%)")
    m.add_argument("--rating", type=float, default=5.0, help="Rating produk")
    m.add_argument("--sales", type=int, default=100, help="Jumlah terjual")
    m.add_argument("--commission", type=float, default=0.0, help="Komisi")
    m.add_argument("--item-id", default="", help="ID produk opsional")
    m.add_argument("--caption", default="", help="Caption kustom opsional")
    m.add_argument("--gemini", action="store_true", default=True, help="Gunakan Gemini AI Caption edukatif")
    m.add_argument("--approve", action="store_true", help="Langsung setujui (status APPROVED)")
    m.set_defaults(func=cmd_manual_add)

    r = sub.add_parser("review", help="setujui/tolak/edit produk PENDING")
    r.add_argument("--limit", type=int, default=20)
    r.set_defaults(func=cmd_review)

    p = sub.add_parser("publish", help="posting produk APPROVED ke Facebook/Threads/IG")
    p.add_argument("--max-per-day", type=int, default=3)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_publish)

    c = sub.add_parser("retry-comments", help="ulangi komentar yang gagal")
    c.set_defaults(func=cmd_retry_comments)

    return parser


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
