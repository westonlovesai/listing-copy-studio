"""
app.py
------
The Streamlit web app. Run it with:

    streamlit run app.py

It reads your Anthropic API key from a .env file (see .env.example).
"""

import base64
import json
import os
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

from prompts import (
    LENGTHS,
    PLATFORMS,
    STYLES,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from sanitize import contains_dash, strip_ai_tells

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
load_dotenv()  # pulls ANTHROPIC_API_KEY out of the .env file

PRESETS_FILE = Path(__file__).parent / "presets.json"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Model choices. Opus is highest quality; Sonnet is cheaper and faster and is
# excellent for copywriting; Haiku is cheapest for quick drafts.
MODELS = {
    "Claude Opus 4.8 (highest quality)": "claude-opus-4-8",
    "Claude Sonnet 5 (great value, recommended)": "claude-sonnet-5",
    "Claude Haiku 4.5 (fast & cheap)": "claude-haiku-4-5",
}


# ---------------------------------------------------------------------------
# Preset storage (the "save an option you use often" feature)
# ---------------------------------------------------------------------------
def load_presets() -> dict:
    if PRESETS_FILE.exists():
        try:
            return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_preset(name: str, text: str) -> None:
    presets = load_presets()
    presets[name] = text
    PRESETS_FILE.write_text(json.dumps(presets, indent=2), encoding="utf-8")


def delete_preset(name: str) -> None:
    presets = load_presets()
    presets.pop(name, None)
    PRESETS_FILE.write_text(json.dumps(presets, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Talking to Claude
# ---------------------------------------------------------------------------
def generate_descriptions(model_id, user_prompt, image_blocks, num_variations):
    """Send the request to Claude and return a list of clean description strings."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    # The user turn = the images (if any) followed by the text instruction.
    content = image_blocks + [{"type": "text", "text": user_prompt}]

    # Structured output: we ask for a JSON object with a "variations" array so we
    # get clean, separated descriptions we can sanitise and display one by one.
    schema = {
        "type": "object",
        "properties": {
            "variations": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "required": ["variations"],
        "additionalProperties": False,
    }

    response = client.messages.create(
        model=model_id,
        max_tokens=8000,
        # System prompt as a cacheable block: if you generate lots of listings in
        # a row, the big "backbone" prompt is served from cache and costs less.
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

    # With structured output the first text block is guaranteed to be valid JSON.
    raw = next(b.text for b in response.content if b.type == "text")
    variations = json.loads(raw)["variations"]

    # Final guarantee: strip any em/en dashes or smart quotes that slipped through.
    return [strip_ai_tells(v) for v in variations]


def build_image_blocks(uploaded_files):
    """Turn Streamlit's uploaded files into Anthropic image content blocks."""
    blocks = []
    for f in uploaded_files:
        if f.type not in ALLOWED_IMAGE_TYPES:
            st.warning(f"Skipped {f.name}: unsupported type ({f.type}).")
            continue
        data = base64.standard_b64encode(f.getvalue()).decode("utf-8")
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": f.type,
                    "data": data,
                },
            }
        )
    return blocks


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Listing Copy Studio", page_icon="🛍️", layout="wide")
st.title("🛍️ Listing Copy Studio")
st.caption(
    "Turn product details and photos into ready-to-paste listing copy. "
    "No em dashes, no AI tells."
)

# Stop early with a friendly message if there's no API key yet.
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error(
        "No API key found. Copy `.env.example` to `.env`, paste your Anthropic "
        "API key into it, then restart the app."
    )
    st.stop()

left, right = st.columns([1, 1])

