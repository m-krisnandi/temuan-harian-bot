"""Smart Market-Driven Scheduler & Ranking Engine untuk Temuan Harian.
Menganalisis potensi pasar produk berdasarkan:
1. Validasi Penjualan (Sales Velocity / Social Proof: 10RB+, 1RB+)
2. Potensi Nominal Komisi (Rp per item terjual)
3. Persentase Komisi (%)
4. Diversifikasi Kategori (Category Interleaving) agar feed tidak monoton.
5. Alokasi ke Waktu Emas (Prime Time Hours: 07:30, 12:15, 17:00, 20:00 WIB).
"""
import math
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

WIB = timezone(timedelta(hours=7))

# Slot jam posting terbaik media sosial Indonesia (WIB)
PRIME_TIME_SLOTS = [
    (7, 30),   # Pagi (Commute / Cek HP Sebelum Kerja)
    (12, 15),  # Siang (Istirahat Makan Siang)
    (17, 0),   # Sore (Pulang Kantor / Santai)
    (20, 0),   # Malam (Prime Time Santai Rebahan)
]


class MarketRanker:
    """Menghitung skor prioritas pasar (Market Score) secara objektif."""

    @staticmethod
    def calculate_score(item: Dict[str, Any]) -> float:
        # 1. Komponen Penjualan (Maks 45 poin)
        sales = int(item.get("sales", 0) or 0)
        if sales >= 10000:
            sales_score = 45.0
        elif sales >= 5000:
            sales_score = 38.0
        elif sales >= 1000:
            sales_score = 30.0
        elif sales >= 100:
            sales_score = 20.0
        else:
            sales_score = max(5.0, min(15.0, sales * 0.15))

        # 2. Komponen Nominal Komisi (Maks 35 poin)
        # Produk dengan komisi Rp15.000 - Rp45.000 sangat potensial
        comm_amount = float(item.get("commission_amount", 0.0) or 0.0)
        if comm_amount >= 30000:
            comm_nominal_score = 35.0
        elif comm_amount >= 15000:
            comm_nominal_score = 28.0
        elif comm_amount >= 8000:
            comm_nominal_score = 20.0
        elif comm_amount >= 3000:
            comm_nominal_score = 12.0
        else:
            comm_nominal_score = max(2.0, min(10.0, comm_amount / 500.0))

        # 3. Komponen Persentase Komisi (Maks 20 poin)
        comm_rate = float(item.get("commission_rate", 0.0) or 0.0)
        comm_rate_score = min(20.0, comm_rate * 1.5)

        # 4. Prioritas Mutlak Media Video (Prioritaskan Video di atas Foto)
        # Produk dengan video asli seller langsung mendapatkan lonjakan skor prioritas utama
        media_type = str(item.get("media_type", "IMAGE")).upper()
        video_url = item.get("video_url", "")
        has_video = media_type == "VIDEO" or bool(video_url)
        video_priority_boost = 100.0 if has_video else 0.0

        total_score = round(sales_score + comm_nominal_score + comm_rate_score + video_priority_boost, 1)
        return total_score


class SmartScheduler:
    """Mengatur antrean postingan agar mengikuti prime time dan diversifikasi kategori."""

    @staticmethod
    def interleave_by_category(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Menyusun produk selang-seling berdasarkan kategori agar feed bervariasi."""
        if not items:
            return []

        # Kelompokkan per kategori
        by_cat: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            cat = it.get("category", "Lainnya")
            by_cat.setdefault(cat, []).append(it)

        # Urutkan tiap grup: Prioritas 1 Video Asli Seller, Prioritas 2 Skor Pasar Tertinggi
        for cat in by_cat:
            by_cat[cat].sort(
                key=lambda x: (
                    1 if (x.get("media_type") == "VIDEO" or x.get("video_url")) else 0,
                    x.get("market_score", 0.0)
                ),
                reverse=True
            )

        # Ambil round-robin bergantian antar kategori
        interleaved: List[Dict[str, Any]] = []
        cat_keys = sorted(by_cat.keys(), key=lambda c: len(by_cat[c]), reverse=True)

        max_len = max(len(v) for v in by_cat.values())
        for idx in range(max_len):
            for cat in cat_keys:
                if idx < len(by_cat[cat]):
                    interleaved.append(by_cat[cat][idx])

        return interleaved

    @classmethod
    def schedule_batch(
        cls,
        items: List[Dict[str, Any]],
        start_datetime: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Memberikan cap jadwal waktu posting (scheduled_at) ke seluruh produk."""
        if not items:
            return []

        # 1. Hitung market score jika belum ada
        for it in items:
            if "market_score" not in it or it["market_score"] == 0:
                it["market_score"] = MarketRanker.calculate_score(it)

        # 2. Kebijakan Mutlak: Prioritaskan Video di Seluruh Slot Terawal (Video-First Policy)
        # Pisahkan item video dan gambar; produk video wajib mendahului produk gambar di antrean
        video_items = [it for it in items if (it.get("media_type") == "VIDEO" or it.get("video_url"))]
        image_items = [it for it in items if not (it.get("media_type") == "VIDEO" or it.get("video_url"))]

        sorted_videos = cls.interleave_by_category(video_items)
        sorted_images = cls.interleave_by_category(image_items)
        sorted_items = sorted_videos + sorted_images

        # 3. Tentukan waktu awal (WIB)
        now_wib = datetime.now(WIB)
        current = start_datetime or now_wib

        # Cari slot terdekat berikutnya
        slot_idx = 0
        scheduled_date = current.date()

        # Cek apakah masih ada slot tersisa hari ini
        found_today = False
        for idx, (hour, minute) in enumerate(PRIME_TIME_SLOTS):
            slot_time = datetime(
                scheduled_date.year, scheduled_date.month, scheduled_date.day,
                hour, minute, tzinfo=WIB
            )
            # Beri buffer 15 menit
            if slot_time > current + timedelta(minutes=15):
                slot_idx = idx
                found_today = True
                break

        if not found_today:
            scheduled_date += timedelta(days=1)
            slot_idx = 0

        # Alokasikan tiap item ke slot waktu emas
        scheduled_items = []
        for it in sorted_items:
            hour, minute = PRIME_TIME_SLOTS[slot_idx]
            post_time = datetime(
                scheduled_date.year, scheduled_date.month, scheduled_date.day,
                hour, minute, tzinfo=WIB
            )
            it["scheduled_at"] = post_time.strftime("%Y-%m-%d %H:%M")
            it["status"] = "APPROVED"  # Siap terbit otomatis saat jamnya tiba
            scheduled_items.append(it)

            # Maju ke slot berikutnya
            slot_idx += 1
            if slot_idx >= len(PRIME_TIME_SLOTS):
                slot_idx = 0
                scheduled_date += timedelta(days=1)

        return scheduled_items
