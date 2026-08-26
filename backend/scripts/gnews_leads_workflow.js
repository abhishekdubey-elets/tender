// Multi-agent extraction workflow: Google News candidates -> verified govt-money leads.
//
// This is the middle step of the repeatable pipeline (see scripts/README_news_leads.md):
//   1. python -m scripts.news_leads fetch --out cand.json      (deterministic)
//   2. Workflow({ scriptPath: this file, args: <contents of cand.json> })   (this)
//   3. python -m scripts.news_leads persist --leads leads.json  (to the dashboard)
//
// It is invoked from Claude Code (the extraction needs a model). `args.bySector`
// is { "<vertical>": [ {title, source, date}, ... ] } — exactly what step 1 writes.
// Returns { leads:[...ranked...], dropped_as_noise, notes }.

export const meta = {
  name: 'gnews-govmoney-leads',
  description: 'Extract government-money sponsorship leads from Google News across the 6 Elets verticals',
  phases: [
    { title: 'Extract', detail: 'per-vertical candidate extraction from headlines' },
    { title: 'Verify', detail: 'adversarial filter: real, government counterparty, in-ICP' },
    { title: 'Synthesize', detail: 'dedupe by company, rank, final lead list' },
  ],
}

const ICP = "e-Governance, Digital Learning, Pharma, eHealth, Banking, Finance"
const bySector = args.bySector
const VERTICALS = Object.keys(bySector)

const CANDIDATES_SCHEMA = {
  type: "object",
  properties: {
    candidates: {
      type: "array",
      items: {
        type: "object",
        properties: {
          company: { type: "string" },
          government_buyer: { type: "string" },
          amount: { type: "string" },
          what_won: { type: "string" },
          is_government: { type: "boolean" },
          in_icp: { type: "boolean" },
          source: { type: "string" },
          date: { type: "string" },
          confidence: { type: "number" },
          note: { type: "string" },
        },
        required: ["company", "is_government", "in_icp", "confidence"],
      },
    },
  },
  required: ["candidates"],
}

const VERIFIED_SCHEMA = {
  type: "object",
  properties: {
    leads: {
      type: "array",
      items: {
        type: "object",
        properties: {
          company: { type: "string" },
          vertical: { type: "string" },
          government_buyer: { type: "string" },
          amount: { type: "string" },
          what_won: { type: "string" },
          reason_to_call: { type: "string" },
          source: { type: "string" },
          date: { type: "string" },
          confidence: { type: "number" },
        },
        required: ["company", "vertical", "reason_to_call", "confidence"],
      },
    },
    dropped: { type: "number" },
  },
  required: ["leads"],
}

const FINAL_SCHEMA = {
  type: "object",
  properties: {
    leads: {
      type: "array",
      items: {
        type: "object",
        properties: {
          rank: { type: "number" },
          company: { type: "string" },
          vertical: { type: "string" },
          government_buyer: { type: "string" },
          amount: { type: "string" },
          what_won: { type: "string" },
          reason_to_call: { type: "string" },
          source: { type: "string" },
          date: { type: "string" },
          confidence: { type: "number" },
        },
        required: ["rank", "company", "vertical", "reason_to_call"],
      },
    },
    dropped_as_noise: { type: "number" },
    notes: { type: "string" },
  },
  required: ["leads"],
}

const extractPrompt = (v, items) => `You are a sales-intelligence analyst for Elets Technomedia, which runs government-sector conferences and sells event sponsorships. Target ICP vertical: ${v} (one of Elets' six: ${ICP}).

Below are recent India news headlines. Identify companies that JUST WON GOVERNMENT MONEY relevant to ${v} — a company that received or won a government / PSU / ministry contract, work order, tender award, or a PLI/scheme incentive disbursement.

Be STRICT. EXCLUDE: stock-watch / "stocks to watch" lists, market-size or opinion/analysis pieces, personnel appointments, pure policy launches with no winning company, purely foreign-government deals (e.g. Malawi, Nigeria), and any deal whose counterparty is NOT an Indian government/PSU/ministry body (a private B2B deal does not count; a defence/DRDO order is out of this ICP).

Headlines (JSON):
${JSON.stringify(items)}

Return candidates. Set is_government=true only if the counterparty is clearly an Indian govt/PSU/ministry body; in_icp=true only if it fits ${v} or another of Elets' six verticals. Include the amount if stated, a short what_won, the source, date, a 0..1 confidence, and a brief note on any uncertainty.`

const verifyPrompt = (v, candidates) => `Adversarially verify these candidate leads for Elets vertical "${v}". For each candidate decide KEEP or DROP.

DROP if any of: the counterparty is not clearly an Indian government/PSU/ministry body; it is a stock tip / market report / opinion / appointment; the company or the award is unclear or unnamed; it is a foreign (non-India-government) deal; or it is outside Elets' ICP (${ICP}). Defence/DRDO and pure private B2B are OUT.

For each KEPT lead, write a crisp one-line reason_to_call in Elets' sponsorship voice: congratulate <company> on winning <amount> in government business (<what_won>) and invite them to sponsor the Elets ${v} summit to get in front of the government buyers who attend.

Candidates (JSON):
${JSON.stringify(candidates)}

Return ONLY the kept leads (vertical="${v}"), plus a count of how many you dropped. Keep confidence honest — these are news-sourced and unverified against the official document.`

// pipeline: extract then verify, per vertical, no barrier between them
const perVertical = await pipeline(
  VERTICALS,
  (v) => agent(extractPrompt(v, bySector[v]), { label: `extract:${v}`, phase: 'Extract', schema: CANDIDATES_SCHEMA })
           .then(r => ({ v, candidates: (r && r.candidates) || [] })),
  (ex) => agent(verifyPrompt(ex.v, ex.candidates), { label: `verify:${ex.v}`, phase: 'Verify', schema: VERIFIED_SCHEMA })
            .then(r => ({ v: ex.v, leads: (r && r.leads) || [], dropped: (r && r.dropped) || 0 })),
)

const kept = perVertical.filter(Boolean)
const allLeads = kept.flatMap(r => r.leads)
const droppedInVerify = kept.reduce((s, r) => s + (r.dropped || 0), 0)
log(`Verified ${allLeads.length} leads across ${kept.length} verticals; ${droppedInVerify} dropped as noise in verify.`)

const synth = await agent(
  `You are consolidating verified government-money sponsorship leads across verticals for Elets Technomedia.

Deduplicate by company + award: multiple headlines about the SAME award are ONE lead (e.g. several CMS Info Systems / SBI stories = one lead; two Venus Remedies PLI stories = one). Merge the best details.

Rank the final list by a blend of deal size, recency, and confidence (biggest, freshest, most-certain first). Assign rank starting at 1.

Return the final ranked leads with all fields, plus dropped_as_noise = ${droppedInVerify} (noise removed during verification) and a one-line notes field reminding that these are news-sourced (authority ~0.65) and should be cross-checked against the official government document before outreach.

Verified leads (JSON):
${JSON.stringify(allLeads)}`,
  { label: 'synthesize', phase: 'Synthesize', schema: FINAL_SCHEMA },
)

return synth
