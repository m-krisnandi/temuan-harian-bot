"""FastAPI Web Application untuk Temuan Harian.
Menerapkan Prinsip SOLID:
- Single Responsibility: Memisahkan routing web, webhook Meta, dan background scheduling.
- Dependency Inversion: Menggunakan dependency injection (Depends) dari core/dependencies.py.
"""
import os
import secrets
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from collections import OrderedDict
from contextlib import asynccontextmanager
import asyncio

from pydantic import BaseModel
from fastapi import (
    FastAPI,
    Request,
    Depends,
    Form,
    File,
    UploadFile,
    HTTPException,
    status,
    Response,
    BackgroundTasks,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from repositories.database import ProductQueueDB, WIB
from core.dependencies import (
    get_db,
    get_publisher_dispatcher,
    get_caption_generator,
    get_product_scraper,
    get_ads_manager,
    get_admin_secret,
    get_admin_session_token,
    verify_admin,
)
from services.shopee_scraper import SHOPEE_CATEGORIES
from services.captions import build_comment
from services.smart_scheduler import SmartScheduler
from services.quality_inspector import QualityInspector
from services.education_pipeline import EducationContentService
from services.tiktok_script import get_recommended_settings


# ===================== BACKGROUND SCHEDULER WORKER =====================

_META_CIRCUIT_BREAKER_UNTIL: Optional[datetime] = None

AUTH_SPAM_SIGNALS = [
    "session has expired",
    "error validating access token",
    "oauthexception",
    "permissions error",
    "checkpoint",
    "temporarily blocked",
    "rate limit",
    "calls have exceeded",
    "user is restricted",
    "integrity",
    "spam"
]

async def automated_scheduler_worker():
    """Background worker yang memeriksa antrean setiap 60 detik.
    1. Mempublikasikan produk/konten yang jadwalnya sudah tiba dengan proteksi Anti-Loop & Circuit Breaker.
    2. Secara otomatis mengisi slot edukasi murni (07:30 & 17:00 WIB) untuk 3 hari ke depan via 5-Stage Content Engine.
    """
    global _META_CIRCUIT_BREAKER_UNTIL
    print("[SCHEDULER] Background worker aktif memantau antrean & auto-replenish edukasi (Asia/Jakarta)...")
    cycle_count = 0
    while True:
        try:
            db = get_db()
            now_dt = datetime.now(WIB)

            # Cek Proteksi Circuit Breaker
            if _META_CIRCUIT_BREAKER_UNTIL and now_dt < _META_CIRCUIT_BREAKER_UNTIL:
                wait_min = max(1, int((_META_CIRCUIT_BREAKER_UNTIL - now_dt).total_seconds() / 60))
                if cycle_count % 10 == 0:
                    print(f"[CIRCUIT BREAKER AKTIF] Penundaan request aktif hingga {_META_CIRCUIT_BREAKER_UNTIL.strftime('%H:%M WIB')} (~{wait_min} menit) untuk melindungi akun Meta.")
            else:
                if _META_CIRCUIT_BREAKER_UNTIL:
                    print("[CIRCUIT BREAKER SELESAI] Masa pendinginan selesai. Melanjutkan jadwal normal...")
                    _META_CIRCUIT_BREAKER_UNTIL = None

                # 1. Cek produk jatuh tempo
                due_product = db.get_due_scheduled()
                if due_product:
                    print(f"[SCHEDULER] Menemukan postingan jatuh tempo: {due_product['product_name'][:40]} (Jadwal: {due_product.get('scheduled_at')})")
                    res_msg = _publish_product_to_channels(db, due_product)
                    print(f"[SCHEDULER RESULT] {res_msg}")

                    # Jika gagal publikasi, jalankan mekanisme Anti-Loop & Circuit Breaker
                    if "Gagal publikasi" in res_msg:
                        is_auth_spam = any(sig in res_msg.lower() for sig in AUTH_SPAM_SIGNALS)
                        fail_res = db.handle_publish_failure(
                            item_id=due_product["item_id"],
                            error_message=res_msg,
                            is_auth_or_spam_error=is_auth_spam
                        )
                        if is_auth_spam:
                            _META_CIRCUIT_BREAKER_UNTIL = now_dt + timedelta(hours=1)
                            db.log_activity(
                                "CIRCUIT_BREAKER",
                                f"Token/Otorisasi Meta bermasalah: {res_msg[:120]}. Scheduler diistirahatkan 1 jam untuk mencegah penalti.",
                                status="FAILED"
                            )
                            print(f"[CIRCUIT BREAKER DIAKTIFKAN] Diistirahatkan hingga {_META_CIRCUIT_BREAKER_UNTIL.strftime('%H:%M WIB')}.")
                        elif fail_res.get("action") == "EXHAUSTED":
                            db.log_activity(
                                "RETRY_EXHAUSTED",
                                f"Produk {due_product['item_id']} gagal 3x dan diisolasi dari antrean: {res_msg[:100]}",
                                status="FAILED"
                            )
                            print(f"[ANTI-LOOP] Produk {due_product['item_id']} gagal 3x berturut-turut, diisolasi dari antrean.")
                        else:
                            print(f"[ANTI-LOOP] Jadwal produk diundur ke {fail_res.get('next_time')} (Percobaan ke-{fail_res.get('retries')}).")

            # 2. Auto-Replenish Konten Edukasi Murni setiap 30 siklus (30 menit) atau saat siklus pertama
            if cycle_count % 30 == 0:
                try:
                    edu_service = EducationContentService(db=db)
                    replenished = edu_service.auto_replenish(days_ahead=3)
                    if replenished:
                        print(f"[AUTO-EDU] Berhasil auto-replenish {len(replenished)} konten edukasi murni 3 hari ke depan.")
                except Exception as edu_err:
                    print(f"[AUTO-EDU ERROR] {edu_err}")

            cycle_count += 1
        except Exception as e:
            print(f"[SCHEDULER ERROR] {e}")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler task in background
    scheduler_task = asyncio.create_task(automated_scheduler_worker())
    yield
    scheduler_task.cancel()


app = FastAPI(title="Temuan Harian Hub", version="2.6.0", lifespan=lifespan)

# Setup Templates & Static Assets
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["build_comment"] = build_comment
templates.env.globals["get_tiktok_recommendation"] = get_recommended_settings

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ===================== REALTIME QUEUE API =====================

@app.get("/api/queue-status")
async def api_queue_status(db: ProductQueueDB = Depends(get_db)):
    """API Realtime untuk status antrean, next drop countdown, dan metrik publikasi."""
    now_dt = datetime.now(WIB)
    metrics = db.get_metrics()
    scheduled = db.list_scheduled(limit=50)

    queue_list = []
    for idx, p in enumerate(scheduled):
        sched = p.get("scheduled_at", "")
        rem_sec = 0
        if sched:
            try:
                sched_dt = datetime.strptime(sched, "%Y-%m-%d %H:%M").replace(tzinfo=WIB)
                rem_sec = max(0, int((sched_dt - now_dt).total_seconds()))
            except Exception:
                rem_sec = 0

        queue_list.append({
            "queue_order": idx + 1,
            "item_id": p["item_id"],
            "product_name": p["product_name"],
            "image_url": p.get("image_url", ""),
            "scheduled_at": sched,
            "remaining_seconds": rem_sec,
            "status": p.get("status", "APPROVED"),
            "market_score": p.get("market_score", 0),
            "price": p.get("price", 0),
            "category": p.get("category", "")
        })

    next_item = queue_list[0] if queue_list else None

    return JSONResponse({
        "server_time_wib": now_dt.strftime("%Y-%m-%d %H:%M:%S WIB"),
        "metrics": metrics,
        "next_item": next_item,
        "total_scheduled": len(queue_list),
        "queue": queue_list
    })



class ReorderRequest(BaseModel):
    item_id_source: Optional[str] = None
    item_id_target: Optional[str] = None
    ordered_ids: Optional[List[str]] = None


@app.post("/api/queue/reorder")
async def api_queue_reorder(
    req: ReorderRequest,
    db: ProductQueueDB = Depends(get_db)
):
    """
    Menukar urutan jadwal (Drag and Drop):
    - Jika ordered_ids diberikan: jadwalkan ulang seluruh antrean sesuai urutan baru.
    - Jika item_id_source & item_id_target diberikan: swap jadwal kedua produk.
    """
    scheduled = db.list_scheduled(limit=100)
    if not scheduled:
        return JSONResponse({"status": "error", "message": "Tidak ada antrean jadwal"}, status_code=400)

    # Mode 1: Reorder seluruh antrean berdasarkan ordered_ids
    if req.ordered_ids:
        # Ambil seluruh jadwal yang sudah ada (terurut waktu asc)
        existing_times = [p["scheduled_at"] for p in scheduled if p.get("scheduled_at")]
        item_map = {p["item_id"]: p for p in scheduled}

        for idx, item_id in enumerate(req.ordered_ids):
            if idx < len(existing_times) and item_id in item_map:
                new_time = existing_times[idx]
                db.update_schedule(item_id, new_time)

        return JSONResponse({
            "status": "success",
            "message": f"Berhasil memperbarui {len(req.ordered_ids)} urutan postingan."
        })

    # Mode 2: Swap dua produk
    if req.item_id_source and req.item_id_target:
        src = db.get(req.item_id_source)
        tgt = db.get(req.item_id_target)
        if not src or not tgt:
            return JSONResponse({"status": "error", "message": "Item tidak ditemukan"}, status_code=404)

        src_time = src.get("scheduled_at")
        tgt_time = tgt.get("scheduled_at")

        if not src_time or not tgt_time:
            return JSONResponse({"status": "error", "message": "Kedua produk harus memiliki jadwal aktif"}, status_code=400)

        db.update_schedule(req.item_id_source, tgt_time)
        db.update_schedule(req.item_id_target, src_time)

        return JSONResponse({
            "status": "success",
            "message": f"Jadwal '{src['product_name'][:25]}' dan '{tgt['product_name'][:25]}' berhasil ditukar!"
        })

    return JSONResponse({"status": "error", "message": "Parameter tidak valid"}, status_code=400)


# ===================== KATALOG PUBLIK =====================

@app.get("/", response_class=HTMLResponse)
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
        query = "SELECT * FROM products WHERE status = 'POSTED' AND affiliate_link != '' AND (post_type != 'EDUCATION' OR post_type IS NULL)"
        params = []

        if q:
            query += " AND (product_name LIKE ? OR category LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])

        if platform and platform != "ALL":
            query += " AND platform = ?"
            params.append(platform)

        if category and category != "ALL":
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY posted_at DESC LIMIT 60"
        cur.execute(query, tuple(params))
        items = cur.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "products": items, "items": items,
            "search_query": q or "",
            "active_platform": platform or "ALL",
            "active_category": category or "ALL",
            "categories": SHOPEE_CATEGORIES,
            "fb_page_url": fb_page_url
        }
    )


