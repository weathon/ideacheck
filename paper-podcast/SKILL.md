---
name: paper-podcast
description: Turn research papers (PDFs) into a single-person podcast/read-along, then optionally render it to audio. Use when the user wants to "make a podcast from these papers", a spoken walkthrough of a paper, or to get up to speed by listening. Fans out one subagent PER SECTION via a Workflow, budgets each section's length from a target time, supports an optional focus area, then converts to MP3 via OpenRouter Gemini TTS.
---

# Paper → Podcast

Two stages: (1) a Workflow outlines each PDF into sections, writes each section with its own subagent (length budgeted from a target time), and stitches them into one script; (2) a Python script renders it to MP3 via OpenRouter TTS. Stage 2 is optional — skip if the user only wants text.

The template is section-based, which is what makes a long, detailed, "read-paper-with-me" episode work: one subagent per section reads only its pages and writes to a word budget, so coverage stays even and you can scale length up without one agent compressing everything.

## Stage 0 — ask the user for audience + length

Unless the user already specified them, ask with **AskUserQuestion** (one call, two questions) before building:

- **Audience / register** → sets `AUDIENCE`:
  - *Expert (read-paper-with-me)* — technically precise, walks design choices, pushes on weak evidence. Use the default expert string in the template.
  - *General public* — explains jargon on first use, motivates why it matters, lighter on equations.
- **Length** → sets `TARGET_MINUTES`:
  - *Short* ≈ 10 min, *Medium* ≈ 20 min, *Long* ≈ 40 min. (Custom: take the user's number.)

Also honor a **focus area** if the user names one (→ `FOCUS`). If they already gave audience/length/focus in the prompt, skip the question and use what they said.

## Stage 1 — papers → script (Workflow)

1. **List the PDFs** in the target dir: `find <dir> -maxdepth 2 -iname '*.pdf'`. Confirm the dir with the user if not given.
2. **Copy** `scripts/workflow_template.js` to a working path and edit the config block at the top:
   - `FILES` — inline the absolute PDF paths. **Critical:** inline them in the script body, NOT via the Workflow `args` field (objects get stringified there, so `args.*` arrives `undefined`).
   - `TOPIC`, `AUDIENCE` — framing/register. For "read-paper-with-me / expert" asks, keep the default expert audience string.
   - `TARGET_MINUTES` — the user's target runtime. The script computes `TOTAL_WORDS = TARGET_MINUTES * WPM` and hands every section a slice of that budget. **WPM ≈ 167** for the current Gemini TTS voice (measured: file `wc -w` ÷ audio minutes; recalibrate if you change voice/model). So ~20 min ≈ 3300 words, ~40 min ≈ 6700 words.
   - `FOCUS` — optional. A topic the user is most interested in (e.g. "how the data is collected and how the model is trained"). Sections the outliner marks as matching get `FOCUS_WEIGHT`× the word budget, so the episode dwells there while still covering the rest. Leave `""` for even coverage.
3. **Run** it: `Workflow({ scriptPath: "<your copy>.js" })`. Three phases: outline each PDF (one subagent per paper → sections + page ranges), then write each section (one subagent per section, in parallel, each reads only its pages), then one stitch agent assembles intro/outro + bridges. All subagents use `model: 'sonnet'` for speed. It runs in the background and notifies on completion. `/workflows` shows live per-section progress.
4. **Extract the script** from the result JSON to a `.md`:
   ```python
   import json
   d = json.load(open("<task-output-file>"))
   open("podcast.md", "w").write(d["result"]["script"])
   ```

Scale via `TARGET_MINUTES` and `FOCUS`. For "be comprehensive", raise `TARGET_MINUTES` (more per-section budget) rather than adding agents. To recalibrate WPM, divide a finished script's `wc -w` by its rendered audio length in minutes.

## Stage 2 — script → audio (OpenRouter TTS)

Run `scripts/tts.py`:
```bash
python scripts/tts.py podcast.md -o podcast.mp3 --voice Zephyr --concurrency 10
```
The script needs an OpenRouter API key. **Ask the user** where their key is (env var, `.env` file path, or paste) — do not assume a hardcoded path. Pass it via `--key` or export `OPENROUTER_API_KEY` before running. Key resolution: `--key` → `$OPENROUTER_API_KEY`.

Chunks are fetched **concurrently** (`--concurrency`, default 10) with a live progress bar on stderr (done/total, elapsed, ETA); the PCM is still concatenated in chunk order so output is identical to a serial run. Raise concurrency for long scripts; lower it if you hit rate limits.

The script bakes in the hard-won gotchas:
- **Endpoint:** `POST https://openrouter.ai/api/v1/audio/speech`, model `google/gemini-3.1-flash-tts-preview`.
- **Voice must be a Gemini voice** — `Zephyr`, `Kore`, `Puck`, `Charon`, `Fenrir`, `Aoede`. OpenAI names like `alloy` return **HTTP 500** (auth/model are fine; the voice is the problem).
- **Output is raw PCM** (`audio/pcm`, s16le, 24 kHz, mono), NOT mp3 despite any `.mp3` in OpenRouter's example. The script concatenates raw PCM across chunks and encodes once with `ffmpeg -f s16le -ar 24000 -ac 1`. Needs `ffmpeg` on PATH.
- **Per-request `timeout=120`** is mandatory — a request with no timeout can hang indefinitely (we lost ~12 min to one stuck call).
- **Per-chunk PCM caching** under `<input>_ttsparts/` → an interrupted run resumes for free; delete that dir to force a clean re-render.
- **`[bracket]` headers stripped** so `[intro]`/`[theme: ...]` aren't read aloud.
- Text is chunked at paragraph boundaries (`--max-chars`, default 2000); the endpoint's per-call input cap is the reason.

## Notes
- `google/gemini-3.1-flash-tts-preview` is the working TTS model on OpenRouter; the OpenAI audio models are not exposed on the `/audio/speech` endpoint. Verify available models with `GET /api/v1/models` if it 400s with "does not exist".
- To change narrator, just pass a different `--voice`. To preview voices, render one short paragraph first.
