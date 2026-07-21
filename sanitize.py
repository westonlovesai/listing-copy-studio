"""
sanitize.py
-----------
The system prompt already tells the model to avoid AI "tells". This file is the
safety net: plain Python that GUARANTEES the final text contains no em dashes or
en dashes, no matter what the model returns.

Two layers (prompt + code) is a deliberate design choice: prompts are persuasion,
code is a guarantee. This is the bit worth pointing to in an interview.
"""

import re

# Curved "smart" quotes -> straight quotes. Smart quotes are a mild AI/word-processor
# tell and can also break plain-text listings (Etsy, eBay), so we normalise them.
_QUOTE_MAP = {
    "‘": "'",  # left single quote
    "’": "'",  # right single quote / apostrophe
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "…": "...",  # ellipsis character -> three dots
}


def strip_ai_tells(text: str) -> str:
    """Return text with em/en dashes and a few other giveaways removed."""
    if not text:
        return text

    # 1. Normalise smart quotes and ellipses.
    for bad, good in _QUOTE_MAP.items():
        text = text.replace(bad, good)

    # 2. En dash (–) used as a NUMBER RANGE (e.g. "5–10") becomes a hyphen.
    text = re.sub(r"(?<=\d)\s*–\s*(?=\d)", "-", text)

    # 3. Any remaining em dash (—) or en dash (–) between words becomes a comma.
    #    "cosy — handmade"  ->  "cosy, handmade"
    text = re.sub(r"\s*[—–]\s*", ", ", text)

    # 4. Tidy up artefacts the replacements can create.
    text = re.sub(r"\s+,", ",", text)      # space before a comma
    text = re.sub(r",\s*,", ",", text)     # doubled commas
    text = re.sub(r"[ \t]{2,}", " ", text)  # runs of spaces
    text = re.sub(r",\s*([.!?])", r"\1", text)  # comma stuck before end punctuation

    return text.strip()


def contains_dash(text: str) -> bool:
    """Quick check used by the UI to prove the guarantee held."""
    return "—" in text or "–" in text