# ===================== META & THREADS OAUTH CALLBACKS =====================

@app.get("/auth/threads/callback")
async def threads_oauth_callback(code: Optional[str] = None, error: Optional[str] = None):
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
    db.log_activity("THREADS_DEAUTH", "Aplikasi Threads diputus atau dideotorisasi oleh pengguna.", status="INFO")
    return JSONResponse({"status": "success", "message": "Deauthorization acknowledged"})


@app.api_route("/auth/threads/delete", methods=["GET", "POST"])
async def threads_delete_callback(request: Request, db: ProductQueueDB = Depends(get_db)):
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
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")

    expected_token = db.get_setting("meta_webhook_verify_token") or os.getenv("META_WEBHOOK_VERIFY_TOKEN", "temuan_harian_secret_token")

    if mode == "subscribe" and token == expected_token:
        print("[WEBHOOK] Meta Webhook verified successfully!")
        return Response(content=challenge, media_type="text/plain")
    return HTMLResponse("Forbidden: Verification Token Mismatch", status_code=403)


@app.post("/webhooks/facebook")
async def meta_webhook_event_handler(request: Request, db: ProductQueueDB = Depends(get_db)):
    try:
        body = await request.json()
        obj = body.get("object")
        entries = body.get("entry", [])

        for entry in entries:
            entry_id = entry.get("id")
            for change in entry.get("changes", []):
                field = change.get("field")
                val = change.get("value")
                db.log_activity("WEBHOOK_EVENT", f"Meta Webhook [{obj} ID:{entry_id}] field: {field}", status="INFO")

        return JSONResponse({"status": "EVENT_RECEIVED"})
    except Exception as e:
        db.log_activity("WEBHOOK_ERROR", f"Error memproses webhook: {str(e)}", status="FAILED")
        return JSONResponse({"status": "ERROR"}, status_code=400)


