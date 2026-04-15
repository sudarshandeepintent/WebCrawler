from __future__ import annotations

import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from crawler.domain.fetch_result import FetchResult
from crawler.models.schemas import ImageInfo, LinkInfo, PageMetadata

# tags whose text content I don't want in the body_text output.
# nav/header/footer usually just have menu items and copyright lines,
# not actual page content. script/style are obvious noise.
_SKIP = {"script", "style", "noscript", "head", "meta", "link", "header", "footer", "nav", "aside"}


def _text(tag: Optional[Tag]) -> Optional[str]:
    if tag is None:
        return None
    t = tag.get_text(separator=" ", strip=True)
    return t or None


def _meta(soup: BeautifulSoup, **attrs) -> Optional[str]:
    # generic meta tag reader — pass any attribute combo, e.g. name="description"
    # or property="og:title". tries content first, then value as a fallback.
    tag = soup.find("meta", attrs=attrs)
    if tag and isinstance(tag, Tag):
        return tag.get("content", None) or tag.get("value", None)  # type: ignore[return-value]
    return None


def _squash_ws(s: str) -> str:
    # collapse multiple whitespace/newlines into a single space.
    # html dumps a lot of extra whitespace that messes with word counts.
    return re.sub(r"\s+", " ", s).strip()


def parse_page(fetch_result: FetchResult) -> PageMetadata:
    """Parse raw HTML from a FetchResult into a PageMetadata object.

    Extracts: title, standard meta tags, Open Graph, Twitter Card, headings
    (h1–h6), deduplicated links with external flag, images (src + alt),
    and cleaned body text with word count.

    Body text skips script/style/nav/header/footer nodes so the output is
    suitable for topic classification without menu/footer noise.
    """
    soup = BeautifulSoup(fetch_result.html, "lxml")
    base = fetch_result.final_url  # use final_url so relative links resolve correctly after redirects
    base_host = urlparse(base).netloc

    title = _text(soup.find("title"))

    # try both name= and property= for description — some sites use property instead of name
    description = _meta(soup, name="description") or _meta(soup, property="description")
    keywords = _meta(soup, name="keywords")
    author = _meta(soup, name="author")
    robots = _meta(soup, name="robots")

    canonical = None
    can_link = soup.find("link", rel="canonical")
    if can_link and isinstance(can_link, Tag):
        canonical = can_link.get("href")  # type: ignore[assignment]

    # language is usually on the <html lang="en"> attribute.
    # falling back to the http-equiv meta tag as a backup.
    language = None
    html_el = soup.find("html")
    if html_el and isinstance(html_el, Tag):
        language = html_el.get("lang") or _meta(soup, **{"http-equiv": "content-language"})  # type: ignore[assignment]

    # charset can be in two places — <meta charset="utf-8"> or inside
    # <meta http-equiv="content-type" content="text/html; charset=utf-8">
    charset = None
    ch = soup.find("meta", charset=True)
    if ch and isinstance(ch, Tag):
        charset = ch.get("charset")  # type: ignore[assignment]
    if not charset:
        ct_meta = soup.find("meta", attrs={"http-equiv": re.compile(r"content-type", re.I)})
        if ct_meta and isinstance(ct_meta, Tag):
            raw = str(ct_meta.get("content", ""))
            m = re.search(r"charset=([^\s;]+)", raw, re.I)
            if m:
                charset = m.group(1)

    # Open Graph tags — strip the "og:" prefix so the dict keys are cleaner
    og: Dict[str, str] = {}
    for tag in soup.find_all("meta", property=re.compile(r"^og:", re.I)):
        if not isinstance(tag, Tag):
            continue
        prop = str(tag.get("property", "")).lower().replace("og:", "")
        val = tag.get("content", "")
        if prop and val:
            og[prop] = str(val)

    # same idea for Twitter Card tags
    twitter: Dict[str, str] = {}
    for tag in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:", re.I)}):
        if not isinstance(tag, Tag):
            continue
        name = str(tag.get("name", "")).lower().replace("twitter:", "")
        val = tag.get("content", "")
        if name and val:
            twitter[name] = str(val)

    # collect all headings h1–h6, grouped by level
    headings: Dict[str, List[str]] = {}
    for n in range(1, 7):
        name = f"h{n}"
        chunk = []
        for h in soup.find_all(name):
            if h.get_text(strip=True):
                chunk.append(_squash_ws(h.get_text(separator=" ")))
        if chunk:
            headings[name] = chunk

    # links — deduplicate by absolute URL, skip anchors/js/mailto/tel
    links: List[LinkInfo] = []
    seen: set = set()
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href = str(a.get("href", "")).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        abs_url = urljoin(base, href)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        ext = urlparse(abs_url).netloc != base_host
        txt = _squash_ws(a.get_text(separator=" ")) or ""
        links.append(LinkInfo(href=abs_url, text=txt, is_external=ext))

    # images — also check data-src for lazy-loaded images
    images: List[ImageInfo] = []
    for img in soup.find_all("img"):
        if not isinstance(img, Tag):
            continue
        src = str(img.get("src", "") or img.get("data-src", "")).strip()
        if not src:
            continue
        images.append(
            ImageInfo(src=urljoin(base, src), alt=str(img.get("alt", "")).strip())
        )

    # body text — walk the DOM manually instead of soup.get_text() so I can
    # skip the noisy elements in _SKIP. this gives much cleaner text for
    # the topic scorer to work with.
    bits: List[str] = []
    body = soup.find("body")
    if body and isinstance(body, Tag):
        for node in body.descendants:
            if isinstance(node, Tag) and node.name in _SKIP:
                continue
            if isinstance(node, NavigableString):
                bit = str(node).strip()
                if bit:
                    bits.append(bit)

    body_text = _squash_ws(" ".join(bits))
    wc = len(body_text.split()) if body_text else 0

    return PageMetadata(
        url=fetch_result.url,
        final_url=fetch_result.final_url,
        status_code=fetch_result.status_code,
        title=title,
        description=description,
        keywords=keywords,
        author=author,
        language=language,
        charset=charset,
        canonical=canonical,
        robots=robots,
        og=og,
        twitter=twitter,
        headings=headings,
        links=links,
        images=images,
        body_text=body_text,
        word_count=wc,
    )
