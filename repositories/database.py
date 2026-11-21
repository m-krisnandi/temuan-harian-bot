"""Antrean produk, log aktivitas, dan pengaturan (SQLite).
Menerapkan Prinsip SOLID:
- Single Responsibility: Terpisah antara ProductRepository, SettingsRepository, ActivityLogRepository, dan QualityBlacklistRepository.
- Interface Segregation: Menerapkan IProductRepository, ISettingsRepository, IActivityLogRepository.
- Open/Closed & Dependency Inversion: Database Connection Factory dan Repositori terisolasi.
"""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import (
    IProductRepository,
    ISettingsRepository,
    IActivityLogRepository,
)

WIB = timezone(timedelta(hours=7))

PENDING, APPROVED, REJECTED, POSTED = "PENDING", "APPROVED", "REJECTED", "POSTED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConnectionFactory:
    """Single Responsibility: Mengelola koneksi database SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._shared_memory_conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self.db_path == ":memory:":
            if self._shared_memory_conn is None:
                self._shared_memory_conn = sqlite3.connect(":memory:")
                self._shared_memory_conn.row_factory = sqlite3.Row
            return self._shared_memory_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def execute(self, sql: str, params: tuple = ()) -> int:
        conn = self.connect()
        try:
            with conn:
                return conn.execute(sql, params).rowcount
        finally:
            if self.db_path != ":memory:":
                conn.close()

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            if self.db_path != ":memory:":
                conn.close()


class SettingsRepository(ISettingsRepository):
    """Single Responsibility: Mengelola tabel settings."""

    def __init__(self, conn_factory: ConnectionFactory):
        self._conn = conn_factory

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        rows = self._conn.query("SELECT value FROM settings WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def get_all(self) -> Dict[str, str]:
        rows = self._conn.query("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows}


class ActivityLogRepository(IActivityLogRepository):
    """Single Responsibility: Mengelola tabel activity_logs."""

    def __init__(self, conn_factory: ConnectionFactory):
        self._conn = conn_factory

    def log(self, event_type: str, message: str, status: str = "SUCCESS") -> None:
        self._conn.execute(
            "INSERT INTO activity_logs (event_type, message, status, created_at) VALUES (?, ?, ?, ?)",
            (event_type, message, status, _now()),
        )

    def list_recent(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self._conn.query(
            "SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,)
        )


class QualityBlacklistRepository:
    """Single Responsibility: Mengelola daftar hitam merk/tipe produk yang kualitasnya buruk."""

    def __init__(self, conn_factory: ConnectionFactory, logger: Optional[IActivityLogRepository] = None):
        self._conn = conn_factory
        self._logger = logger

    def add(
        self,
        item_id: str = "",
        shop_name: str = "",
        brand: str = "",
        product_type: str = "",
        keyword_signature: str = "",
        reason: str = ""
    ) -> int:
        rowcount = self._conn.execute(
            """
            INSERT INTO quality_blacklist (item_id, shop_name, brand, product_type, keyword_signature, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item_id).strip(),
                shop_name.strip(),
                brand.strip().lower(),
                product_type.strip().lower(),
                keyword_signature.strip().lower(),
                reason,
                _now(),
            )
        )
        if self._logger:
            self._logger.log("BLACKLIST", f"Ditambahkan ke blacklist: [{brand or item_id}] - {reason}")
        return rowcount

    def is_blacklisted(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        item_id = str(item.get("item_id", "")).strip()
        shop_name = str(item.get("shop_name", "")).strip().lower()
        product_name = str(item.get("product_name", "")).strip().lower()
        brand = str(item.get("brand", "")).strip().lower()

        # 1. Cek langsung dari ID produk
        if item_id:
            rows = self._conn.query(
                "SELECT reason FROM quality_blacklist WHERE item_id = ? AND item_id != ''",
                (item_id,)
            )
            if rows:
                return True, f"Produk ini masuk daftar hitam: {rows[0]['reason']}"

        # 2. Cek semua aturan merk / tipe / keyword
        rules = self._conn.query("SELECT * FROM quality_blacklist")
        for r in rules:
            rule_brand = (r.get("brand") or "").strip().lower()
            rule_type = (r.get("product_type") or "").strip().lower()
            rule_shop = (r.get("shop_name") or "").strip().lower()
            rule_kw = (r.get("keyword_signature") or "").strip().lower()

            if rule_brand and (rule_brand in product_name or (brand and rule_brand == brand)):
                if rule_type:
                    if rule_type in product_name:
                        return True, f"Merk '{rule_brand}' tipe '{rule_type}' diblokir kualitas: {r['reason']}"
                else:
                    return True, f"Merk '{rule_brand}' diblokir karena kualitas buruk: {r['reason']}"

            if rule_shop and rule_shop == shop_name and rule_type:
                if rule_type in product_name:
                    return True, f"Toko '{rule_shop}' untuk tipe '{rule_type}' pernah ditolak kualitasnya"

            if rule_kw and rule_kw in product_name:
                return True, f"Mengandung kata kunci yang di-blacklist '{rule_kw}': {r['reason']}"

        return False, ""

    def list_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._conn.query("SELECT * FROM quality_blacklist ORDER BY id DESC LIMIT ?", (limit,))

    def delete(self, blacklist_id: int) -> None:
        self._conn.execute("DELETE FROM quality_blacklist WHERE id = ?", (blacklist_id,))


class ProductRepository(IProductRepository):
    """Single Responsibility: Mengelola tabel products."""

    def __init__(self, conn_factory: ConnectionFactory, logger: Optional[IActivityLogRepository] = None):
        self._conn = conn_factory
        self._logger = logger

    def exists(self, item_id: str) -> bool:
        return bool(self._conn.query("SELECT 1 FROM products WHERE item_id = ?", (str(item_id),)))

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        rows = self._conn.query("SELECT * FROM products WHERE item_id = ?", (str(item_id),))
        return rows[0] if rows else None

    def insert(self, item: Dict[str, Any]) -> bool:
        category = item.get("category") or "Rumah Tangga & Dekorasi"
        init_status = item.get("status") or PENDING
        rejection_reason = item.get("rejection_reason", "")
        rowcount = self._conn.execute(
            """
            INSERT OR REPLACE INTO products (
                item_id, product_name, product_url, affiliate_link, image_url,
                price, discount_rate, rating, sales, commission_rate, caption,
                category, status, platform, tiktok_link, scheduled_at,
                media_type, video_url, market_score, commission_amount, shop_name, rejection_reason, post_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(item["item_id"]),
                item["product_name"],
                item["product_url"],
                item["affiliate_link"],
                item.get("image_url"),
                item.get("price", 0),
                item.get("discount_rate", 0),
                item.get("rating", 0),
                item.get("sales", 0),
                item.get("commission_rate", 0),
                item.get("caption", ""),
                category,
                init_status,
                item.get("platform", "SHOPEE"),
                item.get("tiktok_link", ""),
                item.get("scheduled_at", ""),
                item.get("media_type", "IMAGE"),
                item.get("video_url", ""),
                float(item.get("market_score", 0.0) or 0.0),
                float(item.get("commission_amount", 0.0) or 0.0),
                item.get("shop_name", ""),
                rejection_reason,
                item.get("post_type", "AFFILIATE"),
                _now(),
            ),
        )
        if rowcount == 1 and self._logger:
            self._logger.log("INSERT", f"Produk [{item.get('platform', 'SHOPEE')}] baru: {item['product_name'][:40]}")
        return rowcount == 1

    def approve(self, item_id: str) -> None:
        self._conn.execute(
            "UPDATE products SET status = ?, approved_at = ?, rejection_reason = '' WHERE item_id = ?",
            (APPROVED, _now(), str(item_id)),
        )
        if self._logger:
            self._logger.log("APPROVE", f"Produk disetujui ID: {item_id}")

    def reject(self, item_id: str, reason: str = "") -> None:
        self._conn.execute(
            "UPDATE products SET status = ?, rejection_reason = ?, scheduled_at = '' WHERE item_id = ?",
            (REJECTED, reason, str(item_id))
        )
        if self._logger:
            self._logger.log("REJECT", f"Produk ditolak kualitas ID {item_id}: {reason or 'Tanpa keterangan'}")

    def delete(self, item_id: str) -> None:
        self._conn.execute("DELETE FROM products WHERE item_id = ?", (str(item_id),))
        if self._logger:
            self._logger.log("DELETE", f"Produk dihapus ID: {item_id}")

    def update_rating(self, item_id: str, rating: float) -> None:
        self._conn.execute("UPDATE products SET rating = ? WHERE item_id = ?", (rating, str(item_id)))

    def update_caption(self, item_id: str, caption: str) -> None:
        self._conn.execute("UPDATE products SET caption = ? WHERE item_id = ?", (caption, str(item_id)))

    def update_image(self, item_id: str, image_url: str) -> None:
        self._conn.execute("UPDATE products SET image_url = ? WHERE item_id = ?", (image_url.strip(), str(item_id)))
        if self._logger:
            self._logger.log("UPDATE_IMAGE", f"Perbarui foto cover ID {item_id}: {image_url[:40]}")

    def update_post_type(self, item_id: str, post_type: str) -> None:
        self._conn.execute(
            "UPDATE products SET post_type = ? WHERE item_id = ?",
            (post_type, str(item_id))
        )
        if self._logger:
            self._logger.log("POST_TYPE", f"Ubah tipe postingan ID {item_id}: {post_type}")

    def update_schedule(self, item_id: str, scheduled_at: str) -> None:
        self._conn.execute(
            "UPDATE products SET scheduled_at = ?, status = ?, rejection_reason = '' WHERE item_id = ?",
            (scheduled_at, APPROVED, str(item_id))
        )
        if self._logger:
            self._logger.log("SCHEDULE", f"Jadwal posting diatur: {scheduled_at} ID: {item_id}")

    def list_scheduled(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._conn.query(
            "SELECT * FROM products WHERE status = ? AND scheduled_at != '' ORDER BY scheduled_at ASC LIMIT ?",
            (APPROVED, limit),
        )

    def get_due_scheduled(self) -> Optional[Dict[str, Any]]:
        now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M")
        rows = self._conn.query(
            "SELECT * FROM products WHERE status = ? AND scheduled_at != '' AND scheduled_at <= ? ORDER BY scheduled_at ASC LIMIT 1",
            (APPROVED, now_wib),
        )
        return rows[0] if rows else None

    def list_all(self, status: str = "ALL", category: str = "ALL", limit: int = 100) -> List[Dict[str, Any]]:
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        if status != "ALL":
            query += " AND status = ?"
            params.append(status)
        if category != "ALL":
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY CASE WHEN scheduled_at != '' AND status = 'APPROVED' THEN 0 ELSE 1 END, scheduled_at ASC, created_at DESC LIMIT ?"
        params.append(limit)
        return self._conn.query(query, tuple(params))

    def mark_posted_multi(
        self,
        item_id: str,
        fb_post_id: Optional[str] = None,
        threads_post_id: Optional[str] = None,
        ig_post_id: Optional[str] = None
    ) -> None:
        updates = ["status = 'POSTED'", "posted_at = ?", "last_error = NULL"]
        params: List[Any] = [_now()]
        channels = []

        if fb_post_id:
            updates.append("fb_post_id = ?")
            params.append(fb_post_id)
            channels.append("FB")
        if threads_post_id:
            updates.append("threads_post_id = ?")
            params.append(threads_post_id)
            channels.append("Threads")
        if ig_post_id:
            updates.append("ig_post_id = ?")
            params.append(ig_post_id)
            channels.append("Instagram")

        params.append(str(item_id))
        self._conn.execute(
            f"UPDATE products SET {', '.join(updates)} WHERE item_id = ?",
            tuple(params),
        )
        channel_names = ", ".join(channels) or "Social"
        if self._logger:
            self._logger.log("PUBLISH", f"Diposting ke [{channel_names}] ID: {item_id}")

    def mark_comment_done(self, item_id: str) -> None:
        self._conn.execute(
            "UPDATE products SET comment_done = 1, last_error = NULL WHERE item_id = ?",
            (str(item_id),),
        )
        if self._logger:
            self._logger.log("COMMENT", f"Komentar link berhasil diposting ID: {item_id}")

    def set_error(self, item_id: str, message: str) -> None:
        self._conn.execute(
            "UPDATE products SET last_error = ? WHERE item_id = ?", (message[:500], str(item_id))
        )
        if self._logger:
            self._logger.log("ERROR", f"Error pada produk {item_id}: {message[:100]}", status="FAILED")

    def list_pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._conn.query(
            "SELECT * FROM products WHERE status = ? ORDER BY sales DESC LIMIT ?",
            (PENDING, limit),
        )

    def next_approved(self) -> Optional[Dict[str, Any]]:
        due = self.get_due_scheduled()
        if due:
            return due
        rows = self._conn.query(
            "SELECT * FROM products WHERE status = ? ORDER BY market_score DESC, approved_at ASC LIMIT 1",
            (APPROVED,),
        )
        return rows[0] if rows else None

    def list_comment_pending(self) -> List[Dict[str, Any]]:
        return self._conn.query(
            "SELECT * FROM products WHERE status = ? AND comment_done = 0",
            (POSTED,),
        )

    def count_posted_today(self) -> int:
        start_wib = datetime.now(WIB).replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_wib.astimezone(timezone.utc).isoformat(timespec="seconds")
        rows = self._conn.query(
            "SELECT COUNT(*) AS n FROM products WHERE posted_at >= ?", (start_utc,)
        )
        return rows[0]["n"]


class ProductQueueDB:
    """Facade / Unit of Work yang menggabungkan seluruh repositori."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("TEMUAN_DB", "temuan_harian.db")
        db_path = self.db_path
        self.db_path = db_path
        self._conn_factory = ConnectionFactory(db_path)
        self._init_tables()
        self.settings_repo = SettingsRepository(self._conn_factory)
        self.logs_repo = ActivityLogRepository(self._conn_factory)
        self.product_repo = ProductRepository(self._conn_factory, logger=self.logs_repo)
        self.blacklist_repo = QualityBlacklistRepository(self._conn_factory, logger=self.logs_repo)

    def _connect(self) -> sqlite3.Connection:
        """Alias helper untuk koneksi langsung."""
        return self._conn_factory.connect()

    def _init_tables(self) -> None:
        conn = self._conn_factory.connect()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS products (
                        item_id TEXT PRIMARY KEY,
                        product_name TEXT NOT NULL,
                        product_url TEXT NOT NULL,
                        affiliate_link TEXT NOT NULL,
                        image_url TEXT,
                        price REAL,
                        discount_rate REAL,
                        rating REAL,
                        sales INTEGER,
                        commission_rate REAL,
                        caption TEXT,
                        category TEXT DEFAULT 'Rumah Tangga & Dekorasi',
                        status TEXT NOT NULL DEFAULT 'PENDING',
                        platform TEXT NOT NULL DEFAULT 'SHOPEE',
                        tiktok_link TEXT DEFAULT '',
                        fb_post_id TEXT,
                        threads_post_id TEXT,
                        ig_post_id TEXT,
                        comment_done INTEGER NOT NULL DEFAULT 0,
                        last_error TEXT,
                        created_at TEXT,
                        approved_at TEXT,
                        posted_at TEXT
                    )
                    """
                )
                columns_to_add = [
                    ("platform", "TEXT NOT NULL DEFAULT 'SHOPEE'"),
                    ("tiktok_link", "TEXT DEFAULT ''"),
                    ("category", "TEXT DEFAULT 'Rumah Tangga & Dekorasi'"),
                    ("threads_post_id", "TEXT DEFAULT ''"),
                    ("ig_post_id", "TEXT DEFAULT ''"),
                    ("scheduled_at", "TEXT DEFAULT ''"),
                    ("media_type", "TEXT DEFAULT 'IMAGE'"),
                    ("video_url", "TEXT DEFAULT ''"),
                    ("market_score", "REAL DEFAULT 0.0"),
                    ("commission_amount", "REAL DEFAULT 0.0"),
                    ("shop_name", "TEXT DEFAULT ''"),
                    ("rejection_reason", "TEXT DEFAULT ''"),
                    ("post_type", "TEXT DEFAULT 'AFFILIATE'"),
                ]
                for col, col_def in columns_to_add:
                    try:
                        conn.execute(f"ALTER TABLE products ADD COLUMN {col} {col_def}")
                    except sqlite3.OperationalError:
                        pass

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS activity_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'SUCCESS',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS quality_blacklist (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_id TEXT DEFAULT '',
                        shop_name TEXT DEFAULT '',
                        brand TEXT DEFAULT '',
                        product_type TEXT DEFAULT '',
                        keyword_signature TEXT DEFAULT '',
                        reason TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
        finally:
            if self.db_path != ":memory:":
                conn.close()

    # ---- Delegasi Activity Logs ----
    def log_activity(self, event_type: str, message: str, status: str = "SUCCESS") -> None:
        self.logs_repo.log(event_type, message, status)

    def list_logs(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self.logs_repo.list_recent(limit)

    # ---- Delegasi Settings ----
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self.settings_repo.get(key, default)

    def set_setting(self, key: str, value: str) -> None:
        self.settings_repo.set(key, value)

    def get_all_settings(self) -> Dict[str, str]:
        return self.settings_repo.get_all()

    # ---- Delegasi Quality Blacklist Memory ----
    def is_blacklisted(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        return self.blacklist_repo.is_blacklisted(item)

    def add_blacklist(
        self,
        item_id: str = "",
        shop_name: str = "",
        brand: str = "",
        product_type: str = "",
        keyword_signature: str = "",
        reason: str = ""
    ) -> int:
        return self.blacklist_repo.add(item_id, shop_name, brand, product_type, keyword_signature, reason)

    def list_blacklist(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.blacklist_repo.list_all(limit)

    def delete_blacklist(self, blacklist_id: int) -> None:
        self.blacklist_repo.delete(blacklist_id)

    def reject_product_quality(self, item_id: str, reason: str = "", add_blacklist: bool = True) -> None:
        """Menolak produk dan menyimpan jejak merk/tipenya ke memori daftar hitam."""
        product = self.get(item_id)
        if product and add_blacklist:
            from services.quality_inspector import QualityInspector
            brand, p_type = QualityInspector.extract_brand_and_type(
                product.get("product_name", ""),
                product.get("shop_name", "")
            )
            self.add_blacklist(
                item_id=item_id,
                shop_name=product.get("shop_name", ""),
                brand=brand,
                product_type=p_type,
                reason=reason or "Kualitas produk buruk / mengecewakan pembeli"
            )
        self.product_repo.reject(item_id, reason=reason)

    def restore_product(self, item_id: str) -> None:
        self.product_repo.approve(item_id)

    def update_rating(self, item_id: str, rating: float) -> None:
        self.product_repo.update_rating(item_id, rating)

    # ---- Delegasi Produk ----
    def exists(self, item_id: str) -> bool:
        return self.product_repo.exists(item_id)

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        return self.product_repo.get(item_id)

    def list_pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.product_repo.list_pending(limit)

    def list_all(self, status: str = "ALL", category: str = "ALL", limit: int = 100) -> List[Dict[str, Any]]:
        return self.product_repo.list_all(status, category, limit)

    def next_approved(self) -> Optional[Dict[str, Any]]:
        return self.product_repo.next_approved()

    def get_due_scheduled(self) -> Optional[Dict[str, Any]]:
        return self.product_repo.get_due_scheduled()

    def list_scheduled(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.product_repo.list_scheduled(limit)

    def update_post_type(self, item_id: str, post_type: str) -> None:
        self.product_repo.update_post_type(item_id, post_type)

    def update_schedule(self, item_id: str, scheduled_at: str) -> None:
        self.product_repo.update_schedule(item_id, scheduled_at)

    def list_comment_pending(self) -> List[Dict[str, Any]]:
        return self.product_repo.list_comment_pending()

    def count_posted_today(self) -> int:
        return self.product_repo.count_posted_today()

    def insert_product(self, item: Dict[str, Any]) -> bool:
        return self.product_repo.insert(item)

    def approve(self, item_id: str) -> None:
        self.product_repo.approve(item_id)

    def reject(self, item_id: str, reason: str = "") -> None:
        self.product_repo.reject(item_id, reason=reason)

    def delete(self, item_id: str) -> None:
        self.product_repo.delete(item_id)

    def update_caption(self, item_id: str, caption: str) -> None:
        self.product_repo.update_caption(item_id, caption)

    def update_image(self, item_id: str, image_url: str) -> None:
        self.product_repo.update_image(item_id, image_url)

    def mark_posted(self, item_id: str, post_id: str) -> None:
        self.product_repo.mark_posted_multi(item_id, fb_post_id=post_id)

    def mark_posted_multi(
        self,
        item_id: str,
        fb_post_id: Optional[str] = None,
        threads_post_id: Optional[str] = None,
        ig_post_id: Optional[str] = None
    ) -> None:
        self.product_repo.mark_posted_multi(item_id, fb_post_id, threads_post_id, ig_post_id)

    def mark_comment_done(self, item_id: str) -> None:
        self.product_repo.mark_comment_done(item_id)

    def set_error(self, item_id: str, message: str) -> None:
        self.product_repo.set_error(item_id, message)

    # ---- Metrik & Chart Data ----
    def get_metrics(self) -> Dict[str, Any]:
        conn = self._conn_factory.connect()
        try:
            cur = conn.cursor()

            cur.execute("SELECT status, COUNT(*) FROM products GROUP BY status")
            status_counts = dict(cur.fetchall())

            total = sum(status_counts.values())
            pending = status_counts.get(PENDING, 0)
            approved = status_counts.get(APPROVED, 0)
            posted = status_counts.get(POSTED, 0)
            rejected = status_counts.get(REJECTED, 0)

            cur.execute("SELECT platform, COUNT(*) FROM products GROUP BY platform")
            platform_counts = dict(cur.fetchall())

            cur.execute("SELECT category, COUNT(*) FROM products GROUP BY category")
            category_counts = dict(cur.fetchall())

            activity_by_day = []
            today_wib = datetime.now(WIB).date()
            for i in range(6, -1, -1):
                day = today_wib - timedelta(days=i)
                day_str = day.isoformat()
                day_label = day.strftime("%a (%d/%m)")

                cur.execute(
                    "SELECT COUNT(*) FROM products WHERE date(posted_at) = ?",
                    (day_str,)
                )
                count = cur.fetchone()[0]
                activity_by_day.append({"label": day_label, "count": count})

            return {
                "total": total,
                "pending": pending,
                "approved": approved,
                "posted": posted,
                "rejected": rejected,
                "posted_today": self.count_posted_today(),
                "platforms": platform_counts,
                "categories": category_counts,
                "weekly_activity": activity_by_day,
            }
        finally:
            if self.db_path != ":memory:":
                conn.close()
