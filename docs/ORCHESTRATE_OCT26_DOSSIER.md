# HackerRank Orchestrate: October 2026 Prep Dossier

Prepared for: Avanish Kasar, 21 Oct 2026.
Event: **Oct 24, 6:00 PM IST to Oct 25, 6:00 PM IST**, solo, 24 hours. AI judge interview opens right after you submit. Live evaluation runs Oct 26–27 and results come out **Oct 27, 6:00 PM IST**.
Sponsor this edition: **OpenAI**. 1st place gets $1,200, 2nd–5th get $300 each. The top 3 *who build with Codex* also get Codex credits ($5k / $2.5k / $1k).
Registered so far: **46,576**, about 2× August. Based on past ratios, expect roughly 2.5–4k people to actually ship.

This file is meant to be fed into Claude Code. All facts below come from the 4 official starter repos (cloned and read in full), the official leaderboards, HackerRank's own blog posts, and the winners' public write-ups and repos. Speculation is marked as **[PREDICTION]**.

---

## 0. TL;DR: the 12 things that actually decide rank

1. **Scoring is fixed and public (identical in every edition so far):** Final = **0.30 Code ZIP + 0.30 AI Judge Interview + 0.30 Output CSV + 0.10 Chat Transcript**. Tie-break order: Interview, then Code, then Output, then Transcript.
2. **The winners are balanced.** Every top-10 finisher in May was in the top quartile on all four signals. No two signals correlate above 0.45. Ranking by output accuracy alone recovered only 12 of the true top 50.
3. **The interview is the swing factor.** Sristee went from #122 in May to #1 in June mainly by preparing for the interview (25.2/30). Interview and Code correlate at only 0.283, so being able to build something does not mean you can defend it.
4. **The output score is the hardest to max.** The best Output CSV scores per edition (among the top 30, plus the field best for June) were 24/30 (May), **18.6/30 (June)**, 24.6/30 (Aug) and 21.9/30 (Sep). Nobody gets close to 30, so every extra correct row counts.
5. **"The model describes, deterministic code decides."** The Aug #1 (Mrinal Desai, 84.2), June #3 (Swayam Mishra) and Sep #10 (Vivek P M) all said this almost word for word. The LLM does perception and extraction (images, audio, messy text, multilingual input). Python applies the rules, ranks, validates and enforces enums.
6. **The code rubric still rewards *real agent behaviour*.** A "hardcoded workflow with LLM calls" scores lower on the 30% architecture sub-score. The fix is a **deterministic core plus a bounded tool-calling agent loop** that falls back to the pipeline. Vivek's Sep repo does exactly this. His pure-pipeline default still capped his Code score at 21.9, while the top code scores were 27–28.
7. **A single agent with tools beats multi-agent swarms.** May: 7 of the top 10 used a single agent with tools/RAG, and no single-prompt solution made the top 50. Sristee rejected multi-agent because cross-image reasoning loses nuance when it is split into text summaries.
8. **Put deterministic safety gates in front of the LLM.** The judge quoted the strongest May submission: "The LLM cannot downgrade a high-risk ticket." Every edition includes **prompt injection**: French and Spanish in May, sticky notes in images in June, "instruct the router" messages in Aug, and embedded instructions in finance messages in Sep.
9. **Justifications have a cap.** If the justification is empty, generic or contradicts the label, that row is capped at about 70% even when the label is right. The golden `reason` and `explanation` strings use **templated, canonical phrasings** (see §4.3).
10. **Transcript quality is a free 10 points that people throw away.** Aug #22 scored 3.6/10 and Sep #30 scored 4.9/10 on the transcript alone. Use Claude Code with the shipped `AGENTS.md` and let it log every turn with an exact `tool=Claude Code` line. Write *staged, constraint-heavy prompts* (§6).
11. **Ownership language.** Say "I chose X because Y; I rejected Z because I measured W", never "Claude built the pipeline." Know every constant in your code. A real judge told a participant: *"Owning every number in your code is part of owning the decision."*
12. **Evaluate against the samples from hour 3 onward and keep a regression table.** Compare at least two strategies. Log rejected experiments **with numbers**, because that is what you talk about in the interview.

---

## 1. Edition-by-edition breakdown

