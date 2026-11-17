"""Web Catalog & Central Management Dashboard for Temuan Harian.
Subdomain: temuan-harian.pdfumi.com
Menerapkan Prinsip SOLID & Dependency Injection (DI) dengan FastAPI.
"""
import os
import secrets
import sys
import json
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda *args, **kwargs: None
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, Form, HTTPException, status, BackgroundTasks, Body, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from database import ProductQueueDB
from dependencies import (
    get_db,
    get_caption_generator,
    get_product_scraper,
    get_publisher_dispatcher,
    get_ads_manager,
)
from captions import build_comment
from shopee_scraper import SHOPEE_CATEGORIES

load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Temuan Harian Control Center (SOLID & DI Architecture)")

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_admin_secret(db: ProductQueueDB = Depends(get_db)) -> str:
    secret = db.get_setting("admin_secret") or os.getenv("ADMIN_SECRET", "")
    if not secret:
        secret = secrets.token_hex(6)
        db.set_setting("admin_secret", secret)
        print(f"[AUTH] Password admin otomatis dibuat: {secret}")
    return secret


def verify_admin(request: Request, db: ProductQueueDB = Depends(get_db)) -> bool:
    token = request.cookies.get("admin_token") or request.query_params.get("key")
    return token == get_admin_secret(db)


# ===================== META & THREADS OAUTH CALLBACKS =====================

@app.get("/auth/threads/callback")
async def threads_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
    """Menangani pengalihan OAuth dari Threads API Meta."""
    if error:
        return HTMLResponse(f"<h3>Otorisasi Threads Dibatalkan: {error}</h3><p><a href='/admin?tab=settings'>Kembali ke Dashboard</a></p>", status_code=400)
    return HTMLResponse(
        f"""
        <div style="font-family: sans-serif; padding: 2rem; max-width: 600px; margin: auto;">
            <h2>Otorisasi Threads Berhasil</h2>
            <p>Kode otorisasi berhasil diterima:</p>
            <pre style="background: #f1f5f9; padding: 1rem; border-radius: 8px;">{code}</pre>
            <p>Salin kode ini ke Dashboard Admin atau gunakan Generator Token Pengguna di Meta App.</p>
            <a href="/admin?tab=settings" style="display: inline-block; padding: 0.5rem 1rem; background: #4f46e5; color: white; text-decoration: none; border-radius: 6px;">Ke Pengaturan Admin</a>
        </div>
        """
    )


@app.api_route("/auth/threads/deauth", methods=["GET", "POST"])
async def threads_deauth_callback(request: Request, db: ProductQueueDB = Depends(get_db)):
    """Endpoint Deauthorize yang dipanggil Meta ketika pengguna mencabut akses aplikasi."""
    db.log_activity("THREADS_DEAUTH", "Aplikasi Threads diputus atau dideotorisasi oleh pengguna.", status="INFO")
    return JSONResponse({"status": "success", "message": "Deauthorization acknowledged"})


@app.api_route("/auth/threads/delete", methods=["GET", "POST"])
async def threads_delete_callback(request: Request, db: ProductQueueDB = Depends(get_db)):
    """Endpoint Data Deletion Request Callback sesuai ketentuan privasi Meta."""
    confirmation_code = hashlib.sha256(secrets.token_bytes(16)).hexdigest()[:12]
    db.log_activity("DATA_DELETE", f"Permintaan penghapusan data Meta diterima. Kode: {confirmation_code}", status="INFO")
    return JSONResponse({
        "url": f"https://temuan-harian.pdfumi.com/auth/threads/delete-status?code={confirmation_code}",
        "confirmation_code": confirmation_code
    })


@app.get("/auth/threads/delete-status")
async def threads_delete_status(code: Optional[str] = None):
    return HTMLResponse(f"<h3>Status Permintaan Penghapusan Data: SELESAI</h3><p>Kode Konfirmasi: {code}</p>")


# ===================== META FACEBOOK & INSTAGRAM WEBHOOKS =====================

@app.get("/webhooks/facebook")
async def meta_webhook_verification(request: Request, db: ProductQueueDB = Depends(get_db)):
    """Verifikasi webhook resmi dari Meta (Facebook Page, Ad Account, Instagram)."""
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")

    expected_token = db.get_setting("meta_webhook_verify_token") or os.getenv("META_WEBHOOK_VERIFY_TOKEN", "temuan_harian_secret_token")

    if mode == "subscribe" and token == expected_token:
        print("[WEBHOOK] Meta Webhook verified successfully!")
        return Response(content=challenge, media_type="text/plain")
    return HTMLResponse("Forbidden: Verification Token Mismatch", status_code=403)


