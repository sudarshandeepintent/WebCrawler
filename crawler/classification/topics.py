from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from crawler.models.schemas import PageMetadata

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

MIN_SCORE = 0.08


def _build_kw_index() -> Dict[str, List[str]]:
    idx: Dict[str, List[str]] = {}
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            idx.setdefault(kw, []).append(topic)
    return idx


_KW_TO_TOPICS: Dict[str, List[str]] = _build_kw_index()


def _exclusivity_weight(kw: str) -> float:
    n = len(_KW_TO_TOPICS.get(kw, []))
    if n == 1:
        return 3.0
    if n == 2:
        return 1.0
    return 0.4


_CATEGORY_SIGNALS: List[Tuple[str, List[str]]] = [
    ("e-commerce", ["add to cart", "buy now", "shopping cart", "checkout", "wishlist"]),
    ("documentation", [
        "api reference", "getting started", "installation guide", "code sample",
        "parameters", "return value",
    ]),
    ("forum", ["reply to thread", "upvote", "moderator", "mark as answer"]),
    ("search-results", ["results for", "did you mean", "showing results", "no results found"]),
    ("landing-page", ["sign up for free", "request a demo", "start free trial"]),
    ("news", [
        "breaking news", "wire service", "live coverage", "press release",
        "newsroom", "byline",
    ]),
    ("profile", ["unfollow", "your followers", "edit profile", "profile picture"]),
    ("video", ["subscribe to channel", "video player", "watch full episode"]),
    ("blog", ["posted by", "filed under", "leave a comment", "tags:"]),
]

_URL_PATH_HINTS: List[Tuple[str, str]] = [
    (r"/blog/", "blog"),
    (r"/news/", "news"),
    (r"/shop/", "e-commerce"),
    (r"/store/", "e-commerce"),
    (r"/product/", "e-commerce"),
    (r"/docs/", "documentation"),
    (r"/documentation/", "documentation"),
    (r"/wiki/", "documentation"),
    (r"/forum/", "forum"),
    (r"/profile/", "profile"),
    (r"/video/", "video"),
    (r"/watch/", "video"),
    (r"/recipe/", "food"),
    (r"/camp/", "outdoors"),
    (r"/hike/", "outdoors"),
    (r"/trail/", "outdoors"),
    (r"/travel/", "travel"),
]


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    toks = re.findall(r"[a-z][a-z0-9\-']*", text)
    bi = [" ".join(toks[i : i + 2]) for i in range(len(toks) - 1)]
    tri = [" ".join(toks[i : i + 3]) for i in range(len(toks) - 2)]
    return toks + bi + tri


def _score_topics(freq: Counter, total_tokens: int) -> Dict[str, float]:
    SCALE = 5000
    if total_tokens == 0:
        return {}

    weighted_hits: Dict[str, float] = defaultdict(float)
    for tok, count in freq.items():
        topics_for_tok = _KW_TO_TOPICS.get(tok)
        if not topics_for_tok:
            continue
        tf = count / total_tokens
        w = _exclusivity_weight(tok)
        for topic in topics_for_tok:
            weighted_hits[topic] += tf * w * SCALE

    out: Dict[str, float] = {}
    for topic, total in weighted_hits.items():
        raw = total / len(TOPIC_KEYWORDS[topic])
        out[topic] = round(min(raw, 1.0), 4)
    return out


def _guess_category(url: str, body_lower: str, title: str, top_topics: List[str]) -> str:
    path = urlparse(url).path.lower()
    for pattern, cat in _URL_PATH_HINTS:
        if re.search(pattern, path):
            return cat

    scan_text = title.lower() + " " + body_lower
    for cat, needles in _CATEGORY_SIGNALS:
        if any(needle in scan_text for needle in needles):
            return cat

    return top_topics[0] if top_topics else "general"


def classify_page(meta: PageMetadata) -> PageMetadata:
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

    blob = " ".join(chunks)
    tokens = _tokenize(blob)
    freq = Counter(tokens)
    scores = _score_topics(freq, total_tokens=len(tokens))

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

    meta.topics = topics
    meta.topic_scores = {t: s for t, s in ranked}
    meta.page_category = category
    return meta
