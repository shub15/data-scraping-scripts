"""
MDComputers Product Scraper
============================
Scrapes product details from MDComputers (https://mdcomputers.in) for a given
search term, handling pagination automatically, and exports results to CSV
and/or JSON.

Usage:
    python mdcomputers_scraper.py "external harddrive"
    python mdcomputers_scraper.py "rtx 4090" --format json
    python mdcomputers_scraper.py "ssd" --format both --output results
    python mdcomputers_scraper.py "ram" --max-pages 2

Requirements:
    pip install requests beautifulsoup4 lxml
"""

import argparse
import csv
import json
import logging
import random
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mdcomputers_scraper")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://mdcomputers.in/"
SEARCH_ROUTE = "?route=product/search&search={query}&page={page}"

# Realistic browser headers to reduce bot-detection chance
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://mdcomputers.in/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Polite delay range (seconds) between page requests
MIN_DELAY = 1.5
MAX_DELAY = 3.5


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Product:
    name: str                        # Full product name
    url: str                         # Direct product page URL
    image_url: str                   # Main product image URL
    original_price: Optional[str]   # MRP / crossed-out price (None if not shown)
    sale_price: Optional[str]        # Current selling price
    discount_pct: Optional[str]      # Discount badge text e.g. "-35%"
    availability: str                # "In Stock" | "Out of Stock"
    has_flash_deal: bool             # True when a countdown timer is present
    product_id: Optional[str]        # Internal product ID (from cart.add call)
    extra: dict = field(default_factory=dict)  # Future-proof bucket


# ---------------------------------------------------------------------------
# Scraper helpers
# ---------------------------------------------------------------------------

def build_url(query: str, page: int = 1) -> str:
    """Return the full search URL for a given query and page number."""
    encoded = quote_plus(query)
    return BASE_URL + SEARCH_ROUTE.format(query=encoded, page=page)