with left:
    st.subheader("1. Your product")
    product_name = st.text_input("Product name", placeholder="e.g. Hand-poured soy candle")
    details = st.text_area(
        "Key details / features",
        height=140,
        placeholder="Materials, size, scent, what makes it special, who it's for...",
    )
    uploaded_files = st.file_uploader(
        "Product photos (optional)",
        type=["jpg", "jpeg", "png", "gif", "webp"],
        accept_multiple_files=True,
        help="Claude looks at these and writes copy that matches what it sees.",
    )
    if uploaded_files:
        st.image([f for f in uploaded_files], width=110)

    st.subheader("2. How it should sound")
    c1, c2, c3 = st.columns(3)
    style = c1.selectbox("Style", list(STYLES.keys()))
    platform = c2.selectbox("Platform", list(PLATFORMS.keys()))
    length = c3.selectbox("Length", list(LENGTHS.keys()), index=1)

    num_variations = st.slider("How many versions to generate", 1, 3, 2)
    model_label = st.selectbox("Model", list(MODELS.keys()))

with right:
    st.subheader("3. Custom instructions")
    st.caption(
        "Anything the dropdowns don't cover: brand voice, words to include or avoid, "
        "a call to action, target customer, etc."
    )

    presets = load_presets()

    # --- Load a saved preset -------------------------------------------------
    preset_names = ["(none)"] + sorted(presets.keys())
    chosen_preset = st.selectbox("Load a saved instruction", preset_names)

    # When a preset is picked, drop its text into the box.
    if "custom_text" not in st.session_state:
        st.session_state.custom_text = ""
    if chosen_preset == "(none)":
        # Reset the memory so picking the SAME preset again later still reloads it.
        st.session_state["_last_preset"] = None
    elif st.session_state.get("_last_preset") != chosen_preset:
        st.session_state.custom_text = presets.get(chosen_preset, "")
        st.session_state["_last_preset"] = chosen_preset

    custom_instructions = st.text_area(
        "Instructions for this listing",
        key="custom_text",
        height=160,
        placeholder="e.g. Aim at eco-conscious gift buyers. Mention it's plastic-free. "
        "End with a gentle nudge to add to cart.",
    )

    # --- Save the current box as a reusable preset ---------------------------
    st.markdown("**💾 Reuse this often? Save it as a preset:**")
    s1, s2 = st.columns([2, 1])
    preset_name = s1.text_input(
        "Preset name", placeholder="e.g. Eco gift voice", label_visibility="collapsed"
    )
    if s2.button("Save preset", use_container_width=True):
        if preset_name.strip() and custom_instructions.strip():
            save_preset(preset_name.strip(), custom_instructions)
            st.success(f"Saved preset '{preset_name.strip()}'. Find it in the dropdown above.")
            st.rerun()
        else:
            st.warning("Give the preset a name and some instructions first.")

    if chosen_preset != "(none)":
        if st.button(f"🗑️ Delete preset '{chosen_preset}'"):
            delete_preset(chosen_preset)
            st.session_state["_last_preset"] = None
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------
if st.button("✨ Generate descriptions", type="primary", use_container_width=True):
    if not product_name.strip() and not details.strip() and not uploaded_files:
        st.warning("Add a product name, some details, or a photo first.")
    else:
        image_blocks = build_image_blocks(uploaded_files) if uploaded_files else []
        user_prompt = build_user_prompt(
            product_name=product_name,
            details=details,
            style=style,
            platform=platform,
            length=length,
            custom_instructions=custom_instructions,
            num_variations=num_variations,
            has_images=bool(image_blocks),
        )

        try:
            with st.spinner("Writing your copy..."):
                results = generate_descriptions(
                    MODELS[model_label], user_prompt, image_blocks, num_variations
                )
        except anthropic.AuthenticationError:
            st.error("Your API key was rejected. Check the value in your .env file.")
            st.stop()
        except anthropic.RateLimitError:
            st.error("Rate limited by the API. Wait a moment and try again.")
            st.stop()
        except anthropic.APIError as e:
            st.error(f"The API returned an error: {e.message}")
            st.stop()

        st.subheader("Results")
        for i, text in enumerate(results, start=1):
            with st.container(border=True):
                st.markdown(f"**Version {i}**")
                st.write(text)
                # Prove the guarantee held.
                if contains_dash(text):
                    st.warning("A dash slipped through (this should never happen).")
                else:
                    st.caption("✅ No em/en dashes. Copy and paste as-is.")
