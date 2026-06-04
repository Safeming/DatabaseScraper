import unittest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import scraper


class SeleniumBrowserSetupTests(unittest.TestCase):
    @patch("scraper.platform.system", return_value="Windows")
    @patch("scraper.os.path.exists")
    @patch("scraper.webdriver.Chrome")
    @patch("scraper.webdriver.Edge")
    @patch("scraper.ChromeDriverManager")
    def test_windows_uses_edge_when_chrome_is_not_installed(
        self,
        chrome_driver_manager,
        edge_webdriver,
        chrome_webdriver,
        path_exists,
        _platform_system,
    ):
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

        def fake_exists(path):
            return path == edge_path

        path_exists.side_effect = fake_exists
        edge_webdriver.return_value = MagicMock()

        scraper.setup_selenium()

        chrome_driver_manager.assert_not_called()
        chrome_webdriver.assert_not_called()
        edge_webdriver.assert_called_once()
        options = edge_webdriver.call_args.kwargs["options"]
        self.assertEqual(options.binary_location, edge_path)

    @patch("scraper.fetch_html_selenium", return_value=None)
    def test_selenium_scraper_returns_error_when_fetch_fails(self, _fetch_html):
        result = scraper.selenium_scraper("https://example.com")

        self.assertTrue(result.startswith("Error:"))
        self.assertIn("Selenium failed", result)

    @patch("scraper.CrawlerRunConfig")
    @patch("scraper.BrowserConfig")
    @patch("scraper.AsyncWebCrawler")
    def test_crawl4ai_runs_without_verbose_console_output(
        self,
        async_web_crawler,
        browser_config,
        crawler_run_config,
    ):
        result = MagicMock(success=True, markdown="hello")
        crawler = async_web_crawler.return_value
        crawler.__aenter__.return_value = crawler
        crawler.arun = AsyncMock(return_value=result)

        markdown = asyncio.run(scraper.get_markdown_async("https://example.com"))

        self.assertEqual(markdown, "hello\n")
        browser_config.assert_called_once_with(verbose=False)
        crawler_run_config.assert_called_once_with(verbose=False)
        crawler.arun.assert_called_once_with(
            url="https://example.com",
            config=crawler_run_config.return_value,
        )


if __name__ == "__main__":
    unittest.main()
