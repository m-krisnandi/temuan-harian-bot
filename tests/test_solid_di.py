"""Suite Pengujian Unit & Integrasi Arsitektur SOLID & Dependency Injection."""
import unittest
from core.interfaces import ISocialPublisher, ICaptionGenerator, IProductScraper
from core.dependencies import (
    get_db,
    get_caption_generator,
    get_product_scraper,
    get_publisher_dispatcher,
)
from publishers.dispatcher import PublisherDispatcher


class MockPublisher(ISocialPublisher):
    def __init__(self, name: str):
        self._name = name
        self.published = []
        self.comments = []

    @property
    def platform_name(self) -> str:
        return self._name

    def publish_photo(self, image_url: str, caption: str) -> str:
        self.published.append((image_url, caption))
        return f"{self._name}_id_123"

    def add_comment(self, post_id: str, comment_text: str) -> str:
        self.comments.append((post_id, comment_text))
        return f"comment_{post_id}"


class TestSolidArchitecture(unittest.TestCase):
    def setUp(self):
        self.db = get_db(":memory:")

    def test_single_responsibility_repositories(self):
        """Memastikan database terbagi dalam repository terisolasi."""
        self.assertIsNotNone(self.db.product_repo)
        self.assertIsNotNone(self.db.settings_repo)
        self.assertIsNotNone(self.db.logs_repo)

        # Uji Settings
        self.db.set_setting("test_key", "test_val")
        self.assertEqual(self.db.get_setting("test_key"), "test_val")

        # Uji Activity Log
        self.db.log_activity("TEST_EVENT", "Pesan uji aktivitas", status="SUCCESS")
        logs = self.db.list_logs(limit=1)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["event_type"], "TEST_EVENT")

    def test_caption_generator_strategy_composite(self):
        """Memastikan caption generator mematuhi Strategy Pattern & ICaptionGenerator."""
        gen = get_caption_generator(db=self.db, use_ai=False)
        self.assertIsInstance(gen, ICaptionGenerator)

        item = {
            "item_id": "test_item_1",
            "product_name": "Teko Listrik Otomatis 1.5L",
            "price": 89000,
            "category": "Elektronik",
            "rating": 4.9,
            "sales": 540,
        }
        caption = gen.generate(item)
        self.assertIn("Teko Listrik Otomatis", caption)
        self.assertIn("Elektronik", caption)

    def test_product_scraper_interface(self):
        """Memastikan scraper mengimplementasikan IProductScraper."""
        scraper = get_product_scraper()
        self.assertIsInstance(scraper, IProductScraper)

    def test_publisher_dispatcher_liskov_and_dip(self):
        """Memastikan PublisherDispatcher bekerja dengan implementasi ISocialPublisher apapun via DI."""
        mock_fb = MockPublisher("Facebook Page")
        mock_threads = MockPublisher("Threads")

        dispatcher = PublisherDispatcher(publishers=[mock_fb, mock_threads])
        result = dispatcher.dispatch(
            image_url="https://example.com/test.jpg",
            caption="Caption Uji Coba",
            comment_text="Link: https://s.shopee.co.id/xxx",
        )

        self.assertTrue(result.is_success)
        self.assertIn("Facebook Page", result.successful_channels)
        self.assertIn("Threads", result.successful_channels)
        self.assertEqual(len(mock_fb.published), 1)
        self.assertEqual(len(mock_threads.published), 1)
        self.assertEqual(len(mock_fb.comments), 1)
        self.assertEqual(len(mock_threads.comments), 1)


if __name__ == "__main__":
    unittest.main()
