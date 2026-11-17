"""Dependency Injection Container & Factory (DIP - Dependency Inversion Principle).
Menyediakan instansiasi objek dan injeksi ketergantungan untuk Web Controller (FastAPI) dan CLI Pipeline.
"""
import os
from pathlib import Path
from typing import Optional, List

from core.interfaces import (
    ISocialPublisher,
    ICaptionGenerator,
    IProductScraper,
    IAdsManager,
)
from repositories.database import ProductQueueDB
from publishers.facebook import FacebookPagePublisher
from publishers.threads import ThreadsPublisher
from publishers.instagram import InstagramPublisher
from publishers.dispatcher import PublisherDispatcher
from services.captions import (
    TemplateCaptionGenerator,
    GeminiCaptionGenerator,
    CompositeCaptionGenerator,
)
from services.shopee_scraper import ShopeePublicScraper
from publishers.meta_ads import MetaAdsManager

BASE_DIR = Path(__file__).resolve().parent.parent


def get_db(db_path: Optional[str] = None) -> ProductQueueDB:
    """Factory Dependency Injection: Database & Repositories."""
    default_db = str(BASE_DIR / "temuan_harian.db")
    path = db_path or os.getenv("TEMUAN_DB", default_db)
    return ProductQueueDB(path)


def get_caption_generator(db: Optional[ProductQueueDB] = None, use_ai: bool = True) -> ICaptionGenerator:
    """Factory Dependency Injection: Caption Engine (Strategy / Composite)."""
    template_gen = TemplateCaptionGenerator()
    if not use_ai:
        return template_gen

    db_instance = db or get_db()
    gemini_key = db_instance.get_setting("gemini_api_key") or os.getenv("GEMINI_API_KEY")
    gemini_model = db_instance.get_setting("gemini_model") or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    gemini_gen = GeminiCaptionGenerator(api_key=gemini_key, model=gemini_model)
    return CompositeCaptionGenerator(primary=gemini_gen, fallback=template_gen)


def get_product_scraper() -> IProductScraper:
    """Factory Dependency Injection: Product Scraper."""
    return ShopeePublicScraper()


def get_publisher_dispatcher(db: Optional[ProductQueueDB] = None) -> PublisherDispatcher:
    """Factory Dependency Injection: Publisher Dispatcher dengan seluruh channel aktif."""
    db_instance = db or get_db()
    settings = db_instance.get_all_settings()

    publishers: List[ISocialPublisher] = []

    # 1. Facebook Page Channel
    if settings.get("channel_fb_enabled", "1") == "1":
        fb_page_id = settings.get("fb_page_id") or os.getenv("FB_PAGE_ID", "")
        fb_page_token = settings.get("fb_page_access_token") or os.getenv("FB_PAGE_ACCESS_TOKEN", "")
        if fb_page_id and fb_page_token:
            try:
                publishers.append(FacebookPagePublisher(page_id=fb_page_id, access_token=fb_page_token))
            except Exception:
                pass

    # 2. Threads Channel
    if settings.get("channel_threads_enabled", "0") == "1":
        threads_uid = settings.get("threads_user_id") or os.getenv("THREADS_USER_ID", "")
        threads_tok = settings.get("threads_access_token") or os.getenv("THREADS_ACCESS_TOKEN", "")
        if threads_uid and threads_tok:
            try:
                publishers.append(ThreadsPublisher(user_id=threads_uid, access_token=threads_tok))
            except Exception:
                pass

    # 3. Instagram Channel
    if settings.get("channel_ig_enabled", "0") == "1":
        ig_uid = settings.get("ig_user_id") or os.getenv("IG_USER_ID", "")
        ig_tok = settings.get("ig_access_token") or os.getenv("IG_ACCESS_TOKEN", "")
        if ig_uid and ig_tok:
            try:
                publishers.append(InstagramPublisher(ig_user_id=ig_uid, access_token=ig_tok))
            except Exception:
                pass

    return PublisherDispatcher(publishers=publishers)


def get_ads_manager(db: Optional[ProductQueueDB] = None) -> Optional[IAdsManager]:
    """Factory Dependency Injection: Meta Ads Manager."""
    db_instance = db or get_db()
    ad_account_id = db_instance.get_setting("meta_ad_account_id") or os.getenv("META_AD_ACCOUNT_ID", "")
    ad_token = db_instance.get_setting("meta_ad_access_token") or os.getenv("META_AD_ACCESS_TOKEN", "")

    if ad_account_id and ad_token:
        try:
            return MetaAdsManager(ad_account_id=ad_account_id, access_token=ad_token)
        except Exception:
            return None
    return None
