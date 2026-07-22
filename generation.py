"""
generation.py
-------------
The one place that actually talks to Claude. Both the Single Product tab and
the Batch tab call into this file, so there is exactly one code path for
"build a schema, call the API, sanitize the result" - no duplicated logic to
drift out of sync.
"""

import base64
import json

import anthropic

from prompts import SYSTEM_PROMPT
from sanitize import strip_ai_tells

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class GenerationError(Exception):
    """Raised when Claude's response can't be used: a safety refusal, an empty
    response, or output that didn't parse as the requested JSON. Callers should
    show `str(error)` to the user rather than letting a raw StopIteration or
    JSONDecodeError bubble up as a traceback."""


def build_schema(include_title_bullets: bool, target_language: str | None) -> dict:
    """Build the JSON schema Claude's response must match, based on what
    extras the user asked for. Keeping this dynamic means we never ask for
    (or pay tokens for) a translation or bullets nobody wants."""

    def _listing_shape() -> tuple[dict, list[str]]:
        shape = {
            "variations": {"type": "array", "items": {"type": "string"}},
        }
        required = ["variations"]
        if include_title_bullets:
            shape["title"] = {"type": "string"}
            shape["bullets"] = {"type": "array", "items": {"type": "string"}}
            required += ["title", "bullets"]
        return shape, required

    properties, required = _listing_shape()

    if target_language:
        translated_props, translated_required = _listing_shape()
        properties["translated"] = {
            "type": "object",
            "properties": translated_props,
            "required": translated_required,
            "additionalProperties": False,
        }
        required.append("translated")

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def build_image_blocks(uploaded_files) -> list[dict]:
    """Turn Streamlit's uploaded files into Anthropic image content blocks."""
    blocks = []
    for f in uploaded_files or []:
        if f.type not in ALLOWED_IMAGE_TYPES:
            continue
        data = base64.standard_b64encode(f.getvalue()).decode("utf-8")
        blocks.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": f.type, "data": data},
            }
        )
    return blocks


def _sanitize_result(result: dict) -> dict:
    """Run every text field the schema might contain through strip_ai_tells."""
    if "variations" in result:
        result["variations"] = [strip_ai_tells(v) for v in result["variations"]]
    if "title" in result:
        result["title"] = strip_ai_tells(result["title"])
    if "bullets" in result:
        result["bullets"] = [strip_ai_tells(b) for b in result["bullets"]]
    if "translated" in result:
        result["translated"] = _sanitize_result(result["translated"])
    return result


def generate_listing(
    model_id: str,
    user_prompt: str,
    image_blocks: list[dict],
    include_title_bullets: bool = False,
    target_language: str | None = None,
):
    """Call Claude and return (sanitized_result: dict, usage) for one product."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    schema = build_schema(include_title_bullets, target_language)

    content = image_blocks + [{"type": "text", "text": user_prompt}]

    response = client.messages.create(
        model=model_id,
        max_tokens=8000,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )

    if response.stop_reason == "refusal":
        category = None
        if response.stop_details is not None:
            category = getattr(response.stop_details, "category", None)
        raise GenerationError(
            "Claude declined to write this listing"
            + (f" (safety category: {category})" if category else "")
            + ". Try rephrasing the product details or instructions."
        )

    text_blocks = [b.text for b in response.content if b.type == "text"]
    if not text_blocks:
        raise GenerationError(
            f"Claude's response had no usable text (stop_reason={response.stop_reason!r})."
        )

    try:
        result = json.loads(text_blocks[0])
    except json.JSONDecodeError as e:
        raise GenerationError(
            "Claude's response was cut off or malformed and couldn't be read. "
            "This can happen with a very long request - try fewer versions or a "
            "shorter length."
        ) from e

    result = _sanitize_result(result)

    return result, response.usage