@app.post("/webhooks/facebook")
async def meta_webhook_events(request: Request, db: ProductQueueDB = Depends(get_db)):
    """Menerima event real-time dari Meta jika berlangganan field (misal: feed, mentions, comments)."""
    try:
        data = await request.json()
        obj_type = data.get("object", "unknown")
        db.log_activity("WEBHOOK_EVENT", f"Menerima event webhook [{obj_type}] dari Meta.", status="INFO")
    except Exception:
        pass
    return JSONResponse({"status": "EVENT_RECEIVED"})


# ===================== SCRAPER PREVIEW API =====================

@app.post("/api/scrape-preview")
async def api_scrape_preview(request: Request, payload: Dict[str, str] = Body(...)):
    """Mengekstrak data judul, cover foto resmi, dan estimasi harga dari link Shopee via IProductScraper."""
    url = payload.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL diperlukan")
    scraper = get_product_scraper()
    data = scraper.scrape_preview(url)
    return JSONResponse(data)


# ===================== PUBLIK (Katalog Bersih) =====================

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def public_catalog(
    request: Request,
    q: Optional[str] = None,
    platform: Optional[str] = None,
    category: Optional[str] = None,
    db: ProductQueueDB = Depends(get_db)
):
    fb_page_id = db.get_setting("fb_page_id") or os.getenv("FB_PAGE_ID", "")
    fb_page_url = f"https://www.facebook.com/profile.php?id={fb_page_id}" if fb_page_id else None

    with db._connect() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cur = conn.cursor()
        query = "SELECT * FROM products WHERE (status = 'POSTED' OR status = 'APPROVED')"
        params = []

        if q:
            query += " AND product_name LIKE ?"
            params.append(f"%{q.strip()}%")

        if platform and platform != "ALL":
            query += " AND platform = ?"
            params.append(platform.upper())

        if category and category != "ALL":
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY created_at DESC LIMIT 60"
        cur.execute(query, tuple(params))
        products = cur.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "products": products,
            "search_query": q or "",
            "active_platform": platform or "ALL",
            "active_category": category or "ALL",
            "categories": SHOPEE_CATEGORIES,
            "fb_page_url": fb_page_url
        }
    )


# ===================== ADMIN DASHBOARD & MONITORING =====================

@app.api_route("/admin", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    key: Optional[str] = None,
    msg: Optional[str] = None,
    tab: str = "dashboard",
    status_filter: str = "ALL",
    category_filter: str = "ALL",
    db: ProductQueueDB = Depends(get_db)
):
    token = request.cookies.get("admin_token") or key
    admin_secret = get_admin_secret(db)
    if token != admin_secret:
        return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": msg})

    metrics = db.get_metrics()
    logs = db.list_logs(limit=25)
    settings = db.get_all_settings()

    chart_labels = [d["label"] for d in metrics["weekly_activity"]]
    chart_posted = [d["count"] for d in metrics["weekly_activity"]]
    status_counts = [metrics["pending"], metrics["approved"], metrics["posted"], metrics["rejected"]]

    metrics["chart_labels"] = chart_labels
    metrics["chart_posted"] = chart_posted
    metrics["status_counts"] = status_counts
    metrics["shopee_count"] = metrics["platforms"].get("SHOPEE", 0)
    metrics["tiktok_count"] = metrics["platforms"].get("TIKTOK", 0) + metrics["platforms"].get("BOTH", 0)

    with db._connect() as conn:
        conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        cur = conn.cursor()
        query = "SELECT * FROM products WHERE 1=1"
        params = []

        if status_filter != "ALL":
            query += " AND status = ?"
            params.append(status_filter)

        if category_filter != "ALL":
            query += " AND category = ?"
            params.append(category_filter)

        query += " ORDER BY created_at DESC LIMIT 100"
        cur.execute(query, tuple(params))
        products = cur.fetchall()

    response = templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request,
            "metrics": metrics,
            "products": products,
            "logs": logs,
            "settings": settings,
            "categories": SHOPEE_CATEGORIES,
            "active_tab": tab,
            "status_filter": status_filter,
            "category_filter": category_filter,
            "msg": msg,
        }
    )
    if key == admin_secret:
        response.set_cookie("admin_token", admin_secret, max_age=86400 * 30, httponly=True)
    return response