# ===================== ADMIN DASHBOARD & MONITORING =====================

@app.api_route("/admin", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    key: Optional[str] = None,
    msg: Optional[str] = None,
    tab: str = "products",
    status_filter: str = "ALL",
    category_filter: str = "ALL",
    view_mode: str = "timeline",
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": msg})
    admin_secret = get_admin_secret(db)

    metrics = db.get_metrics()
    logs = db.list_logs(limit=25)
    settings = db.get_all_settings()
    blacklist_items = db.list_blacklist(limit=50)

    chart_labels = [d["label"] for d in metrics["weekly_activity"]]
    chart_posted = [d["count"] for d in metrics["weekly_activity"]]
    status_counts = [metrics["pending"], metrics["approved"], metrics["posted"], metrics["rejected"]]

    metrics["chart_labels"] = chart_labels
    metrics["chart_posted"] = chart_posted
    metrics["status_counts"] = status_counts
    metrics["shopee_count"] = metrics["platforms"].get("SHOPEE", 0)
    metrics["tiktok_count"] = metrics["platforms"].get("TIKTOK", 0) + metrics["platforms"].get("BOTH", 0)

    # Ambil produk dengan filter terintegrasi
    products = db.list_all(status=status_filter, category=category_filter, limit=100)
    scheduled_items = db.list_scheduled(limit=50)

    # Menentukan Urutan Antrean (#1, #2, #3...) dan Next Up Post
    now_dt = datetime.now(WIB)
    today_str = now_dt.strftime("%Y-%m-%d")
    tomorrow_str = (now_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    day_names = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"
    }
    month_names = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
        7: "Jul", 8: "Agt", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"
    }

    # Urutan antrean dan grup timeline
    timeline_groups = OrderedDict()
    for idx, p in enumerate(scheduled_items):
        p["queue_order"] = idx + 1
        sched = p.get("scheduled_at", "")
        if sched:
            parts = sched.split(" ")
            date_part = parts[0]
            time_part = parts[1] if len(parts) > 1 else ""
            p["time_slot"] = time_part
            p["date_part"] = date_part

            # Hitung selisih sisa detik
            try:
                sched_dt = datetime.strptime(sched, "%Y-%m-%d %H:%M").replace(tzinfo=WIB)
                p["rem_seconds"] = max(0, int((sched_dt - now_dt).total_seconds()))
            except Exception:
                p["rem_seconds"] = 0

            if date_part == today_str:
                label = f"Hari Ini ({date_part})"
            elif date_part == tomorrow_str:
                label = f"Besok ({date_part})"
            else:
                try:
                    dt = datetime.strptime(date_part, "%Y-%m-%d")
                    day_id = day_names.get(dt.strftime("%A"), dt.strftime("%A"))
                    mon_id = month_names.get(dt.month, "")
                    label = f"{day_id}, {dt.day} {mon_id} {dt.year}"
                except Exception:
                    label = date_part

            if label not in timeline_groups:
                timeline_groups[label] = []
            timeline_groups[label].append(p)

    next_post = scheduled_items[0] if scheduled_items else None

    # Tautkan order ke daftar produk utama
    sched_order_map = {p["item_id"]: p.get("queue_order") for p in scheduled_items}
    for p in products:
        p["queue_order"] = sched_order_map.get(p["item_id"])

    response = templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "request": request,
            "metrics": metrics,
            "products": products,
            "scheduled_items": scheduled_items,
            "timeline_groups": timeline_groups,
            "next_post": next_post,
            "blacklist_items": blacklist_items,
            "logs": logs,
            "settings": settings,
            "categories": SHOPEE_CATEGORIES,
            "active_tab": tab,
            "status_filter": status_filter,
            "category_filter": category_filter,
            "view_mode": view_mode,
            "server_now_wib": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "msg": msg,
        }
    )
    if key and secrets.compare_digest(key, admin_secret):
        session_token = get_admin_session_token(admin_secret)
        response.set_cookie("admin_token", session_token, max_age=86400 * 30, httponly=True)
    return response