def fetch_page(session: requests.Session, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    """
    Fetch a URL with retry logic.
    Returns a BeautifulSoup object or None on failure.
    """
    for attempt in range(1, retries + 1):
        try:
            log.debug("GET %s (attempt %d)", url, attempt)
            resp = session.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.exceptions.HTTPError as exc:
            log.warning("HTTP %s for %s", exc.response.status_code, url)
            if exc.response.status_code in (403, 429):
                wait = 10 * attempt
                log.warning("Rate-limited / blocked. Waiting %ds before retry.", wait)
                time.sleep(wait)
            else:
                break
        except requests.exceptions.RequestException as exc:
            log.warning("Request error: %s", exc)
            time.sleep(3 * attempt)
    return None


def clean_price(text: str) -> str:
    """Normalize a price string: collapse whitespace and handle encoding."""
    # The site uses Unicode rupee sign ₹ (U+20B9), sometimes mangled in terminal
    cleaned = " ".join(text.split())
    # Normalise to Rs. prefix for safe ASCII output
    cleaned = cleaned.replace("\u20b9", "Rs.")
    return cleaned.strip()


def clean_text(text: str) -> str:
    """Collapse whitespace in a string."""
    return " ".join(text.split())


def extract_products(soup: BeautifulSoup) -> list:
    """
    Parse all product cards from a search-results page soup.

    MDComputers HTML structure (confirmed from live page):

        <div class="product-grid-item product-hover-icons product-with-labels ...">
          <div class="product-wrapper">
            <div class="product-element-top product-quick-shop">
              <a class="product-image-link" href="https://mdcomputers.in/product/...">
                <div class="product-labels labels-rectangular">
                  <span class="onsale product-label">-58%</span>   <- discount badge
                </div>
                <img src="..." alt="Product Name" />
              </a>
              <!-- action buttons: Add to Cart, Quick View, Compare, Wishlist -->
              <div class="wrapp-buttons">
                <div class="product-buttons">
                  <div class="product-add-btn ...">
                    <button class="... add-to-cart-loop"
                            onclick="...cart.add('15127');">
                      <span>Add to Cart</span>   <- or "Out of Stock" text
                    </button>
                  </div>
                  ...
                </div>
              </div>
            </div>
            <h3 class="product-entities-title">
              <a href="https://mdcomputers.in/product/...">Product Name</a>
            </h3>
            <span class="price">
              <span class="del">                   <- original / crossed-out price
                <span class="amount"><span>Rs.1,299</span></span>
              </span>
              <span class="ins">                   <- current / sale price
                <span class="amount">Rs.550 <span></span></span>
              </span>
            </span>
            <!-- optional: countdown timer for flash deals -->
            <div class="product-timer">...</div>
          </div>
        </div>
    """
    products = []
    cards = soup.select("div.product-grid-item")

    if not cards:
        log.debug("Fallback: trying div.product-wrapper as top-level cards")
        cards = soup.select("div.product-wrapper")

    for card in cards:
        try:
            # ── Image & product URL ─────────────────────────────────────────
            img_anchor = card.select_one("a.product-image-link")
            product_url = img_anchor.get("href", "").strip() if img_anchor else ""
            img_tag = img_anchor.select_one("img") if img_anchor else None
            image_url = img_tag.get("src", "").strip() if img_tag else ""

            # ── Discount badge ──────────────────────────────────────────────
            # <span class="onsale product-label">-35%</span>
            discount_pct: Optional[str] = None
            badge = card.select_one("span.onsale.product-label, span.product-label")
            if badge:
                txt = badge.get_text(strip=True)
                if txt:
                    discount_pct = txt  # e.g. "-35%" or "Sale" or "-58%"

            # ── Product name ────────────────────────────────────────────────
            # <h3 class="product-entities-title"><a href="...">Name</a></h3>
            name = ""
            title_tag = card.select_one("h3.product-entities-title a")
            if title_tag:
                name = clean_text(title_tag.get_text())
                if not product_url and title_tag.get("href"):
                    product_url = title_tag["href"]

            # ── Prices ──────────────────────────────────────────────────────
            # Original (crossed-out): <span class="del"><span class="amount">…</span></span>
            # Sale price:             <span class="ins"><span class="amount">…</span></span>
            original_price: Optional[str] = None
            sale_price: Optional[str] = None

            del_span = card.select_one("span.del span.amount")
            ins_span = card.select_one("span.ins span.amount")

            if del_span:
                original_price = clean_price(del_span.get_text())
            if ins_span:
                # The ins span sometimes has a nested empty <span>; get_text strips it
                sale_price = clean_price(ins_span.get_text())

            # Fallback: single price with no del/ins wrappers
            if not sale_price and not original_price:
                price_span = card.select_one("span.price")
                if price_span:
                    raw = price_span.get_text(separator=" ")
                    # Look for currency patterns
                    prices = re.findall(r"(?:Rs\.|₹|\u20b9)\s*[\d,]+", raw)
                    if len(prices) >= 2:
                        original_price = clean_price(prices[0])
                        sale_price = clean_price(prices[-1])
                    elif len(prices) == 1:
                        sale_price = clean_price(prices[0])

            # ── Stock status ────────────────────────────────────────────────
            # "Add to Cart" button exists for in-stock items;
            # out-of-stock items show different text or a disabled button.
            availability = "In Stock"
            add_btn = card.select_one("button.add-to-cart-loop")
            if add_btn:
                btn_text = add_btn.get_text(strip=True).lower()
                if "out of stock" in btn_text or "sold out" in btn_text or "unavailable" in btn_text:
                    availability = "Out of Stock"
            else:
                # No add-to-cart button at all often means out of stock
                # But only flag if there's also no price
                if not sale_price and not original_price:
                    availability = "Out of Stock"

            # Also check for a "sold-out" label in product-labels
            sold_label = card.select_one("span.sold-out, span.outofstock")
            if sold_label:
                availability = "Out of Stock"

            # ── Flash deal / countdown timer ────────────────────────────────
            has_flash_deal = bool(
                card.select_one(
                    "div.product-timer, div.product-product-countdown, "
                    "div.count-down, .countdown"
                )
            )

            # ── Internal product ID ─────────────────────────────────────────
            # Extracted from onclick: cart.add('15127')
            product_id: Optional[str] = None
            if add_btn:
                onclick = add_btn.get("onclick", "")
                m = re.search(r"cart\.add\(['\"](\d+)['\"]", onclick)
                if m:
                    product_id = m.group(1)

            products.append(
                Product(
                    name=name,
                    url=product_url,
                    image_url=image_url,
                    original_price=original_price,
                    sale_price=sale_price,
                    discount_pct=discount_pct,
                    availability=availability,
                    has_flash_deal=has_flash_deal,
                    product_id=product_id,
                )
            )
        except Exception as exc:
            log.warning("Skipped a card due to parse error: %s", exc)

    return products


def get_total_pages(soup: BeautifulSoup) -> int:
    """
    Detect total number of result pages.

    MDComputers uses Bootstrap pagination:
      <ul class="pagination"> ... <li><a href="...&page=3">3</a></li> ... </ul>
    Also checks a result-count text like "Showing 1 to 20 of 45 (3 Pages)".
    """
    # Method 1: result summary text  "Showing 1 to 20 of 45 (3 Pages)"
    for el in soup.find_all(string=re.compile(r"\(\d+\s+[Pp]age")):
        m = re.search(r"\((\d+)\s+[Pp]age", el)
        if m:
            return int(m.group(1))

    # Method 2: highest page number in pagination links
    pages = set()
    for a in soup.select("ul.pagination li a"):
        href = a.get("href", "")
        m = re.search(r"[&?]page=(\d+)", href)
        if m:
            pages.add(int(m.group(1)))
    if pages:
        return max(pages)

    # Method 3: check if next-page button is present
    next_btn = soup.select_one("ul.pagination li.active + li a")
    if next_btn:
        return 99  # Unknown total; keep paginating

    return 1  # Default: single page


def scrape(query: str, max_pages: Optional[int] = None) -> list:
    """
    Scrape all products for *query* across all result pages.

    Args:
        query:     The search term.
        max_pages: Maximum number of pages to scrape (None = all).

    Returns:
        A list of Product dataclass instances.
    """
    session = requests.Session()
    all_products: list = []
    page = 1
    effective_max = max_pages or 9999  # will be capped after first page detection

    while True:
        url = build_url(query, page)
        log.info("Scraping page %d -> %s", page, url)

        soup = fetch_page(session, url)
        if soup is None:
            log.error("Failed to fetch page %d. Stopping.", page)
            break

        # On the first page, detect total pages
        if page == 1:
            total_pages = get_total_pages(soup)
            if max_pages is not None:
                effective_max = min(max_pages, total_pages)
            else:
                effective_max = total_pages
            log.info(
                "Total pages detected: %d  |  Will scrape: %d",
                total_pages,
                effective_max,
            )

        products = extract_products(soup)

        if not products:
            log.info("No products found on page %d. Stopping.", page)
            break

        log.info("  Found %d product(s) on page %d.", len(products), page)
        all_products.extend(products)

        if page >= effective_max:
            break

        page += 1
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        log.debug("Sleeping %.1fs before next page...", delay)
        time.sleep(delay)

    log.info("Scraping complete. Total products collected: %d", len(all_products))
    return all_products


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "name",
    "url",
    "image_url",
    "original_price",
    "sale_price",
    "discount_pct",
    "availability",
    "has_flash_deal",
    "product_id",
]


