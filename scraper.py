import time
import stat
import re, os
import shutil
import random
import zipfile
import logging
import asyncio
import platform
import tempfile
import html2text
import subprocess
import urllib.request
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC

from assets import USER_AGENTS, HEADLESS_OPTIONS

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_markdown(md_content, remove_links=False):
    """
    Clean Markdown content to remove unwanted sections, links, '!', and excess whitespace.
    """

    # # remove Comments (HTML AND md)
    md_content = re.sub(r'<!--.*?-->', '', md_content, flags=re.DOTALL)

    # Normalize newlines
    md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")

    # Remove code blocks
    md_content = re.sub(r"```[^`]*```", "", md_content, flags=re.DOTALL)
    md_content = re.sub(r"`[^`]*`", "", md_content)

    # Remove images
    md_content = re.sub(r"!\[(.*?)\]\(.*?\)", r"\1", md_content)

    # Remove headers
    # md_content = re.sub(r"^#+\s*", "", md_content, flags=re.MULTILINE)

    # Remove emphasis markers
    md_content = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", md_content)

    # Remove HTML tags
    md_content = re.sub(r"<[^>]+>", "", md_content)

    # Convert list markers to plain text
    md_content = re.sub(r"^\s*[-*+]\s+", "• ", md_content, flags=re.MULTILINE)
    md_content = re.sub(r"^\s*\d+\.\s+", "", md_content, flags=re.MULTILINE)

    # Handle blockquotes
    md_content = re.sub(r"^\s*>\s*", "", md_content, flags=re.MULTILINE)

    # Collapse multiple newlines
    md_content = re.sub(r"\n\s*\n", "\n\n", md_content)

    # Remove horizontal rules
    md_content = re.sub(r"^\s*[-*_]{3,}\s*$", "", md_content, flags=re.MULTILINE)

    if remove_links :
        # ❌ Remove links with no text: [](url)
        md_content = re.sub(r'\[\s*\]\([^\)]*\)', '', md_content)

        # ❌ Remove HTML links entirely
        md_content = re.sub(r'<a\s+[^>]*href=["\'].*?["\'][^>]*>.*?</a>', '', md_content, flags=re.DOTALL | re.IGNORECASE)

        # Remove links but keep link text
        md_content = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", md_content)
        # ✅ Replace [text](url) with just "text"
        md_content = re.sub(r'\[([^\]]+)\]\(.*?\)', r'\1', md_content)

    # Remove '!' and extra whitespaces
    md_content = re.sub(r'!', '', md_content)  # Remove '!'
    md_content = re.sub(r'\n{3,}', '\n\n', md_content)  # Limit consecutive newlines to 2
    md_content = re.sub(r'\s{2,}', ' ', md_content)  # Reduce excess spaces
    md_content = re.sub(r'(\n\s*){2,}', '\n\n', md_content)  # Remove excessive newline + spaces
    md_content = re.sub(r'\s*\n\s*', '\n', md_content)  # Remove extra spaces around newlines

    return md_content.strip() + "\n"


CHROMIUM_URL = "https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1169/chromium-linux.zip"
CHROMIUM_ZIP = "chromium-linux.zip"
CHROME_DIR = "chrome-linux"
CHROME_BINARY = os.path.join(CHROME_DIR, "chrome")

def download_chromium():
    if not os.path.exists(CHROME_DIR):
        logger.info("Downloading Chromium...")
        urllib.request.urlretrieve(CHROMIUM_URL, CHROMIUM_ZIP)

        with zipfile.ZipFile(CHROMIUM_ZIP, 'r') as zip_ref:
            zip_ref.extractall("chromium-temp")

        # Move the chrome-linux folder to current directory
        shutil.move("chromium-temp/chrome-linux", CHROME_DIR)
        shutil.rmtree("chromium-temp")
        os.remove(CHROMIUM_ZIP)

        # ✅ Add executable permission to the chrome binary
        chrome_binary_path = os.path.join(CHROME_DIR, "chrome")
        os.chmod(chrome_binary_path, os.stat(chrome_binary_path).st_mode | stat.S_IXUSR)

        logger.info("Chromium downloaded and extracted.")
    else:
        logger.info("Chromium already available.")


