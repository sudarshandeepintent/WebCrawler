from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from crawler.schemas import PageMetadata

# rough topic buckets — tune as you like
TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "technology": [
        "software", "hardware", "computer", "programming", "developer",
        "code", "algorithm", "database", "cloud", "api", "machine learning",
        "artificial intelligence", "ai", "cybersecurity", "blockchain",
        "javascript", "python", "startup", "tech", "digital", "internet",
        "network", "server", "data science", "open source",
    ],
    "healthcare": [
        "health", "medical", "doctor", "hospital", "patient", "disease",
        "treatment", "medicine", "clinical", "drug", "symptom", "diagnosis",
        "surgery", "therapy", "vaccine", "pharmaceutical", "nurse",
        "mental health", "wellness", "nutrition", "fitness",
    ],
    "finance": [
        "finance", "investment", "stock", "market", "economy", "bank",
        "trading", "revenue", "profit", "loss", "portfolio", "fund",
        "mortgage", "loan", "interest rate", "inflation", "cryptocurrency",
        "bitcoin", "fintech", "accounting", "tax", "insurance",
    ],
    "e-commerce": [
        "buy", "shop", "cart", "checkout", "product", "price", "discount",
        "sale", "shipping", "delivery", "order", "payment", "store",
        "purchase", "add to cart", "wishlist", "review", "rating",
        "merchandise", "retail", "warehouse",
    ],
    "news": [
        "breaking news", "latest news", "reporter", "journalist", "press",
        "headline", "editorial", "opinion", "article", "story", "report",
        "correspondent", "publication", "broadcast", "media",
    ],
    "education": [
        "learn", "course", "tutorial", "university", "college", "school",
        "student", "teacher", "curriculum", "lecture", "exam", "degree",
        "education", "training", "certification", "scholarship", "study",
        "knowledge", "academic",
    ],
    "entertainment": [
        "movie", "film", "music", "song", "album", "artist", "concert",
        "television", "tv", "show", "series", "game", "gaming", "video",
        "streaming", "podcast", "celebrity", "entertainment", "comedy",
        "drama", "thriller",
    ],
    "travel": [
        "travel", "destination", "hotel", "flight", "vacation", "trip",
        "tour", "tourism", "passport", "visa", "airline", "booking",
        "resort", "beach", "adventure", "explore", "itinerary", "guide",
    ],
    "sports": [
        "sport", "football", "soccer", "basketball", "baseball", "tennis",
        "golf", "cricket", "rugby", "athlete", "team", "championship",
        "league", "score", "match", "tournament", "olympic", "coach",
        "player", "stadium",
    ],
    "politics": [
        "politics", "government", "election", "president", "congress",
        "senate", "democrat", "republican", "policy", "law", "vote",
        "parliament", "minister", "party", "legislation", "campaign",
        "diplomacy", "democracy",
    ],
    "science": [
        "research", "scientist", "experiment", "study", "physics",
        "chemistry", "biology", "astronomy", "climate", "environment",
        "ecology", "gene", "dna", "evolution", "discovery", "laboratory",
        "hypothesis", "theory", "space", "nasa",
    ],
    "food": [
        "food", "recipe", "cook", "restaurant", "cuisine", "ingredient",
        "meal", "diet", "nutrition", "chef", "taste", "flavor", "bake",
        "grill", "vegan", "vegetarian", "organic", "menu",
    ],
    "real-estate": [
        "real estate", "property", "house", "apartment", "rent", "lease",
        "mortgage", "listing", "realtor", "agent", "neighborhood", "home",
        "buy house", "sell house", "square feet", "bedroom", "bathroom",
    ],
    "automotive": [
        "car", "truck", "vehicle", "engine", "horsepower", "electric vehicle",
        "ev", "tesla", "dealership", "driving", "fuel", "hybrid",
        "transmission", "suv", "sedan", "automobile",
    ],
    "fashion": [
        "fashion", "style", "clothing", "outfit", "designer", "brand",
        "trend", "model", "luxury", "apparel", "wardrobe", "collection",
        "dress", "shoes", "accessories",
    ],
}


def _kw_index() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            out.setdefault(kw, []).append(topic)
    return out


_KW_TO_TOPICS = _kw_index()

_CATEGORY_SIGNALS: Dict[str, List[str]] = {
    "e-commerce": ["add to cart", "buy now", "checkout", "shopping cart", "wishlist"],
    "news": ["breaking", "exclusive", "published", "by staff", "wire"],
    "blog": ["posted by", "comments", "tags:", "filed under", "subscribe"],
    "documentation": ["api reference", "getting started", "installation", "usage", "parameters"],
    "landing-page": ["get started", "sign up", "free trial", "learn more", "contact us"],
    "forum": ["reply", "thread", "post", "moderator", "upvote"],
    "search-results": ["results for", "did you mean", "showing", "of results"],
    "profile": ["followers", "following", "bio", "tweet", "timeline"],
    "video": ["watch", "subscribe", "channel", "views", "like", "share"],
}


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    toks = re.findall(r"[a-z][a-z0-9\-']*", text)
    bi = [" ".join(toks[i : i + 2]) for i in range(len(toks) - 1)]
    tri = [" ".join(toks[i : i + 3]) for i in range(len(toks) - 2)]
    return toks + bi + tri


def _score_topics(freq: Counter) -> Dict[str, float]:
    hits: Dict[str, float] = defaultdict(float)
    for tok, c in freq.items():
        for topic in _KW_TO_TOPICS.get(tok, ()):
            hits[topic] += c
    out: Dict[str, float] = {}
    for topic, h in hits.items():
        if h > 0:
            out[topic] = round(h / len(TOPIC_KEYWORDS[topic]), 4)
    return out


def _guess_category(body: str, top: List[str]) -> str:
    for cat, needles in _CATEGORY_SIGNALS.items():
        if any(n in body for n in needles):
            return cat
    if top:
        return top[0]
    return "general"


def classify_page(meta: PageMetadata) -> PageMetadata:
    # title/desc weighted a bit more than body — stops giant footers from steering everything
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
    freq = Counter(_tokenize(blob))
    scores = _score_topics(freq)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    topics = [t for t, s in ranked if s > 0]

    body_l = (meta.body_text or "").lower()
    cat = _guess_category(body_l, topics)

    meta.topics = topics
    meta.topic_scores = {t: s for t, s in ranked if s > 0}
    meta.page_category = cat
    return meta
