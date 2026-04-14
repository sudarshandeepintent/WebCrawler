"""
Topic scoring and page-category detection.

Improvements over v1
---------------------
1.  **Exclusive-keyword bonus** – a keyword that belongs to only ONE topic
    receives a 3× multiplier; two-topic keywords get 1×; three-or-more get 0.4×.
    This suppresses promiscuous words like "article", "store", or "menu" from
    hijacking every page's scores.

2.  **Cleaned vocabularies** – removed words that were causing systematic
    false positives:
      - "news":       removed "article", "story", "report", "editorial",
                      "media", "publication", "opinion"  (appear on any blog)
      - "e-commerce": removed "store", "product", "shop", "order", "review",
                      "rating"  (appear on any commercial/informational site)
      - "food":       removed "menu"  (HTML nav menus are everywhere)
      - "politics":   removed "policy", "law", "party"  (boilerplate footer words)
      - "science":    removed "study"  (shared with education, too generic)
      - "real-estate":removed "home"   (too generic)

3.  **New "outdoors" topic** – covers hiking, camping, gear, trail, nature, etc.
    Needed for sites like REI, AllTrails, NPS, etc.

4.  **Minimum score threshold** – topics scoring below MIN_SCORE (0.08) are
    silently dropped, preventing noise topics from polluting the list.

5.  **URL-path category hints** – `/blog/`, `/shop/`, `/news/`, `/docs/` etc.
    in the page URL are used as strong, high-confidence category signals before
    falling back to keyword scoring.

6.  **Score capping** – final scores are clamped to [0, 1].
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from crawler.schemas import PageMetadata

# ---------------------------------------------------------------------------
# Topic vocabularies
# Rule: prefer *specific* terms over generic ones.
# If a word could appear naturally on 3+ unrelated page types, drop it.
# ---------------------------------------------------------------------------
TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "technology": [
        "software", "hardware", "programming", "developer", "codebase",
        "algorithm", "database", "cloud computing", "api", "machine learning",
        "artificial intelligence", "cybersecurity", "blockchain",
        "javascript", "python", "typescript", "startup", "tech stack",
        "open source", "repository", "devops", "microservice", "framework",
        "deployment", "kubernetes", "docker",
    ],
    "outdoors": [
        "hiking", "camping", "backpacking", "trail", "outdoor", "wilderness",
        "mountain", "summit", "forest", "nature", "wildlife", "tent",
        "campfire", "kayak", "canoe", "climbing", "gear", "trek", "expedition",
        "national park", "scenic", "campsite", "trailhead", "wildflower",
        "sunrise hike", "backpack",
    ],
    "healthcare": [
        "medical", "doctor", "hospital", "patient", "disease",
        "treatment", "medicine", "clinical trial", "prescription", "diagnosis",
        "surgery", "therapy", "vaccine", "pharmaceutical", "nurse",
        "mental health", "wellness", "chronic", "symptom", "specialist",
        "telemedicine", "healthcare provider",
    ],
    "finance": [
        "investment", "stock market", "equity", "portfolio", "hedge fund",
        "trading", "revenue", "profit margin", "cryptocurrency", "bitcoin",
        "fintech", "accounting", "tax return", "insurance premium",
        "interest rate", "inflation", "bond", "dividend", "ipo",
        "venture capital", "balance sheet", "fiscal",
    ],
    "e-commerce": [
        "add to cart", "buy now", "checkout page", "shopping cart", "wishlist",
        "free shipping", "discount code", "promo code", "sale price",
        "sold out", "in stock", "payment gateway", "refund policy",
        "easy returns", "online store", "marketplace listing", "cart total",
        "subscription plan", "quantity in stock",
    ],
    "news": [
        "breaking news", "journalist", "press release", "headline",
        "correspondent", "broadcast", "wire service", "newsroom",
        "byline", "exclusive interview", "investigative report", "scoop",
        "editor in chief", "news anchor", "live coverage", "news brief",
    ],
    "education": [
        "learn", "course", "tutorial", "university", "college", "school",
        "student", "teacher", "curriculum", "lecture", "exam", "degree",
        "certification", "scholarship", "academic", "classroom",
        "e-learning", "syllabus", "homework", "campus",
    ],
    "entertainment": [
        "movie", "film", "music album", "concert", "television series",
        "streaming", "podcast", "celebrity", "box office", "trailer",
        "gaming", "video game", "esports", "comedy show", "thriller",
        "box set", "soundtrack", "award show",
    ],
    "travel": [
        "destination", "hotel", "flight", "vacation", "itinerary",
        "tourism", "passport", "visa", "airline", "resort", "beach",
        "cruise", "travel guide", "booking", "hostel", "sightseeing",
        "travel insurance", "layover", "round trip",
    ],
    "sports": [
        "football", "soccer", "basketball", "baseball", "tennis",
        "golf", "cricket", "rugby", "athlete", "championship",
        "league standings", "tournament bracket", "olympic games",
        "transfer window", "locker room", "halftime", "penalty kick",
        "grand slam", "world cup",
    ],
    "politics": [
        "election", "president", "congress", "senate",
        "democrat", "republican", "legislation", "campaign",
        "diplomacy", "democracy", "political party", "ballot",
        "filibuster", "geopolitics", "foreign policy", "referendum",
        "parliament", "prime minister", "caucus",
    ],
    "science": [
        "research", "scientist", "experiment", "hypothesis",
        "physics", "chemistry", "biology", "astronomy",
        "climate change", "ecology", "genome", "dna sequencing",
        "evolution", "laboratory", "peer review", "scientific paper",
        "nasa", "quantum", "neuroscience",
    ],
    "food": [
        "recipe", "cook", "restaurant", "cuisine", "ingredient",
        "meal prep", "diet plan", "chef", "flavor profile", "bake",
        "grill", "vegan", "vegetarian", "organic produce", "appetizer",
        "entree", "dessert", "food pairing", "culinary",
    ],
    "real-estate": [
        "real estate", "property listing", "apartment", "rent",
        "lease agreement", "mortgage rate", "realtor", "mls listing",
        "neighborhood", "square footage", "bedroom", "bathroom",
        "open house", "closing costs", "down payment", "hoa",
    ],
    "automotive": [
        "car review", "truck", "electric vehicle", "engine specs",
        "horsepower", "ev range", "dealership", "test drive",
        "fuel economy", "hybrid", "transmission", "suv", "sedan",
        "recalls", "vin", "mpg", "torque", "powertrain",
    ],
    "fashion": [
        "fashion week", "designer", "luxury brand", "wardrobe",
        "apparel", "runway", "haute couture", "streetwear", "lookbook",
        "capsule collection", "accessories", "handbag", "sneakers",
        "sustainable fashion", "outfit ideas",
    ],
}

# Minimum normalised score to be included in the output topics list
MIN_SCORE: float = 0.08

# ---------------------------------------------------------------------------
# Pre-compute: keyword → list of topics it belongs to (for exclusivity check)
# ---------------------------------------------------------------------------
def _build_kw_index() -> Dict[str, List[str]]:
    idx: Dict[str, List[str]] = {}
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            idx.setdefault(kw, []).append(topic)
    return idx


_KW_TO_TOPICS: Dict[str, List[str]] = _build_kw_index()


def _exclusivity_weight(kw: str) -> float:
    """
    Return a multiplier based on how many topics share this keyword.
      1 topic  → 3.0  (strong, unambiguous signal)
      2 topics → 1.0  (moderate signal)
      3+ topics → 0.4  (weak, noisy signal)
    """
    n = len(_KW_TO_TOPICS.get(kw, []))
    if n == 1:
        return 3.0
    if n == 2:
        return 1.0
    return 0.4


# ---------------------------------------------------------------------------
# Structural category signals (checked against full lowercase body text)
# Ordered from most-specific to least-specific to prevent early false matches.
# ---------------------------------------------------------------------------
_CATEGORY_SIGNALS: List[Tuple[str, List[str]]] = [
    # Most-specific structural cues first to avoid false early matches
    ("e-commerce",     ["add to cart", "buy now", "shopping cart", "checkout", "wishlist"]),
    ("documentation",  ["api reference", "getting started", "installation guide",
                        "code sample", "parameters", "return value"]),
    ("forum",          ["reply to thread", "upvote", "moderator", "mark as answer"]),
    ("search-results", ["results for", "did you mean", "showing results", "no results found"]),
    ("landing-page",   ["sign up for free", "request a demo", "start free trial"]),
    # news BEFORE profile — news pages mention "timeline" (article timelines),
    # so news must win before profile's "timeline" signal fires
    ("news",           ["breaking news", "wire service", "live coverage", "press release",
                        "newsroom", "byline"]),
    # profile signals tightened: require unambiguous social-profile-only terms
    ("profile",        ["unfollow", "your followers", "edit profile", "profile picture"]),
    ("video",          ["subscribe to channel", "video player", "watch full episode"]),
    # blog: "posted by" and "filed under" are strong; "comments" alone is too broad
    ("blog",           ["posted by", "filed under", "leave a comment", "tags:"]),
]

# URL path patterns that strongly indicate a category
_URL_PATH_HINTS: List[Tuple[str, str]] = [
    (r"/blog/",        "blog"),
    (r"/news/",        "news"),
    (r"/shop/",        "e-commerce"),
    (r"/store/",       "e-commerce"),
    (r"/product/",     "e-commerce"),
    (r"/docs/",        "documentation"),
    (r"/documentation/","documentation"),
    (r"/wiki/",        "documentation"),
    (r"/forum/",       "forum"),
    (r"/profile/",     "profile"),
    (r"/video/",       "video"),
    (r"/watch/",       "video"),
    (r"/recipe/",      "food"),
    (r"/camp/",        "outdoors"),
    (r"/hike/",        "outdoors"),
    (r"/trail/",       "outdoors"),
    (r"/travel/",      "travel"),
]


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> List[str]:
    """
    Lower-case, produce unigrams + bigrams + trigrams.
    Bigrams/trigrams are essential for matching phrases like
    "machine learning", "add to cart", "free shipping", etc.
    """
    text = text.lower()
    toks = re.findall(r"[a-z][a-z0-9\-']*", text)
    bi  = [" ".join(toks[i:i+2]) for i in range(len(toks) - 1)]
    tri = [" ".join(toks[i:i+3]) for i in range(len(toks) - 2)]
    return toks + bi + tri


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _score_topics(freq: Counter, total_tokens: int) -> Dict[str, float]:
    """
    TF-based scoring with exclusivity weighting.

    For each topic:
        score = Σ( (freq[kw] / total_tokens) × exclusivity_weight(kw) × SCALE )
                ─────────────────────────────────────────────────────────────────
                                    len(topic_keywords)

    Dividing by ``total_tokens`` converts raw counts to term-frequency (TF),
    keeping scores comparable across short (blog post) and long (news homepage)
    documents instead of letting volume inflate every score to the ceiling.

    SCALE = 5000 keeps scores in a human-readable range (~0.0 – 1.0) for
    typical web pages.
    """
    SCALE = 5000
    if total_tokens == 0:
        return {}

    weighted_hits: Dict[str, float] = defaultdict(float)
    for tok, count in freq.items():
        topics_for_tok = _KW_TO_TOPICS.get(tok)
        if not topics_for_tok:
            continue
        tf = count / total_tokens
        w  = _exclusivity_weight(tok)
        for topic in topics_for_tok:
            weighted_hits[topic] += tf * w * SCALE

    out: Dict[str, float] = {}
    for topic, total in weighted_hits.items():
        raw = total / len(TOPIC_KEYWORDS[topic])
        out[topic] = round(min(raw, 1.0), 4)
    return out


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------
def _guess_category(url: str, body_lower: str, title: str, top_topics: List[str]) -> str:
    """
    Determine the structural page category using (in priority order):
      1. URL path patterns            — highest confidence
      2. Title + body structural cues — strong semantic signal
      3. Highest-scoring topic        — fallback
    """
    # 1 — URL path
    path = urlparse(url).path.lower()
    for pattern, cat in _URL_PATH_HINTS:
        if re.search(pattern, path):
            return cat

    # 2 — Scan title + body together so short pages (e.g. NYT homepage)
    #     with keywords only in the title are still correctly classified
    scan_text = (title.lower() + " " + body_lower)
    for cat, needles in _CATEGORY_SIGNALS:
        if any(needle in scan_text for needle in needles):
            return cat

    # 3 — Topic fallback
    return top_topics[0] if top_topics else "general"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def classify_page(meta: PageMetadata) -> PageMetadata:
    """
    Enrich *meta* with ``page_category``, ``topics``, and ``topic_scores``.

    Weighted corpus
    ---------------
    title        ×5   – highest signal density
    description  ×4   – explicit page summary
    keywords     ×4   – author-declared topics
    h1/h2/h3     ×3   – section-level topic signals
    body text    ×1   – full content (diluted by boilerplate)
    """
    chunks: List[str] = []
    if meta.title:
        chunks += [meta.title] * 5
    if meta.description:
        chunks += [meta.description] * 4
    if meta.keywords:
        chunks += [meta.keywords] * 4
    for lvl in ("h1", "h2", "h3"):
        for h in meta.headings.get(lvl, []):
            chunks += [h] * 3
    if meta.body_text:
        chunks.append(meta.body_text)

    blob   = " ".join(chunks)
    tokens = _tokenize(blob)
    freq   = Counter(tokens)
    scores = _score_topics(freq, total_tokens=len(tokens))

    # Sort by score descending; apply minimum threshold
    ranked = sorted(
        ((t, s) for t, s in scores.items() if s >= MIN_SCORE),
        key=lambda x: x[1],
        reverse=True,
    )

    topics = [t for t, _ in ranked]
    body_lower = (meta.body_text or "").lower()
    category = _guess_category(
        meta.final_url or meta.url,
        body_lower,
        title=meta.title or "",
        top_topics=topics,
    )

    meta.topics        = topics
    meta.topic_scores  = {t: s for t, s in ranked}
    meta.page_category = category
    return meta
