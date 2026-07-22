"""
brand_profiles.py
------------------
"Brand voice profiles" are the upgraded, structured version of the old simple
text presets. Instead of one free-text box, a profile bundles everything a
real brand would want to reuse across every product they list:

- a short tone description ("warm, playful, a little cheeky")
- words that must never appear (banned_words)
- phrases/CTAs the brand likes to reuse (preferred_phrases)
- any other free-form instructions

Stored locally in brand_profiles.json, one file, easy to read or back up.
"""

import json
from pathlib import Path
from typing import TypedDict

PROFILES_FILE = Path(__file__).parent / "brand_profiles.json"


class BrandProfile(TypedDict):
    brand_name: str
    tone_description: str
    banned_words: list[str]
    preferred_phrases: list[str]
    extra_instructions: str


def load_profiles() -> dict[str, BrandProfile]:
    """Return {profile_name: profile_dict} for every saved brand voice."""
    if PROFILES_FILE.exists():
        try:
            return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_profile(name: str, profile: BrandProfile) -> None:
    """Create or overwrite a profile under the given name."""
    profiles = load_profiles()
    profiles[name] = profile
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2), encoding="utf-8")


def delete_profile(name: str) -> None:
    profiles = load_profiles()
    profiles.pop(name, None)
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2), encoding="utf-8")


def parse_comma_list(raw: str) -> list[str]:
    """Turn a comma-separated textbox value into a clean list of strings."""
    return [item.strip() for item in raw.split(",") if item.strip()]


def profile_to_prompt_block(profile: BrandProfile) -> str:
    """Render a brand profile as instructions Claude can follow."""
    if not any(profile.values()):
        return ""

    lines = []
    if profile.get("brand_name"):
        lines.append(f"Brand: {profile['brand_name']}.")
    if profile.get("tone_description"):
        lines.append(f"Brand tone: {profile['tone_description']}.")
    if profile.get("preferred_phrases"):
        phrases = ", ".join(f'"{p}"' for p in profile["preferred_phrases"])
        lines.append(f"Where it fits naturally, favour phrasing like: {phrases}.")
    if profile.get("banned_words"):
        banned = ", ".join(profile["banned_words"])
        lines.append(f"NEVER use these words or their close variants: {banned}.")
    if profile.get("extra_instructions"):
        lines.append(profile["extra_instructions"])

    return "\n".join(lines)