def export_csv(products: list, filepath: Path) -> None:
    """Write products to a UTF-8 CSV file."""
    with filepath.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for p in products:
            writer.writerow(asdict(p))
    log.info("CSV saved -> %s", filepath.resolve())


def export_json(products: list, filepath: Path) -> None:
    """Write products to a pretty-printed JSON file."""
    data = [asdict(p) for p in products]
    with filepath.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    log.info("JSON saved -> %s", filepath.resolve())


def print_summary(products: list) -> None:
    """Print a terminal summary table (ASCII-safe)."""
    if not products:
        print("\nNo products found.")
        return

    col_name  = 52
    col_price = 14
    col_avail = 14

    header = (
        f"{'#':>3}  "
        f"{'Product Name':<{col_name}}  "
        f"{'Sale Price':>{col_price}}  "
        f"{'Discount':>8}  "
        f"{'Availability':<{col_avail}}"
    )
    sep = "-" * len(header)

    print(f"\n{'='*len(header)}")
    print(f"  Search Results  ({len(products)} products)")
    print(f"{'='*len(header)}")
    print(header)
    print(sep)

    for i, p in enumerate(products, 1):
        name_trunc = (
            (p.name[:col_name - 3] + "...") if len(p.name) > col_name else p.name
        )
        # Normalize price for terminal output (replace rupee symbol)
        price = (p.sale_price or p.original_price or "N/A")
        price = price.replace("\u20b9", "Rs.").encode("ascii", "replace").decode()

        disc  = p.discount_pct or "--"
        avail = p.availability
        print(
            f"{i:>3}.  "
            f"{name_trunc:<{col_name}}  "
            f"{price:>{col_price}}  "
            f"{disc:>8}  "
            f"{avail:<{col_avail}}"
        )

    print(sep)
    in_stock = sum(1 for p in products if p.availability == "In Stock")
    print(f"  In Stock: {in_stock}   |   Out of Stock: {len(products) - in_stock}")
    print(f"{'='*len(header)}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Scrape product listings from MDComputers for a search term.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "query",
        help='Product search term, e.g. "external harddrive" or "rtx 4090"',
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json", "both"],
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Base filename for output (without extension). "
            "Defaults to a sanitised version of the query."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of pages to scrape (default: all).",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Do not save any output files; only print to terminal.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    log.info("Search query : %r", args.query)
    log.info("Max pages    : %s", args.max_pages or "all")
    log.info("Output format: %s", args.format)

    products = scrape(args.query, max_pages=args.max_pages)
    print_summary(products)

    if not products:
        log.warning("No products scraped. Exiting without writing files.")
        return

    if args.no_export:
        return

    # Determine output base path
    if args.output:
        base = Path(args.output)
    else:
        safe = re.sub(r"[^\w\-]", "_", args.query.lower().strip())
        safe = re.sub(r"_+", "_", safe).strip("_")
        base = Path(safe)

    if args.format in ("csv", "both"):
        export_csv(products, base.with_suffix(".csv"))
    if args.format in ("json", "both"):
        export_json(products, base.with_suffix(".json"))


if __name__ == "__main__":
    main()
