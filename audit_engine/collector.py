"""Phase 1 data collector.

This is the seam that Phase 2 will replace with a real crawler (fetch HTML,
headers, robots.txt, sitemap, DNS records, etc). For now it returns a
deterministic "site profile" derived from the URL so the same URL always
produces the same demo audit, and downstream code (checks.py) has no idea
whether the data came from a live crawl or this stub.
"""
import hashlib
from urllib.parse import urlparse


def collect(url: str) -> dict:
    """Return a deterministic site profile for the given URL.

    Phase 2 replaces the body of this function with a real crawl. The
    returned shape (domain, seed, guessed_topics) should stay stable so
    checks.py doesn't need to change.
    """
    parsed = urlparse(url if "://" in url else f"https://{url}")
    domain = parsed.netloc or parsed.path
    seed = int(hashlib.md5(domain.lower().encode()).hexdigest(), 16) % (2**32)

    # crude topic guess from the domain name (Phase 2: derive from real page content)
    slug = domain.split(".")[0].replace("-", " ")
    guessed_topics = [w for w in slug.split() if len(w) > 2][:3] or ["services"]

    return {
        "url": url,
        "domain": domain,
        "seed": seed,
        "guessed_topics": guessed_topics,
        "is_demo_data": True,
        "data_source": "sample_data",
    }
