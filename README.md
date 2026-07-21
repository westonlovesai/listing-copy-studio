# 🛍️ Listing Copy Studio

An AI tool that turns product details and photos into ready-to-paste listing copy
for Etsy, Amazon, Shopify, eBay, real estate, or social. Built with Claude.

**The problem it solves:** small sellers and stores waste hours writing product
descriptions, and a lot of AI-written copy is instantly recognisable (em dashes,
"elevate your", "in today's fast-paced world"). This tool writes in the voice you
choose, avoids those tells, and lets you save the instructions you reuse.

---

## What it does

- **8 writing styles** (Luxury, Playful, Minimalist, SEO, Storytelling, Bold, Warm,
  Technical) plus 6 platforms and 3 lengths.
- **Never uses em dashes or common AI tells** — enforced in two layers (see below).
- **Free-form custom instructions** for anything the dropdowns don't cover.
- **Save presets:** reuse an instruction you type often with one click.
- **Reads product photos:** Claude looks at the images and writes copy that matches.
- **Generates up to 3 versions** at once so you can pick the best.

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

---

## How the two "no AI tells" layers work (the interesting bit)

1. **The prompt** (`prompts.py`) tells the model to avoid em dashes and a list of
   giveaway phrases. Prompts are persuasion, not a guarantee.
2. **The code** (`sanitize.py`) runs on every result and *guarantees* no em/en dashes
   survive, converting them to commas or hyphens and normalising smart quotes. The UI
   even shows a ✅ to prove it held.

That "belt and braces" design — prompt for intent, code for the guarantee — is a good
pattern for any AI product where output has to meet a hard rule.

## How it's built

| File | What it does |
|------|--------------|
| `app.py` | The Streamlit web UI and the call to Claude. |
| `prompts.py` | The marketing "backbone": system prompt + style/platform definitions. |
| `sanitize.py` | The guarantee: strips em/en dashes and AI-tell characters. |
| `presets.json` | Auto-created when you save your first preset. |

Other touches worth mentioning in a portfolio: it uses Claude's **vision** (image
input), **structured JSON output** so each version comes back cleanly separated, and
**prompt caching** on the system prompt so repeated generations cost less.