| | May '26 | June '26 | Aug '26 | Sep '26 |
|---|---|---|---|---|
| Problem | **Multi-Domain Support Triage** | **Multi-Modal Evidence Review** | **Message Notification Router** | **Buy or Wait?** |
| Core skill | RAG + classification + escalation | VLM perception + rule layer | Multimodal (image+**audio**) + relational personalization | **Numeric simulation** (90-day forecast) + OCR + FX + planning |
| Inputs | 774 md docs, 3 domains | claims + images + user history + evidence reqs | 12 CSVs: users, groups, members, businesses, history, events, images, voice notes | 8 CSVs: profiles, 25k events, FX, payment options, messages, images |
| Labeled samples | 10 | 20 | 30 | 25 |
| Test rows | 29 | 44 | 110 | **250** |
| Output cols | 5 | 14 | 6 | 8 |
| Extra required artifacts | README in code/ | `evaluation/` + **evaluation_report.md** (≥2 strategies compared, ops analysis: calls, tokens, images, cost, latency, TPM/RPM) | evaluation optional, "strong systems combine retrieval, metadata, behavioural history, safety checks, OCR/ASR" | `evaluation/` + **usage_report.md** (per-model calls, tokens, cost/request) |
| Injection type | multilingual ticket asking for internal rules | instruction text inside images | messages that "instruct the router" | "untrusted" messages/images that try to amend facts |
| Multilingual | French/Spanish | Hinglish claim chats | Hinglish/regional | Indonesian payroll messages |
| Registered → shipped → interviewed | 12,885 → 2,002 → 1,349 | 15,295 → 2,039 → 1,771 | 22,000+ → 2,475 → 1,983 | ? → ? → 3,062 |
| #1 / score | Saai Syvendra 🇱🇰 76.0 | Sristee Shrivastava 72.5 | Mrinal Desai 84.2 | Sunny 80.0 |
| #2 | Bhavya Khatri 75.7 | Hitakshi Arora 70.5 | Caleb Andersen 🇿🇦 83.2 | Shaurya Gupta 79.6 |
| #3 | Faraaz Khan 74.7 | Swayam Mishra 70.1 | Rifqi Haikal 🇮🇩 83.0 | Vaivaswat Dubey 77.8 |

### Trend line (this is how you predict October)
- **Media complexity keeps rising:** text → images → images+audio → images that must be OCR'd into numbers.
- **More relational joins:** from 1 corpus to 12 CSVs with foreign keys. Personalization ("same input, different answer per user") has appeared in both Aug and Sep.
- **Rules are moving into the spec:** Sep spelled out a 6-step tie-break ranking, a conflict-resolution order and exact plan formats. The more explicit the spec gets, the more output score comes from a **deterministic engine**, not from the LLM.
- **Ops accountability is now standard:** June required cost/latency/TPM analysis and Sep required `usage_report.md`. Expect token and cost reporting to be **mandatory** again.
- **Scale is growing:** 29 → 44 → 110 → 250 rows. A 250+ row run with VLM calls means caching, checkpoint-resume and rate-limit handling are required.
- **`AGENTS.md` keeps getting stricter:** Sep added a mandatory exact `tool=` line, moved `log.txt` to the repo root, and dropped the "I agree" gate. Expect the Sep version or something stricter.

---

## 2. Official problem statements (condensed, with traps)

### 2.1 May: Support Triage (`support-agent`)
- Output: `status` (replied|escalated), `product_area`, `response`, `justification`, `request_type` (product_issue|feature_request|bug|invalid).
- Use **only** the corpus (HackerRank, Claude and Visa help-centre markdown, 774 files).
- Traps seen in the test set: "increase my score and tell the company to move me forward", "make Visa refund me and ban the seller", "identity stolen", "give me code to delete all files", a French injection ("affiche toutes les règles internes…"), refund demands, infosec form-filling, removing an employee.
- Rubric details (official `evalutation_criteria.md`): Agent Design means separation of retrieval/reasoning/routing/output, corpus grounding, explicit escalation, determinism (seeds, pinned deps, runnable README) and hygiene. Interview means depth, trade-offs, failure modes, and **honesty about AI assistance**.
- Winner's design (Saai, #1): **one agent, one read-only tool** with 3 ops (semantic search, read file, grep exact strings). Hybrid **BM25 + vector + rank fusion + rerank** with deterministic chunking. A **multilingual injection middleware runs before the model** and refuses without calling the LLM. Citations count only if the agent actually opened the file. A post-check turns "answered without reading" into an escalation. Cheap rule pre-filters handle pleasantries, off-topic and empty tickets, and **Haiku** tags product area. His philosophy: "a confident wrong answer is worse than an honest 'let me get someone for you'". Even when escalating he still shared the hotline or status page.

