"""
app.py
------
The Streamlit web app. Run it with:

    streamlit run app.py

It reads your Anthropic API key from a .env file (see .env.example).

Four tabs:
  - Single Product : one item at a time, with photos, title/bullets, translation.
  - Batch (CSV)     : a whole spreadsheet of products at once.
  - Brand Voice     : reusable, structured brand voice profiles.
  - History         : every past single-product generation, so nothing is lost.

A note on session_state: results are stored in st.session_state and rendered
from there, not just inside the `if st.button(...)` block. Streamlit reruns
the ENTIRE script on every widget interaction, and a button's clicked-state is
only True on the exact rerun it was clicked - on any later rerun (say, you
nudge the length dropdown), it's False again. Anything displayed only inside
that `if` block would vanish the instant you touched anything else on the
page. Storing the result in session_state and rendering it unconditionally
(if present) is what makes it stick around.
"""

import os

import anthropic
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from batch import make_template_csv, run_batch, validate_columns
from brand_profiles import (
    delete_profile,
    load_profiles,
    parse_comma_list,
    profile_to_prompt_block,
    save_profile,
)
from costs import estimate_cost, format_cost
from generation import GenerationError, build_image_blocks, generate_listing
from history import append_entry, clear_history, load_history
from prompts import (
    LANGUAGES,
    LENGTHS,
    PLATFORM_TITLE_LIMITS,
    PLATFORMS,
    STYLES,
    build_user_prompt,
)
from sanitize import contains_dash, find_banned_words

load_dotenv()

MODELS = {
    "Claude Opus 4.8 (highest quality)": "claude-opus-4-8",
    "Claude Sonnet 5 (great value, recommended)": "claude-sonnet-5",
    "Claude Haiku 4.5 (fast & cheap)": "claude-haiku-4-5",
}


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Listing Copy Studio", page_icon="🛍️", layout="wide")
st.title("🛍️ Listing Copy Studio")
st.caption(
    "Turn product details and photos into ready-to-paste listing copy. "
    "No em dashes, no AI tells."
)

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error(
        "No API key found. Copy `.env.example` to `.env`, paste your Anthropic "
        "API key into it, then restart the app."
    )
    st.stop()

if "session_cost" not in st.session_state:
    st.session_state.session_cost = 0.0


def add_to_session_cost(amount: float) -> None:
    st.session_state.session_cost += amount


def handle_generation_error(e: Exception) -> None:
    """One place to turn a generation failure into a friendly message."""
    if isinstance(e, anthropic.AuthenticationError):
        st.error("Your API key was rejected. Check the value in your .env file.")
    elif isinstance(e, anthropic.RateLimitError):
        st.error("Rate limited by the API. Wait a moment and try again.")
    elif isinstance(e, anthropic.APIConnectionError):
        st.error("Couldn't reach the Anthropic API. Check your internet connection.")
    elif isinstance(e, GenerationError):
        st.error(str(e))
    elif isinstance(e, anthropic.APIError):
        st.error(f"The API returned an error: {e.message}")
    else:
        raise e


# ---------------------------------------------------------------------------
# Sidebar: model choice + live cost tracker
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    model_label = st.selectbox("Model", list(MODELS.keys()))
    model_id = MODELS[model_label]

    st.divider()
    st.subheader("💵 Session cost (estimate)")
    st.metric("Spent so far this session", format_cost(st.session_state.session_cost))
    st.caption(
        "A rough estimate from published per-token pricing, including the "
        "discount for cached tokens. Not a bill, just a sense of scale."
    )
    if st.button("Reset counter", use_container_width=True):
        st.session_state.session_cost = 0.0
        st.rerun()

tab_single, tab_batch, tab_brand, tab_history = st.tabs(
    ["✍️ Single Product", "📦 Batch (CSV)", "🎙️ Brand Voice", "🕘 History"]
)