def get_chrome_version_linux():
    try:
        result = subprocess.run([f"./{CHROME_DIR}/chrome", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode().strip()
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
        if match:
            return match.group(1)
        else:
            logger.warning("Could not parse Chromium version.")
            return None
    except Exception as e:
        logger.error(f"Error getting Chromium version: {e}")
        return None


def setup_selenium():
    options = Options()

    # Set random user-agent
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={user_agent}")

    # Add headless and other options
    for option in HEADLESS_OPTIONS:
        options.add_argument(option)

    # Create a unique temporary user data directory
    user_data_dir = tempfile.mkdtemp()
    logger.info(f"Using unique user data dir: {user_data_dir}")
    options.add_argument(f"--user-data-dir={user_data_dir}")

    # Chrome binary path for Linux
    if platform.system() == "Linux":
        download_chromium()
        options.binary_location = f"./{CHROME_DIR}/chrome"
        chrome_version = get_chrome_version_linux()
        logger.info(f"Chromium version: {chrome_version}")
        if chrome_version :
            driver_path = ChromeDriverManager(driver_version=chrome_version).install()
        else :
            driver_path = ChromeDriverManager().install()

    # Chrome path on Windows (use default or custom install path if needed)
    elif platform.system() == "Windows":
        chrome_default_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        if os.path.exists(chrome_default_path):
            options.binary_location = chrome_default_path
        else:
            logger.warning("Chrome binary not found, using system default.")
        # Get compatible driver version
        driver_path = ChromeDriverManager().install()
        
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def scroll_page(driver, delay=2, repeat=2):
    """Scroll down the page slowly to simulate human behavior"""
    for _ in range(repeat):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(delay)


def click_accept_cookies(driver):
    """Attempt to click common cookie buttons if found"""
    try:
        buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'agree') or contains(text(), 'OK')]")
        if buttons:
            buttons[0].click()
            logger.info("✅ Accepted cookies.")
    except Exception as e:
        logger.warning(f"⚠ Failed to click cookie button: {e}")


def fetch_html_selenium(url, timeout=60):
    driver = setup_selenium()
    try:
        logger.info(f"🔗 Fetching: {url}")
        driver.get(url)
        driver.maximize_window()

        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        click_accept_cookies(driver)
        scroll_page(driver)

        html = driver.page_source
        return html

    except Exception as e:
        logger.error(f"❌ Error fetching page: {e}")
        return None

    finally:
        driver.quit()


def clean_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    # Extract page title and page body
    title = soup.title.string if soup.title else "No Title"
    body = soup.body

    # Remove irrelevant tags
    for tag in body(["script", "style", "iframe", "nav", "footer", "header"]):
        tag.decompose()

    return title, body

def to_markdown(title, body_html) :
    # Convert to markdown
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_content = markdown_converter.handle(str(body_html))

    # markdown_content =  html2text.html2text(str(body))
    markdown_content = f"## Page Title : {title}\n\n ## Content : \n {markdown_content}"

    return clean_markdown(markdown_content)

def selenium_scraper(url):
    html_content = fetch_html_selenium(url)
    title, cleaned_body = clean_html(html_content)
    # print(cleaned_body)
    cleaned_md = to_markdown(title, cleaned_body)
    return cleaned_md

# ------

async def get_markdown_async(url, timeout=120, raw=False):
    """
    Scrape the content of the webpage using Crawl4AI.
    """
    try:
        async with AsyncWebCrawler() as crawler:
            result = await asyncio.wait_for(crawler.arun(url=url), timeout=timeout)

        if result.success:
            return result.markdown if raw else clean_markdown(result.markdown)
        else:
            return ""

    except asyncio.TimeoutError:
        logger.error(f"Crawl4AI timeout after {timeout}s on {url}")
        return "Error: Crawl4AI timed out."
    except Exception as e:
        logger.error(f"Error using Crawl4AI on {url}: {e}")
        return "Error: Unable to Crawl Using Crawl4AI."

def crawl4ai_scraper(url: str, raw=False) -> str:
    """
    Synchronous wrapper around get_markdown_async().
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(get_markdown_async(url, raw=raw))
    finally:
        loop.close()

def get_url_md(url, method="Selenium"):
    """
    Scrape a website using the specified method.
    Falls back to Selenium if Crawl4AI fails.
    """
    if method == "Selenium":
        return selenium_scraper(url)
    elif method == "Crawl4AI":
        result = crawl4ai_scraper(url)
        if not result or result.startswith("Error"):
            logger.warning(f"Crawl4AI failed for {url}, falling back to Selenium...")
            return selenium_scraper(url)
        return result
    else:
        raise ValueError('scraping method not exist, plz select "Selenium" or "Crawl4AI".')


class SeleniumSession:
    """Reusable Selenium session for multi-page scraping."""

    def __init__(self):
        self.driver = None

    def __enter__(self):
        self.driver = setup_selenium()
        return self

    def __exit__(self, *args):
        if self.driver:
            self.driver.quit()

    def fetch_page(self, url, timeout=60):
        self.driver.get(url)
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        click_accept_cookies(self.driver)
        scroll_page(self.driver)
        return self.driver.page_source

    def scrape_to_markdown(self, url):
        html = self.fetch_page(url)
        title, body = clean_html(html)
        return to_markdown(title, body), html


if __name__ == "__main__":
    # example_url = "https://drisskhattabi6.github.io/id-kh"
    example_url = "https://scrapeme.live/shop/"
    # example_url = "https://pypi.org/search/?q=genai"

    # print("Selenium Scraping:")
    # print(get_url_md(example_url, method="Selenium"))

    print("Crawl4AI Scraping:")
    # print(get_url_md(example_url, method="Crawl4AI"))
    print(crawl4ai_scraper(example_url))
