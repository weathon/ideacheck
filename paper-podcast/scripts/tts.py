#!/usr/bin/env python
"""Convert a podcast script (markdown/text) to a single MP3 via OpenRouter TTS.

OpenRouter /audio/speech gotchas this script handles:
  - Gemini TTS returns RAW PCM (s16le, 24kHz, mono), NOT mp3. We concat raw
    bytes across chunks and encode once with ffmpeg.
  - Voice must be a Gemini voice (Zephyr/Kore/Puck/Charon/...). OpenAI names
    like "alloy" return HTTP 500.
  - Each request needs a timeout; without one a stuck request hangs forever.
  - Per-chunk PCM is cached so a failed/interrupted run resumes for free.
  - [bracket] section headers are stripped so they aren't read aloud.
  - Chunks are fetched CONCURRENTLY (--concurrency, default 10) with a live
    progress bar; the final PCM is still concatenated in chunk order.

Usage:
  python tts.py INPUT.md -o OUT.mp3 --voice Zephyr
  python tts.py INPUT.md            # -> INPUT.mp3, default voice Zephyr
  python tts.py INPUT.md --concurrency 16
Key resolution order: --key  >  $OPENROUTER_API_KEY
"""
import argparse, os, re, sys, time, subprocess, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

GEMINI_VOICES = ["Zephyr", "Kore", "Puck", "Charon", "Fenrir", "Aoede"]


def load_key(cli_key):
    if cli_key:
        return cli_key
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    sys.exit("No key: pass --key or set $OPENROUTER_API_KEY")


def chunk_text(text, maxc):
    text = re.sub(r"^\s*\[[^\]]+\]\s*$", "", text, flags=re.M)  # drop [intro]/[theme:..]
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 > maxc and cur:
            chunks.append(cur); cur = p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        chunks.append(cur)
    return chunks


class Progress:
    """Thread-safe single-line progress bar on stderr."""
    def __init__(self, total, width=32):
        self.total, self.width, self.done = total, width, 0
        self.t0 = time.time()
        self.lock = threading.Lock()

    def start(self, done=0):
        self.done = done
        self._draw()

    def tick(self, n=1):
        with self.lock:
            self.done += n
            self._draw()

    def note(self, msg):
        with self.lock:
            sys.stderr.write("\r\033[K" + msg + "\n")
            self._draw()

    def _draw(self):
        frac = self.done / self.total if self.total else 1.0
        fill = int(frac * self.width)
        bar = "#" * fill + "-" * (self.width - fill)
        el = time.time() - self.t0
        rate = self.done / el if el > 0 else 0
        eta = (self.total - self.done) / rate if rate > 0 else 0
        sys.stderr.write(f"\r[{bar}] {self.done}/{self.total} ({frac*100:4.0f}%)  {el:5.0f}s  eta {eta:4.0f}s")
        sys.stderr.flush()

    def close(self):
        sys.stderr.write("\n"); sys.stderr.flush()


def fetch_chunk(i, c, fp, key, model, voice):
    for attempt in range(3):
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/audio/speech",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "input": c, "voice": voice},
                timeout=120,
            )
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if not ct.startswith("audio/pcm"):
                raise AssertionError(f"unexpected content-type: {ct}")
            fp.write_bytes(r.content)
            return i, None
        except Exception as e:
            if attempt == 2:
                return i, str(e)
            time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--voice", default="Zephyr", help=f"Gemini voice, e.g. {', '.join(GEMINI_VOICES)}")
    ap.add_argument("--model", default="google/gemini-3.1-flash-tts-preview")
    ap.add_argument("--max-chars", type=int, default=2000)
    ap.add_argument("--concurrency", type=int, default=10, help="parallel API calls (default 10)")
    ap.add_argument("--key", default=None)
    a = ap.parse_args()

    key = load_key(a.key)
    inp = Path(a.input)
    out = Path(a.output) if a.output else inp.with_suffix(".mp3")
    parts = inp.parent / (inp.stem + "_ttsparts")
    parts.mkdir(exist_ok=True)

    chunks = chunk_text(inp.read_text(), a.max_chars)
    fpaths = [parts / f"part_{i:03d}.pcm" for i in range(len(chunks))]
    todo = [i for i in range(len(chunks)) if not (fpaths[i].exists() and fpaths[i].stat().st_size > 0)]
    cached = len(chunks) - len(todo)
    print(f"{len(chunks)} chunks  ({cached} cached, {len(todo)} to fetch, concurrency {a.concurrency})", flush=True)

    bar = Progress(len(chunks))
    bar.start(done=cached)
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as ex:
        futs = [ex.submit(fetch_chunk, i, chunks[i], fpaths[i], key, a.model, a.voice) for i in todo]
        for f in as_completed(futs):
            i, err = f.result()
            if err:
                failures.append((i, err))
                bar.note(f"chunk {i} FAILED: {err}")
            bar.tick()
    bar.close()
    if failures:
        sys.exit(f"{len(failures)} chunk(s) failed: {[i for i, _ in failures]}")

    pcm = bytearray()
    for fp in fpaths:
        pcm += fp.read_bytes()
    raw = inp.parent / (inp.stem + "_full.pcm")
    raw.write_bytes(pcm)
    subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                    "-i", str(raw), "-b:a", "128k", str(out)], check=True, capture_output=True)
    raw.unlink()
    for fp in fpaths:
        fp.unlink()
    parts.rmdir()
    print("WROTE", out, flush=True)


if __name__ == "__main__":
    main()