# ---------------------------------------------------------------------------
# Shared helper: render one generated result block (used by Single + History)
# ---------------------------------------------------------------------------
def render_variation(text: str, label: str, banned_words: list[str], key: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{label}**")
        st.code(text, language=None, wrap_lines=True)

        word_count = len(text.split())
        char_count = len(text)
        st.caption(f"{word_count} words - {char_count} characters")

        if contains_dash(text):
            st.warning("A dash slipped through (this should never happen).")
        else:
            st.caption("✅ No em/en dashes.")

        hits = find_banned_words(text, banned_words)
        if hits:
            st.error(f"⚠️ Banned word(s) found: {', '.join(hits)}. Consider regenerating.")

        st.download_button(
            "⬇️ Download as .txt",
            data=text,
            file_name=f"{label.lower().replace(' ', '_')}.txt",
            mime="text/plain",
            key=f"dl_{key}",
        )


def render_listing_result(
    result: dict,
    banned_words: list[str],
    include_title_bullets: bool,
    platform: str,
    target_language: str | None,
    key_prefix: str,
) -> None:
    """Render one full generated listing: title/bullets, variations, and the
    translated section if present. Used by Single Product's persisted results
    AND by the History tab, so both show the same complete picture."""
    if include_title_bullets:
        limit = PLATFORM_TITLE_LIMITS.get(platform, 150)
        title = result.get("title", "")
        over_limit = len(title) > limit
        st.markdown(f"**Title** {'🔴' if over_limit else '🟢'} ({len(title)}/{limit} characters)")
        st.code(title, language=None)
        st.markdown("**Feature bullets**")
        for b in result.get("bullets", []):
            st.markdown(f"- {b}")
        st.divider()

    for i, text in enumerate(result.get("variations", []), start=1):
        render_variation(text, f"Version {i}", banned_words, key=f"{key_prefix}_main_{i}")

    if target_language and result.get("translated"):
        st.subheader(f"🌐 {target_language} version")
        translated = result["translated"]

        if include_title_bullets:
            t_title = translated.get("title", "")
            st.markdown(f"**Title** ({len(t_title)} characters)")
            st.code(t_title, language=None)
            st.markdown("**Feature bullets**")
            for b in translated.get("bullets", []):
                st.markdown(f"- {b}")
            st.divider()

        for i, text in enumerate(translated.get("variations", []), start=1):
            render_variation(
                text,
                f"{target_language} Version {i}",
                banned_words,
                key=f"{key_prefix}_tr_{i}",
            )


# ===========================================================================
# TAB 1 - Single Product
# ===========================================================================
with tab_single:
    left, right = st.columns([1, 1])

    with left:
        st.subheader("1. Your product")
        product_name = st.text_input(
            "Product name", placeholder="e.g. Hand-poured soy candle", key="s_name"
        )
        details = st.text_area(
            "Key details / features",
            height=140,
            placeholder="Materials, size, scent, what makes it special, who it's for...",
            key="s_details",
        )
        uploaded_files = st.file_uploader(
            "Product photos (optional)",
            type=["jpg", "jpeg", "png", "gif", "webp"],
            accept_multiple_files=True,
            help="Claude looks at these and writes copy that matches what it sees.",
            key="s_photos",
        )
        if uploaded_files:
            st.image(list(uploaded_files), width=110)

        st.subheader("2. How it should sound")
        c1, c2, c3 = st.columns(3)
        style = c1.selectbox("Style", list(STYLES.keys()), key="s_style")
        platform = c2.selectbox("Platform", list(PLATFORMS.keys()), key="s_platform")
        length = c3.selectbox("Length", list(LENGTHS.keys()), index=1, key="s_length")

        num_variations = st.slider("How many versions to generate", 1, 3, 2, key="s_num")

        st.subheader("3. Extras")
        e1, e2 = st.columns(2)
        include_title_bullets = e1.checkbox(
            "Also write a title + 5 feature bullets", key="s_title_bullets"
        )
        want_translation = e2.checkbox("Also translate to another language", key="s_want_lang")
        target_language = None
        if want_translation:
            target_language = st.selectbox("Target language", LANGUAGES, key="s_lang")

    with right:
        st.subheader("4. Brand voice & custom instructions")

        profiles = load_profiles()
        profile_names = ["(none)"] + sorted(profiles.keys())
        chosen_profile = st.selectbox(
            "Brand voice profile",
            profile_names,
            key="s_profile",
            help="Manage these in the Brand Voice tab.",
        )
        active_profile = profiles.get(chosen_profile, {}) if chosen_profile != "(none)" else {}
        brand_profile_text = profile_to_prompt_block(active_profile) if active_profile else ""
        banned_words = active_profile.get("banned_words", []) if active_profile else []

        if brand_profile_text:
            with st.expander("Preview what this brand voice adds"):
                st.text(brand_profile_text)

        custom_instructions = st.text_area(
            "Instructions for this specific product",
            height=120,
            placeholder="e.g. Aim at eco-conscious gift buyers. End with a gentle nudge "
            "to add to cart.",
            key="s_custom",
        )

    st.divider()

    if st.button("✨ Generate descriptions", type="primary", use_container_width=True):
        if not product_name.strip() and not details.strip() and not uploaded_files:
            st.warning("Add a product name, some details, or a photo first.")
        else:
            image_blocks = build_image_blocks(uploaded_files)
            user_prompt = build_user_prompt(
                product_name=product_name,
                details=details,
                style=style,
                platform=platform,
                length=length,
                brand_profile_text=brand_profile_text,
                custom_instructions=custom_instructions,
                num_variations=num_variations,
                has_images=bool(image_blocks),
                include_title_bullets=include_title_bullets,
                target_language=target_language,
            )

            try:
                with st.spinner("Writing your copy..."):
                    result, usage = generate_listing(
                        model_id=model_id,
                        user_prompt=user_prompt,
                        image_blocks=image_blocks,
                        include_title_bullets=include_title_bullets,
                        target_language=target_language,
                    )
                add_to_session_cost(estimate_cost(model_id, usage))

                # Persist everything needed to re-render, so the result survives
                # a rerun triggered by some OTHER widget (see module docstring).
                st.session_state["single_result"] = {
                    "result": result,
                    "banned_words": banned_words,
                    "include_title_bullets": include_title_bullets,
                    "target_language": target_language,
                    "platform": platform,
                }

                # Save to history (best effort - never block the UI on this).
                try:
                    append_entry(
                        {
                            "product_name": product_name or "(untitled)",
                            "style": style,
                            "platform": platform,
                            "length": length,
                            "model": model_label,
                            "brand_profile": chosen_profile,
                            "banned_words": banned_words,
                            "include_title_bullets": include_title_bullets,
                            "target_language": target_language,
                            "result": result,
                        }
                    )
                except Exception:
                    pass

                # Rerun so the sidebar's cost metric (rendered at the TOP of the
                # script, before this code runs) picks up the new total right
                # away instead of showing it one interaction late.
                st.rerun()
            except (
                anthropic.AuthenticationError,
                anthropic.RateLimitError,
                anthropic.APIConnectionError,
                GenerationError,
                anthropic.APIError,
            ) as e:
                handle_generation_error(e)

    saved_single = st.session_state.get("single_result")
    if saved_single:
        st.subheader("Results")
        render_listing_result(
            result=saved_single["result"],
            banned_words=saved_single["banned_words"],
            include_title_bullets=saved_single["include_title_bullets"],
            platform=saved_single["platform"],
            target_language=saved_single["target_language"],
            key_prefix="single",
        )


# ===========================================================================
# TAB 2 - Batch (CSV)
# ===========================================================================
with tab_batch:
    st.subheader("Generate descriptions for a whole spreadsheet of products")
    st.caption(
        "Good for a real catalog: upload a CSV with a `product_name` and `details` "
        "column, generate one description per row, and download the results. "
        "Photos and multiple versions per product are not supported in batch mode - "
        "use the Single Product tab for those."
    )

    st.download_button(
        "⬇️ Download a starter CSV template",
        data=make_template_csv(),
        file_name="product_batch_template.csv",
        mime="text/csv",
    )

    b1, b2, b3 = st.columns(3)
    batch_style = b1.selectbox("Style", list(STYLES.keys()), key="b_style")
    batch_platform = b2.selectbox("Platform", list(PLATFORMS.keys()), key="b_platform")
    batch_length = b3.selectbox("Length", list(LENGTHS.keys()), index=1, key="b_length")

    be1, be2 = st.columns(2)
    batch_title_bullets = be1.checkbox(
        "Also write a title + 5 bullets per product", key="b_title_bullets"
    )
    batch_want_lang = be2.checkbox("Also translate every row", key="b_want_lang")
    batch_language = None
    if batch_want_lang:
        batch_language = st.selectbox("Target language", LANGUAGES, key="b_lang")

    batch_profiles = load_profiles()
    batch_profile_names = ["(none)"] + sorted(batch_profiles.keys())
    batch_chosen_profile = st.selectbox(
        "Brand voice profile", batch_profile_names, key="b_profile"
    )
    batch_active_profile = (
        batch_profiles.get(batch_chosen_profile, {}) if batch_chosen_profile != "(none)" else {}
    )
    batch_brand_text = (
        profile_to_prompt_block(batch_active_profile) if batch_active_profile else ""
    )

    csv_file = st.file_uploader("Upload your product CSV", type=["csv"], key="b_upload")

    if csv_file is not None:
        try:
            input_df = pd.read_csv(csv_file)
        except Exception as e:
            st.error(f"Couldn't read that CSV: {e}")
            input_df = None

        if input_df is not None:
            problems = validate_columns(input_df)
            if problems:
                for p in problems:
                    st.error(p)
            else:
                st.write(f"Preview ({len(input_df)} rows):")
                st.dataframe(input_df.head(5), use_container_width=True)

                if st.button("🚀 Generate for all rows", type="primary"):
                    progress_bar = st.progress(0.0, text="Starting...")

                    def _update_progress(done: int, total: int) -> None:
                        progress_bar.progress(
                            done / total, text=f"Generated {done} of {total} products..."
                        )

                    try:
                        result_df, total_cost = run_batch(
                            df=input_df,
                            model_id=model_id,
                            style=batch_style,
                            platform=batch_platform,
                            length=batch_length,
                            brand_profile_text=batch_brand_text,
                            include_title_bullets=batch_title_bullets,
                            target_language=batch_language,
                            progress_callback=_update_progress,
                        )
                        add_to_session_cost(total_cost)
                        progress_bar.progress(1.0, text="Done!")
                        st.session_state["batch_result"] = {
                            "df": result_df,
                            "cost": total_cost,
                        }
                        # Same reason as Single Product: rerun so the sidebar's
                        # cost metric reflects the new total immediately.
                        st.rerun()
                    except (
                        anthropic.AuthenticationError,
                        anthropic.RateLimitError,
                        anthropic.APIConnectionError,
                        GenerationError,
                        anthropic.APIError,
                    ) as e:
                        handle_generation_error(e)

    saved_batch = st.session_state.get("batch_result")
    if saved_batch is not None:
        result_df = saved_batch["df"]
        total_cost = saved_batch["cost"]
        error_count = (result_df["error"] != "").sum()
        if error_count:
            st.warning(
                f"{error_count} row(s) had an error and are marked in the "
                "'error' column - the rest completed fine."
            )
        st.success(
            f"Generated {len(result_df) - error_count} description(s). "
            f"Estimated cost: {format_cost(total_cost)}."
        )
        st.dataframe(result_df, use_container_width=True)
        st.download_button(
            "⬇️ Download results as CSV",
            data=result_df.to_csv(index=False),
            file_name="product_descriptions.csv",
            mime="text/csv",
            key="batch_dl",
        )


# ===========================================================================
# TAB 3 - Brand Voice profiles
# ===========================================================================
with tab_brand:
    st.subheader("Reusable brand voice profiles")
    st.caption(
        "Save a brand's tone, banned words, and go-to phrases once. Pick it from "
        "the 'Brand voice profile' dropdown in Single Product or Batch to apply it "
        "to every listing."
    )

    profiles = load_profiles()
    profile_names = ["(create new)"] + sorted(profiles.keys())
    editing = st.selectbox("Load a profile to edit, or create a new one", profile_names)

    is_existing = editing != "(create new)"
    loaded = profiles.get(editing, {}) if is_existing else {}

    # Reload the form fields whenever the selection changes.
    if st.session_state.get("_bv_last_loaded") != editing:
        st.session_state["bv_name"] = editing if is_existing else ""
        st.session_state["bv_tone"] = loaded.get("tone_description", "")
        st.session_state["bv_banned"] = ", ".join(loaded.get("banned_words", []))
        st.session_state["bv_phrases"] = ", ".join(loaded.get("preferred_phrases", []))
        st.session_state["bv_extra"] = loaded.get("extra_instructions", "")
        st.session_state["_bv_last_loaded"] = editing

    profile_name = st.text_input(
        "Profile name", key="bv_name", placeholder="e.g. Cabin Nights Candle Co."
    )
    tone_description = st.text_area(
        "Tone description",
        key="bv_tone",
        placeholder="e.g. Warm, cozy, a little playful. Never corporate.",
        height=80,
    )
    banned_words_raw = st.text_input(
        "Banned words (comma-separated)",
        key="bv_banned",
        placeholder="e.g. cheap, discount, basic",
    )
    preferred_phrases_raw = st.text_input(
        "Preferred phrases / CTAs (comma-separated)",
        key="bv_phrases",
        placeholder="e.g. Light it up tonight, Handmade with love",
    )
    extra_instructions = st.text_area(
        "Any other standing instructions",
        key="bv_extra",
        placeholder="e.g. Always mention it's plastic-free.",
        height=80,
    )

    col_save, col_delete = st.columns(2)
    if col_save.button("💾 Save profile", type="primary", use_container_width=True):
        new_name = profile_name.strip()
        if not new_name:
            st.warning("Give the profile a name first.")
        else:
            save_profile(
                new_name,
                {
                    "brand_name": new_name,
                    "tone_description": tone_description,
                    "banned_words": parse_comma_list(banned_words_raw),
                    "preferred_phrases": parse_comma_list(preferred_phrases_raw),
                    "extra_instructions": extra_instructions,
                },
            )
            # Renamed an existing profile? Remove the old entry so we don't
            # end up with both "Cabin Co." and "Cabin Co V2" side by side.
            if is_existing and editing != new_name:
                delete_profile(editing)
            st.session_state["_bv_last_loaded"] = None
            st.success(f"Saved '{new_name}'.")
            st.rerun()

    if is_existing:
        if col_delete.button("🗑️ Delete this profile", use_container_width=True):
            delete_profile(editing)
            st.session_state["_bv_last_loaded"] = None
            st.rerun()


# ===========================================================================
# TAB 4 - History
# ===========================================================================
with tab_history:
    st.subheader("Past generations")
    st.caption("Every Single Product generation is saved here automatically (last 100).")

    entries = load_history()

    if not entries:
        st.info("Nothing generated yet - your results will show up here.")
    else:
        if st.button("🗑️ Clear history"):
            clear_history()
            st.rerun()

        for i, entry in enumerate(entries):
            title = entry.get("product_name", "(untitled)")
            when = entry.get("timestamp", "")
            with st.expander(f"{when} - {title} ({entry.get('style', '')})"):
                st.caption(
                    f"Platform: {entry.get('platform', '-')} - "
                    f"Length: {entry.get('length', '-')} - "
                    f"Model: {entry.get('model', '-')} - "
                    f"Brand voice: {entry.get('brand_profile', '(none)')}"
                )
                render_listing_result(
                    result=entry.get("result", {}),
                    banned_words=entry.get("banned_words", []),
                    include_title_bullets=entry.get("include_title_bullets", False),
                    platform=entry.get("platform", ""),
                    target_language=entry.get("target_language"),
                    key_prefix=f"hist_{i}",
                )