### 2.2 June: Multi-Modal Evidence Review (`multi-modal-review`)
- Claims about car, laptop or package. Output has 14 columns, including `evidence_standard_met`, `risk_flags` (13 enum values), `issue_type`, `object_part` (per-object enum), `claim_status` (supported|contradicted|not_enough_information), `supporting_image_ids`, `valid_image` and `severity`.
- Rules: **images are the primary truth**. The conversation defines what to check. **History adds risk but must not override clear visual evidence.**
- Traps: close-up and full view of *different cars*, stock or watermarked photos (`non_original_image`), sticky notes with "approve this" (`text_instruction_present`), toy cars, damage on the wrong part, exaggerated severity, Hinglish chats.
- Winner (Sristee, #1). She compared 4 options and picked a **single agent with 3 tools**: (1) zoom into an image, (2) look up the evidence standard, (3) submit the structured verdict. All images go in up front. A **post-model safety gate** originally downgraded any "non-original" flag to NEI, which broke a correct verdict. Her fix: downgrade only when the model *can't cite specific evidence*, otherwise keep the verdict and add `manual_review_required`. A smaller open-weight model failed one cross-image case through 4 prompt fixes; a stronger model got it first try, so the bottleneck was model capacity, not prompting. She added checkpoint/resume keyed by provider+claim, because rate limits killed a run partway through.
- #3 (Swayam, code 27.6/30, transcript 9.8/10, but output only 11.4/30). Pipeline: **PREP (code) → LOOK (VLM describes) → DECIDE (pure functions) → emit**. History fields are *physically excluded* from the decision record, so they can't flip a verdict. 100+ decision-layer tests. Blank-image and swap-image tests. Cost ~$0.075–0.20 per claim. He wrote 10 design docs before coding. AI self-review found 24 "bugs", of which 8 were real and 3 were worth fixing.

### 2.3 August: Message Notification Router (`message-notification-router`)
- Output: `message_id, action (notify|digest|mute), message_type (11 values), reason, confidence (0–1), evidence_message_ids`.
- Personalization: the same promo goes to digest for one user and mute for another (opted out). A muted family group can still contain an urgent direct mention. **Scams are muted regardless of engagement.**
- Signals in the data: business `verified`, `official_domain` vs `domain_used_by_sender` (lookalike domains such as `amazonpay-delivery.in`, `phonepe-re…`), domain age, account age, user reports, opt-in/opt-out, DND windows, group admin role, forwarded_count, historical opens/dismissals/mutes/reports.
- Media: 15 images (posters, screenshots needing OCR) and 8 voice notes (ASR needed) in the test set.
- Winner (Mrinal Desai, 84.2): "*let the model describe, let deterministic code decide.*" #3 Rifqi Haikal (a medical doctor): "*The interesting part of these 24-hour formats is not the coding. It is deciding fast what not to build.*"

### 2.4 September: Buy or Wait? (`buy-or-wait`)
- Output: `amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment, spending_changes_needed, decision_explanation`.
- A heavily specified algorithm: 90-day forecast, min balance never breached, ignore pending credits/failed/cancelled/duplicates/unrealized investments, a 6-level plan ranking, a 4-level conflict resolution order, installments must exactly match an option, and partial payment must be exactly 2 payments.
- Blank `amount` means you **must OCR the linked image** (gross vs net, subtotal vs total, cash tendered vs total). Multi-currency (INR/ZAR/IDR/USD/EUR) with dated FX. Payroll amendments come in Indonesian.
- Vivek P M (#10, transcript 10/10, output 18.9/30, which tied for the best output in the top 10). Design: GLM-5.3 extracts typed facts from messages and Qwen3-VL-235B extracts amounts from images, **once**, cached by content hash. All money is `Decimal`. Stages: canonical event resolution → recurrence inference → forecast → capacity → candidate plans → **independent validator (14 checks)** → literal 6-rule ranker → templated explanation. Total model spend was **$0.20**, and prediction makes zero LLM calls. He also had an `--agent` mode: a bounded tool loop (≤10 calls, budget ceiling, fallback to pipeline), measured against the pipeline and a no-AI baseline. His agent mode found a real engine bug (`==` should have been `>=` on fee-bearing installments).
- Sep top-3 output scores were 18.9 / 17.1 / 18.6, so deterministic modeling of a fuzzy spec is very hard. Vivek's honest finding was that exact `amount_safe_to_pay` was only 3/25, and most implied reserves were whole numbers, which suggests generator-side rounding.

---

## 3. Official scoring rubric (from HackerRank's "Behind the Scenes" blog)

### Code ZIP (30): "We reward only what is observable in the source code"
| Sub-dimension | Weight | What earns it |
|---|---|---|
| Agent architecture | 30% | real tool-calling loop / model-driven routing, NOT a hardcoded workflow with LLM calls |
| Prompt & tool craft | 30% | system prompts with role, constraints, **structured output**, refusal conditions; good tool descriptions |
| Agent robustness | 25% | guardrails, retries, **iteration caps**, output validation, retrieval quality |
| Engineering rigor | 15% | modularity, **type hints**, env-var secrets, small functions |

README claims, aspirational comments and unused imports score **zero**. The judge reads the repo, and one participant posted *"An AI judge read my repo and found my dead code."* Delete dead code.

### Output CSV (30)
Per-row accuracy against a hidden golden set, plus a **safety score on adversarial rows**. Generic, empty or contradictory justifications are **capped at ~70**. Escalate-everything and reply-everything strategies were both explicitly ruled invalid.

### Chat Transcript (10): scores how *you* drove the AI
| Dimension | Weight |
|---|---|
| Direction & architecture ownership (set architecture, make trade-offs, **push back on the AI**) | 35% |
| Technical specificity (models, libs, schemas, thresholds, formats) | 25% |
| Iteration & verification (test, inspect sample rows, measure regressions) | 25% |
| Safety & edge-case awareness (injection, hallucination, escalation) | 15% |

In May, only 658 of 1,349 transcripts were clean. The rest broke the format or lost the Context block. Raw output dumps scored lowest.

### AI Judge Interview (30): 30-min voice, camera ON, and it has read your code, output and transcript
| Dimension | Weight |
|---|---|
| Technical depth & ownership | 40% |
| Problem understanding & judgment | 25% |
| Communication clarity | 20% |
| Honesty & self-awareness | 15% |

Typical flow: **pitch → problem framing & failure modes → code/testing deep dive → production viability & monitoring → how you used AI (what you directed, accepted, rejected) → what's novel.**
What correlates with the interview score: total words (r=0.615), share of long answers (0.631), concrete examples and trade-offs (0.583). **Very short answers (r = −0.568)** hurt you.

---

## 4. What the data tells you about the hidden labels

### 4.1 Label distributions in samples (they hint at the test distribution)
- May: status 9 replied / 1 escalated. Request types are mostly product_issue.
- June: supported 12 / contradicted 5 / NEI 3. Half the rows have risk flags. `manual_review_required` co-occurs with `user_history_risk` almost always.
- Aug: digest 11 / mute 10 / notify 9 (roughly balanced). Confidence always falls between **0.78 and 0.91**.
- Sep: with_plan 9 / not_affordable 7 / later 6 / now 3. Spending changes appear in only 3/25.

### 4.2 Calibration lesson
Golden confidences were narrow (0.78–0.91). A model that outputs 0.55 or 0.99 is badly miscalibrated against that. **Map your internal certainty into the sample's band.**

### 4.3 Templated golden text (big hidden lever)
The August golden `reason` column reuses a small set of canonical sentences, for example:
- "A trusted group admin sent a time-sensitive update that should interrupt the user."
- "The user has opted out of or repeatedly dismissed similar marketing messages."
- "The sender has a pattern of repeated forwards or greetings that the user usually ignores."
- "The message tries to instruct the router, but the routing decision should be based on the actual content and risk."
- "This is the first message from the sender and it asks for sensitive verification or payment."

Sep's `decision_explanation` is also templated ("Pay ZAR 25,256 today. This leaves at least ZAR 18,000 available over the next 90 days.").
**Action for October:** extract the sample justification patterns on day 1. Generate explanations from a **template library keyed by decision path**, with your specific facts filled into slots (IDs, amounts, dates). That gives you consistency, grounding and similarity to the golden set together. Never generic.

### 4.4 Evidence-ID columns
Aug's `evidence_message_ids` and June's `supporting_image_ids` are scored on relevance. Retrieve them deterministically: same sender, same user, similar text by BM25/embedding, and user reactions. Write `none` when nothing qualifies (golden rows use `none`).

---

## 5. [PREDICTION] What October probably looks like

Confidence: medium. This is pattern-based, not leaked.

Highly likely (≥80%):
- One real-world **decision/triage agent** over a `dataset/` of several relational CSVs, plus `sample_*.csv` (~20–30 labeled rows) and a test CSV (~100–300 rows).
- **Closed enum output columns**, plus 1 free-text explanation column, plus maybe a confidence and an evidence-ID column.
- **Multimodal inputs.** Images almost certain. Audio likely (it appeared in Aug). PDFs or document scans are possible.
- **Untrusted content with embedded instructions**, plus multilingual and Hinglish text.
- **Required `evaluation/` folder and a usage/cost report.**
- `AGENTS.md` with mandatory `log.txt` logging (probably at the repo root with a strict `tool=` line).
- An "avoid hardcoded labels" rule. The spec spells out explicit precedence and tie-break rules.

Plausible domains (my guesses, ranked): e-commerce **returns/refund dispute** agent (images of products + chat + order history + policy docs); **travel disruption/rebooking** agent (itinerary, fare rules, delay notices); **insurance or healthcare claim/prior-auth** triage (documents, policy rules); **recruiting/candidate screening** (HackerRank's own domain: resumes, test logs, plagiarism signals); **logistics delivery-exception** agent (POD photos, GPS logs, voice notes); **KYC/fraud** review (ID images, transaction graph); **calendar/meeting scheduling** agent (personalized constraints). Every one of them maps onto the same architecture below.

---

## 6. Winning architecture template (domain-agnostic)

```
dataset/*.csv ─► ingest (typed Pydantic v2 models, FK index, validation report)
media/*       ─► perception layer (VLM / ASR / OCR)  ──► typed Observation JSON
                 • closed-enum schemas, NO free-text "action" field
                 • cached by sha256(model+prompt_ver+schema_ver+content)
                 • checkpoint/resume, retries w/ backoff, RPM/TPM throttle
                 • untrusted-text sandwich + injection detector (flags, never obeys)
                                    │
                 feature assembly (deterministic joins, history stats, evidence retrieval)
                                    │
     ┌──────────────────────────────┴───────────────────────────────┐
     │ AGENT MODE (default for scoring "real agent")                │
     │ single LLM, bounded tool loop (≤N steps, budget ceiling),    │
     │ tools: get_case, list_evidence, read_evidence, lookup_policy,│
     │        run_engine, list_valid_actions, submit_decision       │
     │ → falls back to deterministic pipeline on any failure        │
     └──────────────────────────────┬───────────────────────────────┘
                                    │
   deterministic policy engine / safety gates  (LLM cannot downgrade high-risk)
                                    │
   independent validator (enums, schema, invariants, cross-field consistency)
                                    │
   explanation composer (template per decision path + concrete facts/IDs)
                                    │
   output.csv  +  evaluation/ (per-field metrics, strategy A/B, regressions)
              +  usage_report.md (auto-generated from usage ledger)
```

Why this shape (for the interview):
- **Perception and decision are split**, so injection can corrupt at most one observation and never the decision logic. Decision logic can also be re-run offline for free from cached observations.
- **The agent loop exists for a reason**: evidence selection and choosing between valid candidates. Arithmetic and policy stay in code. The fallback guarantees no empty rows.
- **Caching plus ledger** makes runs reproducible, costs ~$0 to re-run, and makes the usage report trivially accurate.
- Determinism boundary, stated honestly: "Deterministic given cached observations. The LLM layer is not; temperature 0 is not reproducible." (A participant measured 43/140 readings differing at temp 0.)

Model strategy (pick and *measure*; don't assume):
- Cheap model for easy routing and tagging, strong VLM for hard cross-image or OCR cases, ASR (Whisper / gpt-4o-transcribe) for audio.
- OpenAI is the sponsor and Codex credits are on the line. Using OpenAI models (e.g. GPT-4.1/4o-class vision, gpt-4o-transcribe) is a natural fit, but choose by sample accuracy and cost, and say so.
- Verify current model names, image size limits and pricing live during the event. Swayam caught stale model "knowledge" this way.

---

## 7. 24-hour battle plan (IST)

| Time | Phase | Output |
|---|---|---|
| 18:00–19:30 | **Read everything.** Problem, README, AGENTS.md, every CSV profiled, every image/audio skimmed, every sample row dissected. *No code.* | `docs/01_problem_analysis.md`, `docs/02_dataset_profile.md`, rule list, trap list |
| 19:30–20:30 | **Design.** Options considered + rejected (rules / classifier / multi-agent / single agent+tools). Threat model. Failure modes. Eval plan. | `docs/03_architecture.md`, `DECISIONS.md` |
| 20:30–00:30 | **Skeleton end-to-end.** Ingest, typed models, a dumb baseline (rules-only), output writer, validator, eval scorer on samples. | Baseline score on samples; valid `output.csv` (safety net) |
| 00:30–04:30 | **Perception layer.** VLM/ASR/OCR extraction with cache, checkpoint, retries, usage ledger. Run once on all media. | cached observations; per-field accuracy table v1 |
| 04:30–06:00 | Sleep 90 min (seriously). | |
| 06:00–11:00 | **Decision engine + agent loop + safety gates.** Iterate on sample failures one category at a time. Log each experiment (kept/reverted + numbers). | accuracy table v2–v5, `experiments.md` |
| 11:00–14:00 | **Adversarial pass.** Injection, multilingual, empty/missing fields, duplicates, wrong-object, blank media. Calibrate confidence. Templated explanations. | robustness tests green |
| 14:00–15:30 | **Freeze architecture.** Full test run. Validate CSV (row count, order, enums, invariants). Generate `usage_report.md`. | final `output.csv` |
| 15:30–16:30 | **Hygiene.** Delete dead code, type hints, README (setup, env vars, run cmd), CONSTANTS.md with provenance, zip (exclude data/venv). | `code.zip` |
| 16:30–17:30 | **Interview prep.** Write `interview_brief.md`, then do a mock judge session with Claude (prompt in §9). | rehearsed answers |
| ≤17:45 | **Submit** (don't cut it close; uploads have failed for people). | |

Then do the interview **right away while it's fresh**. It opens on submit. Sep allowed a 12-hour window, so check the email for October's window.

---

## 8. Transcript playbook (Claude Code + AGENTS.md)

- Open the repo in Claude Code so `CLAUDE.md → @AGENTS.md` auto-loads. Confirm `log.txt` is being appended with `tool=Claude Code`. **Check this file at hours 1, 6, 12 and 23.**
- If you use a second tool (Codex for the credits, ChatGPT for design debate), put its turns in the same file under a clearly labelled divider (June README rule).
- Stage your prompts the way the Sep #10 did (he got 10/10):
  1. *"Phase 1 is ANALYSIS ONLY. Do not implement, do not hardcode sample outputs. Profile every CSV, open every image, reverse-engineer each sample row, report confirmed rules, ambiguities, failure modes, open questions. Stop and wait."*
  2. *"Don't move to architecture yet. [Specific forensic question with numbers]. No blind grid search."*
  3. *"Architecture is fixed: [models, deterministic core, typed JSON, caching, budget]. Deliver package structure, data models, validator rules, eval harness, fail-closed error table. Stop and wait."*
- Push back visibly: "No, that adds a second agent without a measured gain; revert." "Show me rows where this changed the label." "Why top_k=8? Run 4 vs 8 on samples."
- Never paste API keys. Use env vars, `.env` gitignored.

---

## 9. AI Judge interview prep

### 9.1 Question bank (collected from winners' write-ups, the HackerRank blog and a judge simulator built from real interviews)
Opening and framing
- Give me a 60-second pitch of your system.
- What is the hardest part of this problem, and where does your system fail?
- Why is this problem not solvable with a single prompt?

Architecture
- Why a single agent instead of multi-agent? Where would the alternative have lost accuracy? (asked of the June #1)
- Where does the model decide and where does code decide? Why that split?
- A rule engine is just if-statements. Why is that engineering?
- Why does this function exist? (it points at your code)
- Walk me through one input row from read to final CSV.

Retrieval and evidence
- How does retrieval work, and what happens when it returns nothing?
- What are your retrieval hyperparameters and how were they chosen?
- How do you select supporting evidence IDs?
- How does your system handle images and audio? What if the image is blank or unrelated?

Safety
- Where does untrusted text reach something that makes a decision?
- Walk me through your safety gate. Why hard-block some cases and not others? What did the code do before your fix? (asked of the June #1)
- Can the LLM ever downgrade a high-risk case?

Evaluation
- What is your score, and on what set and how many rows?
- What did you try that made things worse, and how did you know?
- If you deliberately broke a component, would your harness notice?
- How is confidence computed, and what is it calibrated against?
- Is your system deterministic? Precisely where is it not?

Ops and production
- Cost per row, latency, how you handled rate limits and retries.
- What breaks first on unseen data? How would you monitor this in production?
- What would you do with another week?

AI usage
- How did you build this? What did the AI write, what did you decide, and what did you reject?
- Give an example where the AI was wrong and you caught it.

### 9.2 Answer structure
**Claim (1 sentence) → Evidence (number + where it lives) → Boundary (where it stops being true) → Alternative rejected and why.** Then stop. Long, concrete answers win (r=0.63), but don't ramble.

### 9.3 Never say
"Claude built the pipeline." · "It's fully deterministic." · "I get 100%." (say on which set and n) · "No dataset-specific assumptions." (say "I hunted for them and removed the ones I found") · any number you didn't measure. **"I don't remember the exact value, it's in CONSTANTS.md, I believe ~X"** beats inventing one.

### 9.4 Mock judge prompt (paste into Claude after submission)
> You are the HackerRank Orchestrate AI Judge. You have read my code (attached), output.csv and transcript. Interview me for 30 minutes in this order: pitch → problem framing & failure modes → code deep-dive (pick specific functions and constants) → testing evidence → production/monitoring → how I used AI (directed/accepted/rejected) → novelty. Ask one question at a time, follow up on vague answers, catch contradictions with the code, and at the end score me on: technical depth & ownership (40), judgment (25), clarity (20), honesty (15).

---

## 10. Pre-event build list (Oct 21–24)

**Hard truth about pre-building:** the rules don't forbid reusable personal tooling, but (a) your transcript is scored on *directing the build during the event*, and (b) the judge asks "what did you write and when." So pre-build **small generic utilities** that you understand line by line. Disclose them in the README and interview ("my own reusable LLM client and cache I wrote before the event"). Do **not** pre-build domain logic.

Build and rehearse these (Python 3.11, Pydantic v2, typed, PowerShell-friendly):
1. `llm/client.py`: provider-agnostic wrapper (OpenAI + Anthropic + Gemini) with structured JSON output via Pydantic schema, retries with exponential backoff and jitter, timeout, RPM/TPM token bucket, and a usage ledger (`usage.jsonl`: model, in/out tokens, cost, latency, cache hit).
2. `llm/cache.py`: content-addressed disk cache keyed on `sha256(model, prompt_version, schema_version, payload)`.
3. `runner/checkpoint.py`: per-row checkpoint and resume (`--no-resume` flag), and a concurrency pool with bounded parallelism.
4. `perception/`: image → base64 with resize under provider limits; audio → transcript (Whisper/gpt-4o-transcribe); PDF → text/images; OCR fallback.
5. `safety/injection.py`: multilingual heuristic detector + "untrusted data" wrapper template. Output is a **flag**, never an action.
6. `eval/`: per-field accuracy, confusion matrix, macro-F1, numeric MAE, a regression diff between two runs (rows whose labels changed), and a strategy comparison table → markdown.
7. `report/usage_report.py`: renders usage.jsonl into the exact required markdown (per-model + overall, avg tokens per row, cost per row).
8. `submit/validate_output.py`: exact column order, row count equals input, IDs unique and complete, enums valid, invariants hook. Plus `make_zip.py` that excludes data/, venv, caches and `.env`.
9. `agent/loop.py`: generic bounded tool loop (max steps, budget ceiling, tool-error recovery, fallback callback, per-row JSON trace).
10. Templates: `DECISIONS.md`, `CONSTANTS.md` (with provenance column: MEASURED / SPEC / STANDARD / JUDGEMENT), `experiments.md`, `interview_brief.md`.

**Dry run (do at least one by Oct 23):** clone the Sep repo and re-solve it in ~6 hours with this kit. Score yourself on the 25 samples and write the usage report. Then do the same on the August repo (it has audio). That gives you real interview anecdotes and finds the bugs in your kit before Oct 24.

Commands (PowerShell):
```powershell
New-Item -ItemType Directory -Force -Path "$HOME\orchestrate-prep" | Out-Null
Set-Location "$HOME\orchestrate-prep"
foreach ($m in @('may26','june26','august26','september26')) {
  git clone --depth 1 "https://github.com/interviewstreet/hackerrank-orchestrate-$m.git"
}
# reference solutions to study (read, don't copy)
git clone --depth 1 https://github.com/VIVPM/hackerrank-buy-or-wait.git                       # Sep #10, includes his 10/10 log.txt
git clone --depth 1 https://github.com/VIVPM/hackerrank-multi-modal-evidence-review-hackathon.git
git clone --depth 1 https://github.com/swayam-mishra/hackerrank-orchestrate.git               # June #3
git clone --depth 1 https://github.com/NITISH-R-G/hackerrank-orchestrate-skills.git           # judge simulator + 34 skills
```

---

## 11. Checklists

### Day-of setup (before 18:00 Oct 24)
- [ ] API keys for 2 providers loaded as env vars. Spend limits set. Quotas and tier checked (rate limits killed the June #1's run).
- [ ] Your prep kit installed. Python venv ready. `pip freeze` pinned.
- [ ] Claude Code and Codex logged in. Decide **now** whether you'll build primarily with Codex (credit prize) or Claude Code (what 7 of the May top 10 used). Don't switch mid-event.
- [ ] Discord joined: https://discord.gg/TzsUaAhPbr (clarifications get posted there).
- [ ] Camera, mic and quiet room for the interview. Water nearby.

### Submission gate
- [ ] `output.csv`: exact columns and order, 1 row per input ID, no blanks in required fields, enums valid, invariants hold.
- [ ] Justifications are specific (IDs, amounts, parts) and consistent with the label. None are generic.
- [ ] `code.zip` contains README (setup, env vars, run cmd), `evaluation/`, any usage report, prompts/configs. No data, no venv, no secrets, **no dead code**.
- [ ] `log.txt` is valid: every entry has the Context block and `tool=`, and secrets are redacted.
- [ ] `CONSTANTS.md` and `DECISIONS.md` are memorised. You have 3 rejection stories with numbers.

### Git (your standing rule)
- Commits must be under your name only, with Conventional Commits and no AI co-author trailers. Check `git log --format='%an %ae%n%b'` before pushing a public repo after the event.

---

## 12. Key people to follow (repeat top finishers)
These names keep showing up, which suggests the skill is repeatable rather than luck:
- **Rifqi Haikal** 🇮🇩: #5 May, #17 June, **#3 Aug**, #27 Sep. A medical doctor.
- **Hitakshi Arora**: #15 May, **#2 June**, #8 Aug, #20 Sep.
- **Caleb Andersen** 🇿🇦: #5 June, **#2 Aug** (code 28.2/30).
- **Sunny**: #15 Aug, then **#1 Sep**.
- **Vivek P M**: #30 June, #30 Aug, #10 Sep. Public repos and transcript.
- **Sristee Shrivastava**: #122 May, then **#1 June**.

Score shape of winners: Interview 24–27, Code 25–28, Output 18–23, Transcript 9–10. **You win by having no weak dimension.**

---

## Sources
- Official starter repos: [May](https://github.com/interviewstreet/hackerrank-orchestrate-may26) · [June](https://github.com/interviewstreet/hackerrank-orchestrate-june26) · [August](https://github.com/interviewstreet/hackerrank-orchestrate-august26) · [September](https://github.com/interviewstreet/hackerrank-orchestrate-september26)
- Leaderboards: [May](https://www.hackerrank.com/contests/hackerrank-orchestrate-may26/challenges/support-agent/leaderboard) · [June](https://www.hackerrank.com/contests/hackerrank-orchestrate-june26/challenges/multi-modal-review/leaderboard) · [Aug](https://www.hackerrank.com/contests/hackerrank-orchestrate-august26/challenges/message-notification-router/leaderboard) · [Sep](https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/leaderboard)
- [HackerRank: Behind the Scenes of Orchestrate](https://www.hackerrank.com/blog/behind-the-scenes-of-hackerrank-orchestrate/) · [Getting better at Orchestrate](https://www.hackerrank.com/blog/getting-better-at-orchestrate/) · [What 12,885 developers taught us](https://www.hackerrank.com/blog/what-12885-developers-taught-us-about-building-with-ai/) · [The new cheating problem](https://www.hackerrank.com/blog/the-new-cheating-problem-and-why-the-answer-isnt-a-stricter-test/)
- Winners: [Saai Syvendra, May #1](https://saai.syvendra.com/myspace/hackerrank-orchestrate) · [Sristee, June #1](https://medium.com/@sristee45/how-i-went-from-122-to-1-in-24-hours-building-a-multimodal-damage-claim-verifier-for-hackerrank-92cdc18242b2) · [Swayam Mishra, June #3](https://swayam-mishra.medium.com/how-to-build-ai-agents-you-can-actually-trust-d0c37289f48d) · [Shreesh, 3-edition guide](https://medium.com/@shreesh.exe22/hackerrank-orchestrate-3268f0d710a5) · [Arul Cornelious, June](https://dev.to/arul_cornelious/building-a-multi-modal-evidence-review-agent-for-damage-claims-2nc6)
- Repos: [VIVPM Sep](https://github.com/VIVPM/hackerrank-buy-or-wait) · [VIVPM June](https://github.com/VIVPM/hackerrank-multi-modal-evidence-review-hackathon) · [Swayam](https://github.com/swayam-mishra/hackerrank-orchestrate) · [NITISH skills kit](https://github.com/NITISH-R-G/hackerrank-orchestrate-skills)
- [June winners announcement (X)](https://x.com/hackerrank/status/2070493040532459527) · [October landing page](https://www.hackerrank.com/hackerrank-orchestrate-october26)
- Not accessible (robots-blocked): the LinkedIn posts and the rvivek X recap thread. Their key lines were taken from the testimonial cards on the official October page.
