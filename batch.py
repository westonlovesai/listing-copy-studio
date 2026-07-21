"""
batch.py
--------
Runs the generator across a whole spreadsheet of products instead of one at
a time. This is what turns the tool from "a demo for one listing" into
"something a real seller with a 50-product catalog could actually use".

Deliberately kept Streamlit-free (no `import streamlit`) so this logic is
easy to test and reuse outside the web UI. app.py passes in a small
`progress_callback` if it wants a progress bar.
"""

import pandas as pd

from costs import estimate_cost
from generation import generate_listing
from prompts import build_user_prompt

REQUIRED_COLUMNS = ["product_name", "details"]


def make_template_csv() -> str:
    """A starter CSV the user can download, fill in, and re-upload."""
    df = pd.DataFrame(
        {
            "product_name": ["Nimbus 2P Backpacking Tent", "Cabin Nights Soy Candle"],
            "details": [
                "2-person 3-season tent, 2.4kg, freestanding aluminium poles, "
                "5 minute pitch, two doors and vestibules, 3000mm waterproof rainfly.",
                "Hand-poured soy wax candle, 8oz amber glass jar, ~45 hour burn, "
                "cedarwood and woodsmoke scent, cotton wick, reusable jar.",
            ],
        }
    )
    return df.to_csv(index=False)


def validate_columns(df: pd.DataFrame) -> list[str]:
    """Return a list of problems, empty if the file is usable."""
    problems = []
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            problems.append(f"Missing required column: '{col}'")
    return problems


def run_batch(
    df: pd.DataFrame,
    model_id: str,
    style: str,
    platform: str,
    length: str,
    brand_profile_text: str,
    include_title_bullets: bool,
    target_language: str | None,
    progress_callback=None,
) -> tuple[pd.DataFrame, float]:
    """Generate one listing per row. Returns (augmented_dataframe, total_cost_usd).

    A failure on one row is recorded in that row's 'error' column and does NOT
    stop the rest of the batch - a 40-row job shouldn't die because row 12 had
    a weird encoding issue.
    """
    result_df = df.copy()
    result_df["description"] = ""
    if include_title_bullets:
        result_df["title"] = ""
        result_df["bullets"] = ""
    if target_language:
        result_df["translated_description"] = ""
        if include_title_bullets:
            result_df["translated_title"] = ""
            result_df["translated_bullets"] = ""
    result_df["error"] = ""

    total_cost = 0.0
    total_rows = len(result_df)

    for position, (idx, row) in enumerate(result_df.iterrows(), start=1):
        product_name = str(row.get("product_name", "")).strip()
        details = str(row.get("details", "")).strip()

        try:
            prompt = build_user_prompt(
                product_name=product_name,
                details=details,
                style=style,
                platform=platform,
                length=length,
                brand_profile_text=brand_profile_text,
                custom_instructions="",
                num_variations=1,
                has_images=False,
                include_title_bullets=include_title_bullets,
                target_language=target_language,
            )
            result, usage = generate_listing(
                model_id=model_id,
                user_prompt=prompt,
                image_blocks=[],
                include_title_bullets=include_title_bullets,
                target_language=target_language,
            )
            total_cost += estimate_cost(model_id, usage)

            result_df.at[idx, "description"] = result["variations"][0]
            if include_title_bullets:
                result_df.at[idx, "title"] = result.get("title", "")
                result_df.at[idx, "bullets"] = " | ".join(result.get("bullets", []))
            if target_language:
                translated = result.get("translated", {})
                result_df.at[idx, "translated_description"] = (
                    translated.get("variations", [""])[0]
                )
                if include_title_bullets:
                    result_df.at[idx, "translated_title"] = translated.get("title", "")
                    result_df.at[idx, "translated_bullets"] = " | ".join(
                        translated.get("bullets", [])
                    )

        except Exception as e:  # noqa: BLE001 - a batch row error must never kill the batch
            result_df.at[idx, "error"] = str(e)

        if progress_callback:
            progress_callback(position, total_rows)

    return result_df, total_cost
