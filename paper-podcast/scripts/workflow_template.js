// Workflow TEMPLATE: section-by-section read-along podcast from one or more papers.
// Phase 1 outlines each PDF into sections (with page ranges). JS then allocates a
// per-section WORD BUDGET from TARGET_MINUTES (a FOCUS area gets extra weight).
// Phase 2 writes each section with its own subagent (reads only its pages).
// Phase 3 stitches them into one continuous script with intro/outro + bridges.
//
// Inline the PDF paths into `FILES` below — DO NOT pass them via Workflow `args`
// (objects get stringified there, so args.* comes back undefined).
export const meta = {
  name: 'paper-podcast-sections',
  description: 'Section-by-section read-along podcast: subagent per section, target-time word budget, optional focus area',
  phases: [
    { title: 'Outline', detail: 'one subagent per PDF -> ordered sections + page ranges' },
    { title: 'Write', detail: 'one subagent per section, budgeted word count' },
    { title: 'Stitch', detail: 'assemble into one continuous script' },
  ],
}

// >>> EDIT: absolute paths to the PDFs (paste from `find <dir> -iname '*.pdf'`)
const FILES = [
  // "/abs/path/paper.pdf",
]

// >>> EDIT: framing
const TOPIC = "<one-line topic>"
const AUDIENCE = "expert researchers; read-paper-with-me register, technically precise, not public-facing, not casual"

// >>> EDIT: length + pacing
const TARGET_MINUTES = 20
const WPM = 167                 // calibrated for the Gemini TTS voice (file words / audio minutes)
const TOTAL_WORDS = Math.round(TARGET_MINUTES * WPM)

// >>> EDIT: optional focus. "" = even coverage. Otherwise these topics get more time.
const FOCUS = ""
const FOCUS_WEIGHT = 2.4        // budget multiplier for sections matching FOCUS
const MIN_SECTION_WORDS = 180   // floor so no section is too thin to be worth a subagent

const OUTLINE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['title', 'sections'],
  properties: {
    title: { type: 'string', description: 'Paper title and venue/year if visible' },
    sections: {
      type: 'array',
      description: 'Ordered sections suited to a spoken read-along (merge/split the paper structure as needed; 6-12 sections)',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'pages', 'notes', 'focusMatch'],
        properties: {
          title: { type: 'string', description: 'Short section title for the episode' },
          pages: { type: 'string', description: 'PDF page range to read for this section, e.g. "5-7"' },
          notes: { type: 'string', description: '3-6 sentences of the key technical content, numbers, and any caveats. Do not invent numbers.' },
          focusMatch: { type: 'boolean', description: 'True if this section is squarely about the FOCUS topic stated in the prompt' },
        },
      },
    },
  },
}

phase('Outline')
const outlines = await parallel(FILES.map((f, i) => () =>
  agent(
    `Read the research paper at ${f} with the Read tool (use the pages parameter; read the whole paper across several calls). ` +
    `Produce an ordered sectioning suited to a spoken "read-paper-with-me" episode for ${AUDIENCE}. ` +
    `For each section give a page range, dense technical notes (real numbers only, never invented), and set focusMatch. ` +
    (FOCUS ? `FOCUS topic = "${FOCUS}". Mark focusMatch=true for sections squarely about it; you may split the paper finer there so those parts can get more airtime.` : `No focus topic; aim for even coverage.`),
    { label: `outline:${f.split('/').pop()}`, phase: 'Outline', schema: OUTLINE_SCHEMA, model: 'sonnet' }
  )
))

let sections = outlines.filter(Boolean).flatMap((o, fi) =>
  o.sections.map(s => ({ ...s, file: FILES[fi], paperTitle: o.title }))
)

// JS budget allocation: focus sections weighted up, then a per-section floor.
const weights = sections.map(s => (FOCUS && s.focusMatch) ? FOCUS_WEIGHT : 1)
const wsum = weights.reduce((a, b) => a + b, 0)
sections = sections.map((s, i) => ({ ...s, words: Math.max(MIN_SECTION_WORDS, Math.round(TOTAL_WORDS * weights[i] / wsum)) }))
const planned = sections.reduce((a, s) => a + s.words, 0)
log(`${TARGET_MINUTES} min -> ~${TOTAL_WORDS} words across ${sections.length} sections (planned ${planned}). Focus: ${FOCUS || 'none'}.`)
sections.forEach(s => log(`  ${s.focusMatch ? '*' : ' '} ${s.words}w  ${s.title}`))

const outlineForWriters = sections.map((s, i) => `${i + 1}. ${s.title}`).join('\n')

phase('Write')
const written = await parallel(sections.map((s, idx) => () =>
  agent(
    `You are writing ONE section of a continuous "read-paper-with-me" podcast script for ${AUDIENCE}.\n\n` +
    `Paper: ${s.paperTitle}\nPDF: ${s.file}\nRead pages ${s.pages} with the Read tool (pages parameter) before writing.\n\n` +
    `Your section: "${s.title}". Target length: ~${s.words} words (this matters — write to the budget, it sets the episode pacing).\n` +
    `Key content to cover (do not invent numbers beyond what the paper states): ${s.notes}\n\n` +
    `Full episode outline so you know your place and avoid re-explaining other sections:\n${outlineForWriters}\n\n` +
    `Style: technically precise, expert register, read-paper-with-me (walk through the actual design choices and push on weak evidence). ` +
    `Not casual, no public-facing hand-holding, but spoken-word continuous prose (no bullet lists, no math symbols spelled as LaTeX). ` +
    `Write ONLY the body of your section as flowing narration. Do NOT add an intro/outro or a section header — the stitcher handles those. ` +
    `Do not restate the paper's whole thesis; assume earlier sections set it up.`,
    { label: `write:${s.title}`.slice(0, 60), phase: 'Write', model: 'sonnet' }
  )
))

const drafted = sections.map((s, i) => ({ ...s, body: written[i] })).filter(s => s.body)

phase('Stitch')
const assembled = drafted.map(s => `[${s.title}]\n${s.body}`).join('\n\n')
const script = await agent(
  `Below are the drafted sections of a single-host "read-paper-with-me" episode for ${AUDIENCE}, in order. ` +
  `Assemble them into ONE continuous script of about ${TOTAL_WORDS} words.\n\n` +
  `RULES:\n` +
  `- Do NOT summarize or shorten the section bodies. Preserve their technical detail and length — the word budget is intentional.\n` +
  `- Add a short spoken intro (name the paper + the one-line thesis + what this episode dwells on) and a short outro.\n` +
  `- Add 1-2 sentence bridges between sections so it flows as one monologue.\n` +
  `- Remove only true duplication (e.g. the same term defined twice) and fix contradictions.\n` +
  `- Keep section headers as [bracketed] lines (the TTS step strips these so they are silent).\n` +
  `- Spoken-word prose only: no bullet lists, no markdown tables, no LaTeX.\n\n` +
  `=== SECTIONS ===\n${assembled}`,
  { label: 'stitch', phase: 'Stitch', model: 'sonnet' }
)

return { script, target_minutes: TARGET_MINUTES, target_words: TOTAL_WORDS, sections: sections.map(s => ({ title: s.title, words: s.words, focus: !!s.focusMatch })) }
