# API research agent: 100 apps, one case study

An agent researches 100 apps (auth, self-serve vs gated, API, MCP, buildability, evidence), a second pass verifies it, and `index.html` shows patterns, table and accuracy.

## Run
```
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY, then: export $(cat .env | xargs)
python pipeline.py one "Stripe"   # test one app
python pipeline.py pass1          # research all 100 (resumable)
python pipeline.py pass2          # verifier re-checks every field
python pipeline.py sample         # 30-app stratified sample -> results/sample.csv
# Fill the h_* columns BY HAND from real docs before looking at agent columns.
python pipeline.py analyze        # writes data.js; open index.html
python pipeline.py bundle         # dist/index.html: one file with data inlined (deploy this)
```
Optionally write `notes.md` (what a human fixed, which apps defeated the agent). Deploy the folder (index.html + data.js) to GitHub Pages or Netlify.

## Notes
- Accuracy numbers on the page come only from your hand-checked sample. Nothing is pre-filled.
- Composio angle: swap the web_search tool in `call()` for Composio tools (Firecrawl/Exa) via the Composio SDK, and say so on the page.
- Never commit `.env`.