@app.post("/admin/login")
async def admin_login(password: str = Form(...), db: ProductQueueDB = Depends(get_db)):
    admin_secret = get_admin_secret(db)
    if secrets.compare_digest(password.strip(), admin_secret.strip()):
        resp = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        session_token = get_admin_session_token(admin_secret)
        resp.set_cookie("admin_token", session_token, max_age=86400 * 30, httponly=True)
        return resp
    return RedirectResponse(url="/admin?msg=Kunci+akses+tidak+valid", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/admin/logout")
async def admin_logout():
    resp = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie("admin_token")
    return resp


# ===================== KONTROL & AKSI PRODUK =====================

# Set in-memory lock untuk mencegah eksekusi duplikat serentak (idempotency guard)
_PUBLISHING_LOCKS = set()

def _publish_product_to_channels(db: ProductQueueDB, item: Dict[str, Any]) -> str:
    """Mempublikasikan produk ke seluruh channel aktif via PublisherDispatcher dengan pengaman anti-duplikat."""
    item_id = str(item["item_id"])
    
    # 1. Cek apakah produk sudah berstatus POSTED di database
    current = db.get(item_id)
    if current and current.get("status") == "POSTED":
        return f"Produk {item_id} sudah pernah diposting sebelumnya. Dibatalkan untuk mencegah duplikat."

    # 2. Cek apakah produk sedang dalam proses publish oleh worker/thread lain
    if item_id in _PUBLISHING_LOCKS:
        return f"Produk {item_id} sedang diproses. Permintaan duplikat dibatalkan."

    _PUBLISHING_LOCKS.add(item_id)
    try:
        dispatcher = get_publisher_dispatcher(db=db)
        post_type = item.get("post_type", "AFFILIATE")
        # Edukasi murni tanpa link promosi; hanya postingan AFFILIATE yang menyertakan link Shopee
        if post_type == "EDUCATION":
            comment_text = None
        else:
            comment_text = build_comment(item)

        result = dispatcher.dispatch(
            image_url=item.get("image_url", ""),
            caption=item.get("caption", ""),
            comment_text=comment_text,
            video_url=item.get("video_url", ""),
            media_type=item.get("media_type", "IMAGE")
        )

        if result.is_success:
            fb_id = result.post_ids.get("Facebook Page")
            th_id = result.post_ids.get("Threads")
            ig_id = result.post_ids.get("Instagram")
            db.mark_posted_multi(item_id, fb_id, th_id, ig_id)
            db.mark_comment_done(item_id)
            return result.summary()
        else:
            err_msg = result.summary()
            db.set_error(item_id, err_msg)
            return f"Gagal publikasi: {err_msg}"
    finally:
        _PUBLISHING_LOCKS.discard(item_id)


@app.post("/admin/action")
async def admin_action(
    request: Request,
    item_id: str = Form(...),
    action: str = Form(...),
    reason: Optional[str] = Form(""),
    image_url: Optional[str] = Form(None),
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if action == "approve":
        db.approve(item_id)
        msg = f"Produk {item_id} berhasil disetujui (APPROVED)"
    elif action == "reject":
        db.reject(item_id, reason=reason or "Ditolak manual oleh admin")
        msg = f"Produk {item_id} ditandai ditolak"
    elif action == "delete":
        db.delete(item_id)
        msg = f"Produk {item_id} berhasil dihapus dari database"
    elif action == "update_image":
        if image_url and image_url.strip():
            db.update_image(item_id, image_url.strip())
            msg = "Foto cover berhasil diganti dengan foto stok komersial bebas AI!"
        else:
            msg = "URL foto tidak boleh kosong"
    elif action == "toggle_post_type":
        item = db.get(item_id)
        current_type = item.get("post_type", "AFFILIATE") if item else "AFFILIATE"
        new_type = "EDUCATION" if current_type == "AFFILIATE" else "AFFILIATE"
        db.update_post_type(item_id, new_type)
        label = "Edukasi Murni (Bebas Link)" if new_type == "EDUCATION" else "Rekomendasi Afiliasi (Ada Link)"
        msg = f"Tipe postingan diubah menjadi: {label}"
    elif action == "publish_now":
        item = db.get(item_id)
        if not item:
            return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg=Produk+tidak+ditemukan", status_code=status.HTTP_303_SEE_OTHER)
        msg = _publish_product_to_channels(db, item)
    else:
        msg = "Aksi tidak dikenali"

    return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/education/create")
async def admin_create_education_post(
    request: Request,
    topic: str = Form(...),
    category: str = Form("Rumah Tangga & Dekorasi"),
    search_visual: str = Form(""),
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    """Membuat postingan edukasi murni (non-komersial) via 4-Stage Content Engine."""
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        scheduled_list = db.list_scheduled(limit=100)
        scheduled_at_str = SmartScheduler.get_next_slot(scheduled_list)

        edu_service = EducationContentService(db=db)
        item = edu_service.create_and_queue(
            topic=topic.strip(),
            category=category,
            search_query_visual=search_visual.strip() or topic.strip(),
            scheduled_at=scheduled_at_str
        )
        msg = f"Artikel edukasi murni '{item['product_name'][:30]}' berhasil dibuat & dijadwalkan pada {scheduled_at_str} WIB!"
    except Exception as e:
        msg = f"Gagal membuat artikel edukasi: {e}"

    return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/education/auto-replenish")
async def admin_auto_replenish_education(
    request: Request,
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    """Memicu pengisian otomatis konten edukasi murni untuk seluruh slot kosong 3 hari ke depan."""
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        edu_service = EducationContentService(db=db)
        created = edu_service.auto_replenish(days_ahead=3)
        msg = f"Berhasil meriset & menjadwalkan {len(created)} konten edukasi murni (5-Stage Engine) untuk 3 hari ke depan!" if created else "Seluruh slot jadwal edukasi 3 hari ke depan sudah terisi rapi."
    except Exception as e:
        msg = f"Gagal auto-replenish edukasi: {e}"

    return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/action/reject-quality")
async def admin_reject_quality(
    request: Request,
    item_id: str = Form(...),
    reason: str = Form("Kualitas produk buruk / rating rendah"),
    add_blacklist: bool = Form(True),
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    """Menolak produk karena kualitas buruk dan memasukkannya ke memori daftar hitam."""
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    db.reject_product_quality(item_id, reason=reason.strip(), add_blacklist=add_blacklist)
    msg = f"Produk berhasil ditolak ke tab 'Ditolak / Kualitas Rendah' dan merk dimasukkan daftar hitam."
    return RedirectResponse(url=f"/admin?tab={redirect_tab}&status_filter=REJECTED&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/action/restore")
async def admin_restore_product(
    request: Request,
    item_id: str = Form(...),
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    """Memulihkan produk dari status REJECTED kembali ke APPROVED."""
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    db.restore_product(item_id)
    msg = f"Produk {item_id} berhasil dipulihkan ke status disetujui."
    return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/action/update-rating")
async def admin_update_rating(
    request: Request,
    item_id: str = Form(...),
    rating: float = Form(...),
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    """Memperbarui rating produk secara manual."""
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    db.update_rating(item_id, float(rating))
    msg = f"Rating produk berhasil diperbarui menjadi {rating:.1f}"
    return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/update-caption")
async def admin_update_caption(
    request: Request,
    item_id: str = Form(...),
    caption: str = Form(...),
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    db.update_caption(item_id, caption.strip())
    return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg=Caption+berhasil+diperbarui", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/reschedule")
async def admin_reschedule(
    request: Request,
    item_id: str = Form(...),
    scheduled_at: str = Form(...),
    redirect_tab: str = Form("products"),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    db.update_schedule(item_id, scheduled_at.strip())
    return RedirectResponse(url=f"/admin?tab={redirect_tab}&msg=Jadwal+posting+berhasil+diubah", status_code=status.HTTP_303_SEE_OTHER)


# ===================== FITUR 1: SINGLE LINK INSTANT =====================

@app.post("/admin/single-link")
async def admin_single_link_import(
    request: Request,
    url: str = Form(...),
    use_gemini: bool = Form(True),
    auto_approve: bool = Form(True),
    db: ProductQueueDB = Depends(get_db)
):
    """Input 1 link Shopee saja -> AI mengambil foto/video asli seller,
    memvalidasi rating/kredibilitas (Quality Gate), membuat caption edukasi renyah tanpa emoji,
    dan mengalokasikan jadwal posting jika lolos kurasi.
    """
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    clean_url = url.strip()
    if not clean_url:
        return RedirectResponse(url="/admin?tab=products&msg=URL+produk+diperlukan", status_code=status.HTTP_303_SEE_OTHER)

    scraper = get_product_scraper()
    scraped = scraper.scrape_preview(clean_url)

    item = {
        "item_id": scraped["item_id"],
        "product_name": scraped["product_name"],
        "product_url": scraped["product_url"],
        "affiliate_link": clean_url,
        "image_url": scraped.get("image_url", ""),
        "video_url": scraped.get("video_url", ""),
        "media_type": scraped.get("media_type", "IMAGE"),
        "price": scraped.get("price", 0),
        "discount_rate": 0,
        "rating": 0.0,
        "sales": 1000,
        "commission_rate": 10.0,
        "commission_amount": scraped.get("price", 0) * 0.1,
        "category": scraped.get("category", "Rumah Tangga & Dekorasi"),
        "platform": "SHOPEE",
        "status": "APPROVED" if auto_approve else "PENDING",
        "post_type": "AFFILIATE",
        "rejection_reason": "",
        "caption": ""
    }

    # Quality Gate & Blacklist Guard
    is_bl, bl_reason = db.is_blacklisted(item)
    q_res = QualityInspector.inspect(item)
    item["rating"] = q_res["rating"]

    if is_bl:
        item["status"] = "REJECTED"
        item["rejection_reason"] = f"Ditolak otomatis (Daftar Hitam): {bl_reason}"
        item["scheduled_at"] = ""
    elif q_res["verdict"] == "REJECT":
        item["status"] = "REJECTED"
        item["rejection_reason"] = q_res["reason"]
        item["scheduled_at"] = ""
    else:
        # Generate caption edukasi santai & natural tanpa emoji
        caption_gen = get_caption_generator(db=db, use_ai=use_gemini)
        item["caption"] = caption_gen.generate(item)
        scheduled = SmartScheduler.schedule_batch([item])
        item = scheduled[0] if scheduled else item

    db.insert_product(item)
    if item["status"] == "REJECTED":
        msg = f"Perhatian: Produk '{item['product_name'][:30]}' DITOLAK ke tab Kualitas Rendah ({item['rejection_reason']})"
        return RedirectResponse(url=f"/admin?tab=products&status_filter=REJECTED&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)
    else:
        msg = f"Produk '{item['product_name'][:30]}' lolos kurasi & dijadwalkan pada {item.get('scheduled_at')}!"
        return RedirectResponse(url=f"/admin?tab=products&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


# ===================== FITUR 2: BULK IMPORT (CSV & MULTI-LINK) =====================

def _bg_run_bulk_import(
    csv_text: str,
    raw_links: str,
    auto_approve: bool,
    use_gemini: bool,
    db_path: str = "temuan_harian.db"
):
    """Proses latar belakang dengan Quality Gate terintegrasi."""
    from repositories.database import ProductQueueDB
    from services.bulk_importer import ShopeeBulkImporter
    db = ProductQueueDB(db_path)
    importer = ShopeeBulkImporter()

    items = []
    if csv_text.strip():
        items = importer.parse_csv(csv_text)
    elif raw_links.strip():
        for line in raw_links.splitlines():
            l = line.strip()
            if l.startswith("http"):
                items.append({
                    "item_id": "",
                    "product_name": "",
                    "affiliate_link": l,
                    "product_url": l,
                    "price": 0,
                    "sales": 0,
                    "commission_rate": 0,
                    "commission_amount": 0,
                    "category": "",
                    "platform": "SHOPEE",
                    "status": "APPROVED" if auto_approve else "PENDING"
                })

    if not items:
        db.log_activity("BULK_IMPORT", "Gagal impor massal: Tidak ada data valid yang ditemukan.", status="FAILED")
        return

    db.log_activity("BULK_IMPORT", f"Memulai impor massal {len(items)} produk dengan Quality Gate...", status="INFO")

    api_key = db.get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY")
    enriched = importer.process_and_enrich(items, use_gemini=use_gemini, gemini_api_key=api_key, db=db)

    approved_count = 0
    rejected_count = 0
    for it in enriched:
        if it.get("status") != "REJECTED" and auto_approve:
            it["status"] = "APPROVED"
        if db.insert_product(it):
            if it.get("status") == "REJECTED":
                rejected_count += 1
            else:
                approved_count += 1

    db.log_activity(
        "BULK_IMPORT",
        f"Impor selesai: {approved_count} produk dijadwalkan, {rejected_count} produk kualitas buruk dipisahkan ke tab Ditolak.",
        status="SUCCESS"
    )


@app.post("/admin/bulk-import")
async def admin_bulk_import(
    request: Request,
    background_tasks: BackgroundTasks,
    csv_file: Optional[UploadFile] = File(None),
    links_text: Optional[str] = Form(""),
    use_gemini: bool = Form(True),
    auto_approve: bool = Form(True),
    db: ProductQueueDB = Depends(get_db)
):
    """Menerima file CSV ekspor Shopee Affiliate atau daftar teks link sekaligus."""
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    csv_content = ""
    if csv_file and csv_file.filename:
        content_bytes = await csv_file.read()
        csv_content = content_bytes.decode("utf-8", errors="ignore")

    raw_links = links_text or ""
    if not csv_content.strip() and not raw_links.strip():
        return RedirectResponse(url="/admin?tab=products&msg=Mohon+unggah+file+CSV+atau+masukkan+link+produk.", status_code=status.HTTP_303_SEE_OTHER)

    db_path = os.getenv("TEMUAN_DB", "temuan_harian.db")
    background_tasks.add_task(
        _bg_run_bulk_import,
        csv_content,
        raw_links,
        auto_approve,
        use_gemini,
        db_path
    )

    msg = "Impor massal sedang diproses di latar belakang dengan Quality Gate. Produk rating jelek akan otomatis dipisahkan."
    return RedirectResponse(url=f"/admin?tab=products&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/quick-add")
async def admin_quick_add(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    affiliate_link: str = Form(...),
    price: float = Form(0),
    rating: float = Form(5.0),
    sales: int = Form(0),
    category: str = Form("Rumah Tangga & Dekorasi"),
    image_url: Optional[str] = Form(None),
    platform: str = Form("SHOPEE"),
    use_ai: bool = Form(True),
    auto_approve: bool = Form(True),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    scraper = get_product_scraper()
    scraped = scraper.scrape_preview(url.strip())

    item = {
        "item_id": scraped["item_id"],
        "product_name": name.strip() or scraped["product_name"],
        "product_url": url.strip(),
        "affiliate_link": affiliate_link.strip(),
        "image_url": image_url.strip() if image_url else scraped["image_url"],
        "video_url": scraped.get("video_url", ""),
        "media_type": scraped.get("media_type", "IMAGE"),
        "price": price or scraped["price"],
        "discount_rate": 0,
        "rating": rating,
        "sales": sales,
        "commission_rate": 10.0,
        "commission_amount": (price or scraped["price"]) * 0.1,
        "category": category or scraped["category"],
        "platform": platform,
        "status": "APPROVED" if auto_approve else "PENDING",
    }

    # Quality Gate
    q_res = QualityInspector.inspect(item)
    if q_res["verdict"] == "REJECT":
        item["status"] = "REJECTED"
        item["rejection_reason"] = q_res["reason"]
        item["scheduled_at"] = ""
    else:
        caption_gen = get_caption_generator(db=db, use_ai=use_ai)
        item["caption"] = caption_gen.generate(item)
        scheduled = SmartScheduler.schedule_batch([item])
        item = scheduled[0] if scheduled else item

    db.insert_product(item)
    return RedirectResponse(url="/admin?tab=products&msg=Produk+berhasil+ditambahkan", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/trigger/scheduler")
async def trigger_scheduler_manual(request: Request, db: ProductQueueDB = Depends(get_db)):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    product = db.next_approved()
    if not product:
        return RedirectResponse(url="/admin?msg=Tidak+ada+produk+dalam+antrean+siap+posting", status_code=status.HTTP_303_SEE_OTHER)

    summary = _publish_product_to_channels(db, product)
    return RedirectResponse(url=f"/admin?msg={summary}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/trigger/retry-comments")
async def trigger_retry_comments(request: Request, db: ProductQueueDB = Depends(get_db)):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    pending_comments = db.list_comment_pending()
    if not pending_comments:
        return RedirectResponse(url="/admin?tab=logs&msg=Tidak+ada+komentar+tertunda", status_code=status.HTTP_303_SEE_OTHER)

    dispatcher = get_publisher_dispatcher(db=db)
    success = 0
    for item in pending_comments:
        comment_text = build_comment(item)
        if dispatcher.dispatch_comment(item.get("fb_post_id", ""), comment_text):
            db.mark_comment_done(item["item_id"])
            success += 1

    return RedirectResponse(url=f"/admin?tab=logs&msg={success}+komentar+berhasil+diposting", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/api/stock-photos/search")
async def api_search_stock_photos(
    request: Request,
    q: str,
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    from services.stock_photos import StockPhotoService
    photos = StockPhotoService.search(q, db=db)
    return {"query": q, "results": photos}


@app.post("/admin/settings")
async def update_settings(request: Request, db: ProductQueueDB = Depends(get_db)):
    global _META_CIRCUIT_BREAKER_UNTIL
    _META_CIRCUIT_BREAKER_UNTIL = None  # Reset circuit breaker jika admin menyimpan token/pengaturan baru
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    form_data = await request.form()
    for key, val in form_data.items():
        if key not in ["csrf_token", "action"]:
            db.set_setting(key, str(val).strip())

    return RedirectResponse(url="/admin?tab=settings&msg=Pengaturan+berhasil+disimpan", status_code=status.HTTP_303_SEE_OTHER)


# ===================== META ADS MARKETING API =====================

@app.post("/admin/ads/create-campaign")
async def create_ad_campaign(
    request: Request,
    campaign_name: str = Form(...),
    daily_budget: int = Form(50000),
    db: ProductQueueDB = Depends(get_db)
):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")

    manager = get_ads_manager(db=db)
    try:
        camp_id = manager.create_traffic_campaign(campaign_name, daily_budget_idr=daily_budget)
        msg = f"Kampanye+iklan+berhasil+dibuat+(ID:+{camp_id})"
    except Exception as e:
        msg = f"Gagal+membuat+iklan:+{str(e)}"

    return RedirectResponse(url=f"/admin?tab=settings&msg={msg}", status_code=status.HTTP_303_SEE_OTHER)


# ===================== TIKTOK AFFILIATE AI STUDIO API =====================

@app.post("/api/tiktok/analyze")
async def api_tiktok_analyze(request: Request, db: ProductQueueDB = Depends(get_db)):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    item_id = body.get("item_id")
    product = db.get(item_id) if item_id else body.get("product")
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    from services.tiktok_script import TikTokContentStudioService
    studio = TikTokContentStudioService(db=db)
    res = studio.analyze_product_opportunity(product)
    return res


@app.post("/api/tiktok/generate-script")
async def api_tiktok_generate_script(request: Request, db: ProductQueueDB = Depends(get_db)):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    item_id = body.get("item_id")
    product = db.get(item_id) if item_id else body.get("product")
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    content_format = body.get("content_format", "problem_solution")
    duration = int(body.get("duration", 30))
    honesty_mode = body.get("honesty_mode", "research_based")
    hook_direction = body.get("hook_direction", "")

    from services.tiktok_script import TikTokContentStudioService
    studio = TikTokContentStudioService(db=db)
    res = studio.generate_tiktok_script(
        product,
        content_format=content_format,
        duration_seconds=duration,
        honesty_mode=honesty_mode,
        custom_hook_direction=hook_direction
    )
    return res


@app.post("/api/tiktok/synthesize-tts")
async def api_tiktok_synthesize_tts(request: Request, db: ProductQueueDB = Depends(get_db)):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    text = body.get("text", "").strip()
    voice_name = body.get("voice_name", "Kore")
    item_id = body.get("item_id", "temp")
    if not text:
        raise HTTPException(status_code=400, detail="Teks narasi tidak boleh kosong")

    from services.gemini_tts import GeminiTTSService
    audio_dir = os.path.join(os.path.dirname(__file__), "static", "audio")
    os.makedirs(audio_dir, exist_ok=True)
    audio_filename = f"tts_{item_id}_{voice_name.lower()}.mp3"
    audio_path = os.path.join(audio_dir, audio_filename)

    tts = GeminiTTSService(db=db)
    res = tts.synthesize(text=text, voice_name=voice_name, output_path=audio_path)
    if res.get("ok"):
        res["audio_url"] = f"/static/audio/{audio_filename}"
    return res


@app.post("/api/tiktok/render-video")
async def api_tiktok_render_video(request: Request, db: ProductQueueDB = Depends(get_db)):
    if not verify_admin(request, db):
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    item_id = body.get("item_id")
    product = db.get(item_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")

    script = body.get("script", {})
    audio_url = body.get("audio_url", "")
    voice_name = body.get("voice_name", "Kore")

    from services.gemini_tts import GeminiTTSService
    from services.video_producer import TikTokVideoProducer

    # 1. Pastikan audio voiceover tersedia
    audio_dir = os.path.join(os.path.dirname(__file__), "static", "audio")
    os.makedirs(audio_dir, exist_ok=True)
    audio_filename = f"tts_{item_id}_{voice_name.lower()}.mp3"
    audio_path = os.path.join(audio_dir, audio_filename)

    if not os.path.exists(audio_path) or not audio_url:
        vo_text = script.get("full_voiceover_text") or script.get("main_narration") or product.get("product_name")
        tts = GeminiTTSService(db=db)
        tts_res = tts.synthesize(text=vo_text, voice_name=voice_name, output_path=audio_path)
        if not tts_res.get("ok"):
            return {"ok": False, "error": f"Gagal membuat voiceover: {tts_res.get('error')}"}

    # 2. Render Video 9:16
    producer = TikTokVideoProducer()
    vid_res = producer.render_video(product, script, audio_path)
    if vid_res.get("ok"):
        script_json_str = json.dumps(script, ensure_ascii=False)
        db.update_video(
            item_id=item_id,
            video_url=vid_res["video_url"],
            thumbnail_url=vid_res.get("thumbnail_url", ""),
            script_text=script_json_str
        )
    return vid_res


@app.get("/api/tiktok/recommendation")
async def api_tiktok_recommendation(item_id: str, db: ProductQueueDB = Depends(get_db)):
    """Mengambil rekomendasi cerdas format & suara video TikTok untuk produk."""
    product = db.get_product(item_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produk tidak ditemukan")
    rec = get_recommended_settings(product)
    return {"ok": True, "recommendation": rec}
