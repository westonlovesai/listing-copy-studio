# 🛍️ Listing Copy Studio

An AI tool that turns product details and photos into ready-to-paste listing copy
for Etsy, Amazon, Shopify, eBay, real estate, or social — one product at a time,
or a whole catalog at once. Built with Claude.

**The problem it solves:** small sellers and stores waste hours writing product
descriptions, a lot of AI-written copy is instantly recognisable (em dashes,
"elevate your", "in today's fast-paced world"), and doing it one listing at a
time doesn't scale to a real catalog.

---

## What it does

### ✍️ Single Product
- **8 writing styles**, 6 platforms, 3 lengths.
- **Reads product photos** with Claude's vision so the copy matches what's really there.
- **Title + 5 feature bullets** on request, with a live character-limit check per platform.
- **Translate to a second language** as a native rewrite, not a literal translation.
- **Never uses em dashes or common AI tells** — enforced in two layers (see below).
- **One-click copy** (built into every result box), **download as .txt**, and live
  word/character counts.

### 📦 Batch (CSV)
- Upload a spreadsheet of products (a starter template is one click away),
  generate a description — plus title/bullets and a translation if you want —
  for every row, and download the results as CSV.
- One bad row never kills the batch: errors are recorded per-row so the rest
  of the catalog still completes.

### 🎙️ Brand Voice profiles
- Save a brand's tone, banned words, and go-to phrases once as a named profile.
- Apply it from a dropdown in Single Product or Batch mode — no retyping.
- Banned words are actively checked in every result and flagged if one slips through.

### 🕘 History
- Every Single Product generation is saved locally and automatically, so a
  good result is never lost just because you navigated away.

### 💵 Cost tracker
- A running, honest estimate of session spend in the sidebar, based on
  published per-token pricing (including the discount for cached tokens).

---

## How to run it

1. Install Python 3.10+.
2. In this folder, install the dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Get an Anthropic API key from https://console.anthropic.com, then:
   - copy `.env.example` to a new file called `.env`
   - paste your key after `ANTHROPIC_API_KEY=`
4. Start the app:
   ```
   streamlit run app.py
   ```
   It opens in your browser.

### Running the tests

```
pip install -r requirements-dev.txt
pytest
```

`tests/test_sanitize.py` proves the "no em dashes" guarantee and the
banned-word detector both hold, including edge cases (idempotency, whole-word
matching so "cap" doesn't false-positive inside "capable").

---

## How the two "no AI tells" layers work (the interesting bit)

1. **The prompt** (`prompts.py`) tells the model to avoid em dashes and a list of
   giveaway phrases. Prompts are persuasion, not a guarantee.
2. **The code** (`sanitize.py`) runs on every result and *guarantees* no em/en dashes
   survive, converting them to commas or hyphens and normalising smart quotes. The UI
   even shows a ✅ to prove it held, and a real pytest suite backs it up.

Banned words from a Brand Voice profile use the opposite approach on purpose:
they're **detected and flagged**, not silently deleted, because yanking a whole
word out of a sentence can wreck the grammar in a way stripping a dash never does.

## How it's built

| File | What it does |
|------|--------------|
| `app.py` | The Streamlit UI: four tabs (Single Product, Batch, Brand Voice, History). |
| `generation.py` | The single place that calls Claude: builds the dynamic JSON schema and sanitizes every result. Used by both Single Product and Batch. |
| `prompts.py` | The marketing "backbone": system prompt, styles, platforms, lengths, title-limit guidelines, and prompt assembly. |
| `sanitize.py` | The em-dash/AI-tell guarantee, plus banned-word detection, in plain Python. |
| `brand_profiles.py` | CRUD for reusable, structured brand voice profiles (`brand_profiles.json`). |
| `history.py` | Auto-saves every Single Product generation (`history.json`, capped at 100). |
| `costs.py` | Per-model pricing table and cache-aware cost estimation. |
| `batch.py` | CSV batch processing: validation, per-row generation, per-row error handling. |
| `tests/test_sanitize.py` | pytest suite proving the core guarantees hold. |

Other touches worth mentioning in a portfolio: Claude's **vision** (image input),
**structured JSON output** with a schema that changes shape based on what the user
asked for, and **prompt caching** on the system prompt so repeated generations
(especially in batch mode) cost less.
