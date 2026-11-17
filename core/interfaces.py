"""Definisi Interface dan Abstraksi untuk Arsitektur SOLID.
Memastikan Dependency Inversion Principle (DIP) dan Interface Segregation Principle (ISP).
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class ISocialPublisher(ABC):
    """Interface untuk Social Media Publisher (Open/Closed & Liskov Substitution)."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Nama platform sosial (misal: 'Facebook Page', 'Threads', 'Instagram')."""
        pass

    @abstractmethod
    def publish_photo(self, image_url: str, caption: str) -> str:
        """Membuat postingan foto + teks. Mengembalikan post_id."""
        pass

    @abstractmethod
    def add_comment(self, post_id: str, comment_text: str) -> str:
        """Menambahkan komentar pertama (untuk link afiliasi). Mengembalikan comment_id."""
        pass


class ICaptionGenerator(ABC):
    """Interface untuk Generator Caption (Open/Closed)."""

    @abstractmethod
    def generate(self, item: Dict[str, Any]) -> str:
        """Menghasilkan caption untuk produk."""
        pass


class IProductScraper(ABC):
    """Interface untuk Ekstraksi Data Produk (Single Responsibility)."""

    @abstractmethod
    def scrape_preview(self, url: str) -> Dict[str, Any]:
        """Mengekstrak metadata publik (judul, foto resmi, harga, kategori)."""
        pass


class IProductRepository(ABC):
    """Interface Repository Produk (Single Responsibility & Interface Segregation)."""

    @abstractmethod
    def exists(self, item_id: str) -> bool:
        pass

    @abstractmethod
    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def insert(self, item: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def approve(self, item_id: str) -> None:
        pass

    @abstractmethod
    def reject(self, item_id: str, reason: str = "") -> None:
        pass

    @abstractmethod
    def delete(self, item_id: str) -> None:
        pass

    @abstractmethod
    def update_rating(self, item_id: str, rating: float) -> None:
        pass

    @abstractmethod
    def list_pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def next_approved(self) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def count_posted_today(self) -> int:
        pass

    @abstractmethod
    def update_schedule(self, item_id: str, scheduled_at: str) -> None:
        pass

    @abstractmethod
    def list_scheduled(self, limit: int = 50) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_due_scheduled(self) -> Optional[Dict[str, Any]]:
        pass


class ISettingsRepository(ABC):
    """Interface Repository Pengaturan Sistem."""

    @abstractmethod
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        pass

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        pass

    @abstractmethod
    def get_all(self) -> Dict[str, str]:
        pass


class IActivityLogRepository(ABC):
    """Interface Repository Audit Log Aktivitas."""

    @abstractmethod
    def log(self, event_type: str, message: str, status: str = "SUCCESS") -> None:
        pass

    @abstractmethod
    def list_recent(self, limit: int = 30) -> List[Dict[str, Any]]:
        pass


class IAdsManager(ABC):
    """Interface Manajemen Iklan Meta Marketing API."""

    @abstractmethod
    def get_account_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def create_traffic_campaign(self, name: str, daily_budget_idr: int = 50000) -> str:
        pass