@app.post("/admin/login")
async def admin_login(password: str = Form(...), db: ProductQueueDB = Depends(get_db)):
    admin_secret = get_admin_secret(db)
    if password == admin_secret:
        resp = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        resp.set_cookie("admin_token", admin_secret, max_age=86400 * 30, httponly=True)
        return resp
    return RedirectResponse(url="/admin?msg=Kunci+akses+tidak+valid", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/logout")
async def admin_logout():
    resp = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("admin_token")
    return resp


# ===================== KONTROL & AKSI PRODUK =====================

def _publish_product_to_channels(db: ProductQueueDB, item: Dict[str, Any]) -> str:
    """Mempublikasikan produk ke seluruh channel aktif via PublisherDispatcher (Dependency Inversion)."""
    dispatcher = get_publisher_dispatcher(db=db)
    comment_text = build_comment(item)
    result = dispatcher.dispatch(
        image_url=item["image_url"],
        caption=item["caption"],
        comment_text=comment_text
    )

    if result.is_success:
        fb_id = result.post_ids.get("Facebook Page")
        th_id = result.post_ids.get("Threads")
        ig_id = result.post_ids.get("Instagram")
        db.mark_posted_multi(item["item_id"], fb_id, th_id, ig_id)
        db.mark_comment_done(item["item_id"])
        return result.summary()
    else:
        err_msg = result.summary()
        db.set_error(item["item_id"], err_msg)
        return err_msg


@app.post("/admin/action")
async def admin_product_action(
    request: Request,
    item_id: str = Form(...),
    action: str = Form(...),
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if action == "approve":
        db.approve(item_id)
        msg = f"Produk {item_id} berhasil disetujui (APPROVED)"
    elif action == "reject":
        db.reject(item_id)
        msg = f"Produk {item_id} ditandai ditolak"
    elif action == "delete":
        db.delete(item_id)
        msg = f"Produk {item_id} berhasil dihapus dari database"
    elif action == "publish_now":
        item = db.get(item_id)
        if not item:
            return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg=Produk+tidak+ditemukan", status_code=status.HTTP_303_SEE_OTHER)
        msg = _publish_product_to_channels(db, item)
    else:
        msg = "Aksi tidak dikenali"

    return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/quick-add")
async def admin_quick_add(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    image_url: str = Form(...),
    category: str = Form("Rumah Tangga & Dekorasi"),
    platform: str = Form("SHOPEE"),
    tiktok_link: str = Form(""),
    price: float = Form(0),
    discount: float = Form(0),
    rating: float = Form(5.0),
    sales: int = Form(100),
    use_gemini: bool = Form(True),
    custom_caption: str = Form(""),
    auto_approve: bool = Form(False),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    import time
    item_id = f"m_{int(time.time())}"
    item = {
        "item_id": item_id,
        "product_name": name.strip(),
        "product_url": url.strip(),
        "affiliate_link": url.strip(),
        "image_url": image_url.strip(),
        "category": category.strip(),
        "platform": platform.upper(),
        "tiktok_link": tiktok_link.strip(),
        "price": price,
        "discount_rate": discount,
        "rating": rating,
        "sales": sales,
        "commission_rate": 0.0,
    }

    if custom_caption.strip():
        item["caption"] = custom_caption.strip()
    else:
        caption_gen = get_caption_generator(db=db, use_ai=use_gemini)
        item["caption"] = caption_gen.generate(item)

    if db.insert_product(item):
        if auto_approve:
            db.approve(item_id)
            msg = f"Produk [{platform.upper()}] kategori '{category}' berhasil ditambahkan & disetujui!"
        else:
            msg = f"Produk [{platform.upper()}] kategori '{category}' berhasil masuk antrean PENDING."
    else:
        msg = "Produk sudah ada di dalam database."

    return RedirectResponse(url=f"/admin?tab=products&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


# ===================== KONTROL OTOMASI LATAR BELAKANG =====================

def _bg_run_scout(auto_approve: bool = False):
    from scout_viral import run_viral_discovery
    try:
        run_viral_discovery(auto_approve=auto_approve)
    except Exception as e:
        db = get_db()
        db.log_activity("SCOUT_ERROR", f"Error pada auto-scout: {e}", status="FAILED")


@app.post("/admin/trigger/scout")
async def trigger_scout(
    request: Request,
    background_tasks: BackgroundTasks,
    auto_approve: bool = Form(False),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    background_tasks.add_task(_bg_run_scout, auto_approve)
    db.log_activity("TRIGGER_SCOUT", "Proses Auto-Scout produk viral dijalankan di latar belakang.")
    return RedirectResponse(url="/admin?tab=logs&msg=Auto-Scout+sedang+berjalan+di+latar+belakang.+Cek+tab+Log+Aktivitas+dalam+beberapa+saat.", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/trigger/publish-next")
async def trigger_publish_next(request: Request, db: ProductQueueDB = Depends(get_db)):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    item = db.next_approved()
    if not item:
        return RedirectResponse(url="/admin?tab=dashboard&msg=Tidak+ada+produk+berstatus+APPROVED+yang+siap+diposting.", status_code=status.HTTP_303_SEE_OTHER)

    msg = _publish_product_to_channels(db, item)
    return RedirectResponse(url=f"/admin?tab=dashboard&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/trigger/retry-comments")
async def trigger_retry_comments(request: Request, db: ProductQueueDB = Depends(get_db)):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    items = db.list_comment_pending()
    if not items:
        return RedirectResponse(url="/admin?tab=logs&msg=Tidak+ada+komentar+yang+tertunda.", status_code=status.HTTP_303_SEE_OTHER)

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

    msg = f"Selesai: {success}/{len(items)} komentar berhasil diperbarui."
    return RedirectResponse(url=f"/admin?tab=logs&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


# ===================== PENGATURAN SISTEM =====================

@app.post("/admin/settings/save")
async def save_settings(
    request: Request,
    shopee_affiliate_id: str = Form(""),
    tiktok_affiliate_id: str = Form(""),
    channel_fb_enabled: str = Form("0"),
    channel_threads_enabled: str = Form("0"),
    channel_ig_enabled: str = Form("0"),
    post_frequency_per_day: int = Form(3),
    post_schedule_times: str = Form("08:00, 12:30, 19:30"),
    gemini_api_key: str = Form(""),
    gemini_model: str = Form("gemini-3.8-flash"),
    fb_page_id: str = Form(""),
    fb_page_access_token: str = Form(""),
    threads_app_id: str = Form(""),
    threads_app_secret: str = Form(""),
    threads_user_id: str = Form(""),
    threads_access_token: str = Form(""),
    ig_user_id: str = Form(""),
    ig_access_token: str = Form(""),
    meta_ad_account_id: str = Form(""),
    meta_webhook_verify_token: str = Form(""),
    min_sales: int = Form(300),
    min_rating: float = Form(4.8),
    auto_scout_keywords: str = Form(""),
    admin_secret: str = Form(""),
    auto_approve_scouted: str = Form("0"),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    db.set_setting("shopee_affiliate_id", shopee_affiliate_id.strip())
    db.set_setting("tiktok_affiliate_id", tiktok_affiliate_id.strip())
    db.set_setting("channel_fb_enabled", "1" if channel_fb_enabled == "1" else "0")
    db.set_setting("channel_threads_enabled", "1" if channel_threads_enabled == "1" else "0")
    db.set_setting("channel_ig_enabled", "1" if channel_ig_enabled == "1" else "0")
    db.set_setting("post_frequency_per_day", str(post_frequency_per_day))
    db.set_setting("max_posts_per_day", str(post_frequency_per_day))
    db.set_setting("post_schedule_times", post_schedule_times.strip())
    db.set_setting("gemini_model", gemini_model.strip() or "gemini-3.8-flash")
    db.set_setting("min_sales", str(min_sales))
    db.set_setting("min_rating", str(min_rating))
    db.set_setting("auto_approve_scouted", "1" if auto_approve_scouted == "1" else "0")

    if gemini_api_key.strip():
        db.set_setting("gemini_api_key", gemini_api_key.strip())
    if fb_page_id.strip():
        db.set_setting("fb_page_id", fb_page_id.strip())
    if fb_page_access_token.strip():
        db.set_setting("fb_page_access_token", fb_page_access_token.strip())

    if threads_app_id.strip():
        db.set_setting("threads_app_id", threads_app_id.strip())
    if threads_app_secret.strip():
        db.set_setting("threads_app_secret", threads_app_secret.strip())
    if threads_user_id.strip():
        db.set_setting("threads_user_id", threads_user_id.strip())
    if threads_access_token.strip():
        db.set_setting("threads_access_token", threads_access_token.strip())

    if ig_user_id.strip():
        db.set_setting("ig_user_id", ig_user_id.strip())
    if ig_access_token.strip():
        db.set_setting("ig_access_token", ig_access_token.strip())

    if meta_ad_account_id.strip():
        db.set_setting("meta_ad_account_id", meta_ad_account_id.strip())

    if meta_webhook_verify_token.strip():
        db.set_setting("meta_webhook_verify_token", meta_webhook_verify_token.strip())

    if auto_scout_keywords.strip():
        db.set_setting("auto_scout_keywords", auto_scout_keywords.strip())
    if admin_secret.strip():
        db.set_setting("admin_secret", admin_secret.strip())

    db.log_activity("SETTINGS", "Pengaturan sistem, channel multi-posting & AI Gemini diperbarui.")
    return RedirectResponse(url="/admin?tab=settings&msg=Pengaturan+berhasil+disimpan!", status_code=status.HTTP_303_SEE_OTHER)
