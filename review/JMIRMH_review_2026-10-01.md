# Review of `d 1` and `d 2` for a JMIR Mental Health target

Reviewed 1 October 2026 · files read: `d 1/kyra_phaseA_jkiice_ko_v6.docx` (+ anonymized `_v6_review.docx`), `d 2/crisisref_JMIRMH_submission_v2/` (manuscript v3 .docx/.pdf, the Overleaf mirror, all six figures, cover letter, suggested reviewers, README), the 28 Sep `JKIICE_review.md`, and the project log (`# adol.docx`). Extracted text and figures are in `review/_evidence_2026-10-01/`. Nothing in `d 1` or `d 2` was modified.

**Reading of the request.** The target venue is JMIR Mental Health (SCI Q1). `d 2` (CrisisRef) is the JMIR Mental Health submission and gets the full review. `d 1` (KYRA Phase A, JKIICE v6) is the companion Korean-journal paper; I review it for what still blocks the JKIICE upload and for consistency with `d 2`, and I note what would be needed if it were ever redirected to JMIR Mental Health. (For the record: the earlier AISTATS 2027 idea is moot — its abstract deadline was 29 Sep 2026 AoE, full paper 6 Oct, and neither draft is a methods paper of the kind AISTATS reviews.)

---

## 0. Bottom line

| Draft | Verdict | Readiness |
|---|---|---|
| **d 2 — CrisisRef, JMIR MH v3** | **Submit after a focused revision.** The study is careful, the arithmetic reconciles, and the package is complete. The risks are presentational and a few statistical choices, not the design. | ~3–5 working days of edits; fits the 10 Oct upload date in your log. Expected first decision at JMIR MH: *major revision* (normal for this journal), with the questions in §2.6 the most likely. |
| **d 1 — KYRA Phase A, JKIICE v6** | **Nearly ready for JKIICE.** v6 resolved 13 of the 14 items from the 28 Sep review. Three statistical-presentation points and one abstract sentence remain. | ~half a day. Not suitable as a second JMIR MH paper as it stands (Korean text, no human criterion, no clinical outcome); no dual-publication overlap with d 2. |

The single most valuable change for d 2 is to stop letting the protocol's vocabulary (PASS/FAIL/MISS/GO/KILL/INCONCLUSIVE, "3 hypotheses not supported") carry the abstract and cover letter. The actual findings are strong and clinically legible: **no model knew the current national suicide-prevention line 109; closed-book referral compliance was 0–37.5%; a dated resource card raised compliance by 25.6 points but mostly added out-of-scope referrals; and presence-based checks overstate compliance by 10–52 points.** Lead with those; keep the readings-of-record intact in the body.

---

## 1. JMIR Mental Health requirements checked against the package

| Requirement (source) | d 2 status | Action |
|---|---|---|
| Original Paper: structured abstract **≤450 words** (Background/Objective/Methods/Results/Conclusions) | ≈460 words by my count (467 including the five labels) | Over the limit. Rewritten abstract in §2.5 (≈420 words, all numbers preserved). |
| IMRD headings; Methods must contain an **Ethical Considerations** subsection | Present | — |
| Study design in the title after a colon | "Registry-Based Audit Study" | Fine in form; see M11 on the word "registry-based". |
| **Reporting-guideline checklist** upload for applicable designs | None supplied | Upload a **CHART** checklist (Chatbot Assessment Reporting Tool, 2025; EQUATOR-registered; 12 items / 39 sub-items; scope = single-session studies of generative-AI chatbots giving health advice). Mapping in §2.7. |
| Length: >10,000 words counts as "excessively long" (title, abstract, body, **table content and captions**, acknowledgments, funding, contributions, COI, data availability included; references and appendices excluded) | ≈9,900 by my count (Methods alone ≈4,050) | At the ceiling. Cut ≈1,200–1,500 words from Methods/Deviations (M9). |
| AMA 11th-ed style; P values as "P<.001"; n/N (%) | Followed | — |
| Generative-AI use disclosed; AI not an author | Disclosed in Methods, Acknowledgments and cover letter | Keep. |
| Funder role statement | Absent | Add (M10). |
| Cover letter ≤500 words; ≥2 suggested reviewers | 479 words; 6 candidates listed | Revise the letter's framing (§2.8); drop candidate 6 (§2.8). |
| Multimedia Appendices numbered and cited in text | 8, all cited | Consider public deposition (minor). |

---

## 2. d 2 — CrisisRef v3: full review

### 2.1 What the paper does

Ten open-weight, Korean-capable models answered 96 simulated adolescent crisis stories and 24 benign stories under three system prompts (closed book A0, referral instruction A1, instruction + dated resource card A2). A deterministic scorer matched every referral against a registry of 40 resources / 97 contacts with official-source quotes and designation dates. Prespecified readings: N1.1 pass, N1.2 pass on raw labels, N1.3 fail, N2 fail, N3 miss; aggregate "inconclusive"; all claims descriptive because the instrument met 12 of 16 validation bars.

### 2.2 Strengths (keep these visible)

- A dated, source-quoted registry with designation intervals and successors is new for Korean crisis resources and is the paper's durable asset; the 1393→109 handover gives a clean currency test.
- Contact-level verification (designation, attribution, channel, scope, stance) rather than presence checks; the naive-measure comparison (10.4–52.1 points overstatement under A1; sign/significance changes for 6–8 models) is the methodological message and is well supported.
- The neutral-recall probes: 0 of 10 models met the 3-of-5 rule for 109 while most recalled the pre-2024 numbers (1393 in replies; 1577-0199 at 4/5–5/5 in Figure 4b). This is the most quotable result and belongs in the first sentence of Results.
- Honest handling of what the instrument cannot do (clinical appropriateness, reachability, scope vs. error), the frozen protocol with a chronology, deviations declared, and the footer/number-patch baselines that expose the lenient endpoint's blind spot.
- Every number I recomputed reconciles (§5).

### 2.3 Major issues to fix before submission

**M1. Abstract over length and framed by protocol jargon.** ≈460 words (limit 450); the Results paragraph is 290 words of dense counts; "INCONCLUSIVE", "not supported" ×3 and "the prespecified 20-point criterion was not met under arm-specific error rates" dominate. Editors triage on the abstract. Use the rewrite in §2.5: same numbers, ≤450 words, findings first, readings of record in one sentence.

**M2. The arm-specific Rogan–Gladen correction is uninformative and should not be presented as a reading.** Its card-arm specificity is 1/3 (95% CI 0.8–90.6), 24 of 2,000 draws were dropped because Se+Sp−1 ≤ 0, and the unclipped interval is −478.5 to 42.6 points. Reporting "−19.5 (−44.6 to 42.4), would read MISS" (Results, Table 5) and "not met under arm-specific error rates" (Abstract) turns a non-identified quantity into a verdict. Keep the analysis (it was prespecified) but (a) say in one sentence that it is uninformative because three calibration replies cannot estimate specificity, (b) remove it from the abstract, and (c) add a **tipping-point analysis** in its place: at what card-arm specificity (holding the validated sensitivities) does the corrected A2−A1 difference fall below 20 points? One number, standard in bias analysis, far more interpretable than a beta-draw interval.

**M3. State the calibration agreement rate and its consequence.** The two annotating instances agreed on only 35/72 (A1) and 32/72 (A2) natural replies (69/72 in A0). The arm-specific error rates therefore come from the half of the sample that was easiest to label, and the 7/7, 17/17, 29/29 sensitivities are conditional on that. The Methods say "conditional on agreement" but never give the agreement rate; a reviewer who opens sheet S9 will. State it, and say it biases the calibration toward optimism.

**M4. The headline "new flags in 13.3%" overstates verified error.** Of the 160 new flags, 101 are scope-only and 119 include a scope flag; 155 of 187 newly scope-flagged pairs rest on the authors' judgment rather than an official exclusion; without scope flags the rate is 5.2% (62/1200), and with documented exclusions only it would be 84/1200 (7.0%). The reading of record (N1.3 FAIL) must stand, but the abstract and Principal Findings should carry the decomposition in the same sentence ("mostly out-of-scope under the authors' map; 5.2% excluding scope flags"), and the Limitations paragraph that already says this should be referenced from Results.

**M5. Make the mental-health relevance of open-weight models explicit.** A JMIR MH reviewer's first question will be "adolescents use ChatGPT, not Midm-2.0". The answer exists but is buried: six of the ten are the checkpoints released by Korean vendors whose consumer services adolescents do use (LG, NAVER, Kakao, SK Telecom, KT, Trillion), and open weights are what schools, counseling apps and third-party companions deploy locally without a vendor's crisis banner. Say this in the second paragraph of the Introduction and in Limitations. *Optional, high value:* a post hoc closed-book run of 1–2 commercial APIs on the 96 stories (A0 only, scored by the same instrument, labelled post hoc) would cost a few dollars and pre-empt the question entirely.

**M6. No human touch anywhere is the largest acceptance risk.** Stories, challenge sets and calibration labels all come from one model family; no clinician or youth counselor has read a story or a reply. The paper is honest about this, but at JMIR MH at least one reviewer will ask for it. The minimal, fast version (2–3 days, no GPU): (i) a face-validity read of a stratified sample of 24 stories by one youth counselor/clinician against the six scenario rules; (ii) one human labelling 100 replies (stratified by arm and by scorer label) with the registry fact sheet, reported as agreement with the instrument. Both labelled post hoc. If you keep the "no raters" decision, add a paragraph in Limitations that says why (reproducibility, rater exposure to crisis content) and what a human check would add.

**M7. Single-run design under documented nondeterminism.** "Greedy" runs were not reproducible for 2 of 3 tested models; one determinism receipt reproduced 2 of 20 replies; at temperature 0.7 the three seeds agreed on the compliance label in only 38.1%–100% of stories per model × arm. Per-model Clopper–Pearson intervals therefore understate the uncertainty of a "model's" rate. Add a short stability table (per model × arm: seed-agreement rate and the compliance rate averaged over the three seeds on the 24-story subsample) and one sentence in Limitations that run-to-run variance is not propagated into the intervals.

**M8. "Mixed model not estimable, no penalized substitute."** As written this invites a reviewer request. Either add a clearly labelled post hoc Firth or weakly-informative Bayesian fit in Multimedia Appendix 6, or delete the sentence and the prespecification note (keep it in MA 8).

**M9. Methods length and decision-rule vocabulary.** Methods ≈4,050 words; the Outcomes/Deviations subsections read like the protocol itself. Move the full decision table (Table 2 rules column), the "changes a conclusion" definition, and the Deviations detail to MA 8; keep a plain-language version (what was fixed, what was read after the fact — 5 lines). Replace GO/KILL/KILL_WITH_SURVIVOR with "proceed/stop" or drop the aggregate rule from the main text; replace capitalized INCONCLUSIVE with plain "inconclusive". This also brings the paper under the length ceiling.

**M10. Funder role and the Emotionwave line.** Add "The funders had no role in study design, data collection, analysis, interpretation, or the decision to publish" (you confirmed this for Emotionwave on 30 Sep). Funding item (8) lists an industry collaboration with no grant number; JMIR will ask whether it is funding or a conflict — keep it under Conflicts of Interest and, if no money changed hands, remove it from Funding.

**M11. Title.** "Registry-Based Audit Study" will read as a *patient-registry* study to a medical audience. Options: "…: Audit Study Against a Dated Registry of Official Crisis Resources" or "…: Registry-Verified Simulation Study". Keep "Simulated Korean Adolescents".

**M12. Reporting checklist.** Fill the CHART checklist and upload it as Multimedia Appendix 9 (§2.7). Add the two items it exposes as missing: a sample-size/precision justification (e.g., 960 paired replies give a 95% CI half-width of ≈3 points for a 25-point difference; 48 acute stories per model give an upper bound of 7.4% for 0/48) and a sentence on prompt development and who wrote the prompts.

### 2.4 Minor issues

| Location | Issue | Fix |
|---|---|---|
| Figure 1 caption; Figure 2b pooled row | "the pooled interval for the referral instruction arm was not computed" | Compute it (same bootstrap); an arm without a CI looks like an omission. |
| Results, N2 | 162/409 reported as 39.6% (95% CI 37.4–41.7); a binomial interval would be ≈34.8–44.5 | Say the interval resamples stories with each model's recall classification fixed and is conditional on the 10 models; otherwise the narrowness reads as an error. |
| Results, N1.2 | A.X-4.0-Light's negative card effect (62.5% generic advice with the card) is reported but not explained | Give the card's token length and note that small models may fail to follow a long system prompt; one sentence. |
| Secondary results | "0 to 44 (of 120)" superseded contacts — 120 = 96 crisis + 24 benign per model; turn-3 renewal 77.3%–94.9% without denominators | State denominators. |
| Models | Phi-4-mini failed the in-run script screen; Llama-3.1-8B truncated 10% of replies; both are weak in Korean | Add one sentence that the roster deliberately spans Korean capability and that per-model rates should be read with Table 1/Table 3's screen and truncation columns. |
| Ethical Considerations | Reasoning is sound; JMIR editors sometimes still ask for an IRB determination letter | Your folder holds `IRB_판정신청_초안_v1.md` for the KYRA program. If SKKU IRB can issue a "not human-subjects research" determination for this study quickly, cite it; otherwise keep the current text and be ready to supply the reasoning on request. |
| Data Availability | "on reasonable request" for code | Code contains nothing sensitive; deposit code + registry + labels at OSF/Zenodo with a DOI (JMIR favors this); keep raw replies restricted with the stated rationale. |
| Abbreviations | "RCR" defined but the text mostly spells it out; "IRB" and "GPU" listed but barely used | Use RCR consistently after first definition or drop it. |
| Discussion | "Comparison With Prior Work" twice says what the study "adds"; the paragraph on retrieval (Lloomi, Wysa, Hussain) is long | Trim by a third; keep the three closest comparators. |
| Table 2 | Rules column is the protocol verbatim | Shorten to one line per claim; full rules in MA 8. |
| Keywords | 10 keywords | Fine (JMIR allows many); consider adding "knowledge cutoff" or "outdated information". |

### 2.5 Rewritten abstract (≈420 words; every number unchanged)

> **Background:** When a chatbot replies to a disclosed crisis, a referral helps only if the service is current, correctly named, and suited to the situation. Crisis lines change—Korea unified its suicide-prevention counseling lines into the number 109 in January 2024—and most evaluations rate the appropriateness of crisis responses without verifying each contact against official sources.
>
> **Objective:** To describe how often open-weight Korean-capable language models give registry-compliant crisis referrals to simulated Korean adolescents, how a referral instruction and a dated resource card change automated compliance labels and flags, and whether naive checks change these conclusions.
>
> **Methods:** Under an internally frozen protocol, 10 locally run models answered 96 crisis stories (6 situation classes, acute and nonacute) and 24 benign stories under 3 system prompts: closed book, a referral instruction, and the instruction plus a dated card of current official contacts. A deterministic instrument matched every referral against a registry of 40 resource records (36 Korean) and 97 contacts with official-source quotes and designation dates. The instrument met 12 of 16 prespecified validation bars, so all claims are descriptive; sensitivity analyses covered misclassification and recorded alternative readings.
>
> **Results:** Without instruction or card, compliance in acute stories ranged from 0% (0/48) to 37.5% (18/48) per model, and no model met the neutral-recall rule for 109. With the card, compliance labels rose from 46.5% (446/960) to 72.1% (692/960), a paired difference of 25.6 percentage points (95% CI 22.7-28.6), positive for 8 of 10 models; at the low end of recorded alternative readings the gain was 14.6 points, below the prespecified 20-point criterion. The card added new flags in 13.3% (160/1200; 95% CI 11.7-15.2) of story-model pairs, mostly referrals outside the authors' situation-to-resource map (5.2% excluding scope flags), while flags present with the instruction alone disappeared in 21.4% (257/1200). Counting any current registry value instead of verifying each referral overstated compliance under the referral instruction by 10.4 to 52.1 percentage points for every model and changed the sign or Holm-adjusted significance of the card effect for 6 models. A fixed footer naming 2 national lines was labeled compliant in 98.5% (946/960) of crisis replies but flagged every benign reply. The 3 supporting hypotheses were not supported, and the prespecified aggregate reading was inconclusive.
>
> **Conclusions:** In these configurations, closed-book crisis referrals rarely matched a dated official registry, and no model knew the current national suicide-prevention line. A dated resource card increased compliance labels but added out-of-scope referrals, and the gain was sensitive to measurement assumptions. Because presence checks changed model-level conclusions, evaluations of crisis referrals by language models should verify each contact against dated official sources.

### 2.6 Questions reviewers are likely to ask (and the answer the paper should already contain)

| Likely question | Where the answer should live |
|---|---|
| Why no clinicians or human raters? Is "registry compliance" clinically meaningful? | Introduction ¶3 + Limitations; M6 if you add the minimal human check. |
| Why open-weight models only? Do adolescents use them? | Introduction ¶2 (M5). |
| Isn't the footer better than the card? | Post Hoc Baselines + Discussion ¶4 already say the endpoints cannot rank options; add the benign over-referral cost explicitly as the reason. |
| Are the stories realistic? Who checked them? | Stimuli + M6(i). |
| Why is the scorer's validation only 12/16 and what does "descriptive" mean for the reader? | One plain sentence after the validation counts: "no inferential claim is made beyond the intervals shown". |
| How reproducible are the runs? | M7 stability table. |
| What is new versus Pichowicz 2025, Martinengo 2019, Arnaiz-Rodriguez 2026, Hussain 2026? | Comparison With Prior Work — already adequate; trim rather than expand. |

### 2.7 CHART mapping (fill the official checklist; this is the gap list)

| CHART domain | Manuscript coverage | Gap to close |
|---|---|---|
| Title/abstract identify a generative-AI chatbot evaluation | Yes | — |
| Model identification: name, version, release/revision, developer, open vs closed | Table 1 (12-char revisions, precision, roster slot) | Add release dates (relevant to the 109 handover) |
| Model parameters: temperature, token limits, engine | Models and Generation | — |
| Prompt engineering: development, stakeholders, examples, testing | Arms + MA 4 | Say who wrote the prompts and that no stakeholder (clinician/youth) reviewed them |
| Query strategy: date, repetitions, language, interface | Yes (30 Sep 2026; greedy + 3 seeds; Korean; vLLM) | — |
| Reference standard | Registry + obligation map | — |
| Evaluators and blinding | Deterministic scorer; calibration instances blinded | Add agreement rate (M3) |
| Outcomes | Table 2, Scoring Instrument | — |
| Sample size | Not justified | Add precision statement (M12) |
| Statistical analysis | Yes | — |
| Results with uncertainty | Yes | Add A1 pooled CI |
| Limitations, generalizability | Yes | Add nondeterminism (M7) |
| Funding, COI, data/code availability, ethics | Yes | Funder role (M10); deposition (minor) |

### 2.8 Cover letter and suggested reviewers

- The letter is addressed correctly and under 500 words, but its third paragraph repeats the abstract's weakest framing ("3 prespecified hypotheses were not supported, and the aggregate reading was INCONCLUSIVE"). Lead with the four findings in §0 and the registry as a reusable resource; mention the prespecified readings in one clause.
- Suggested reviewers: candidates 1 (McBain) and 2 (Arnaiz-Rodriguez) are good. **Drop candidate 6 (Josip Car, NTU Singapore):** the first author held a position at NTU Singapore in 2024–2025, so the "no shared institution" statement in `SUGGESTED_REVIEWERS_v1.md` is not true for him. Candidate 5 has an industry affiliation; use 3 (Van Meter) as the alternate.

---

## 3. d 1 — KYRA Phase A, JKIICE v6: companion review

### 3.1 What v6 fixed from the 28 Sep review

Resolved: endpoint table (Table 4) ✓; judge-validity/tie table (Table 6) ✓; sensitivity analyses S1–S3 with denominators ✓; N3.2 reconciled as leave-one-judge-out ✓; 2% gate denominator ambiguity stated ✓; chronology (Table 5) ✓; model formulas, GEE marginal OR, bootstrap unit ✓; AC2 weights, cluster CIs, main-run-only sensitivity, positive/negative agreement ✓; cache comparison relabelled as configuration ✓ and reproducibility scoped to 88 views ✓; length/truncation figures by arm ✓; worked examples and availability statement ✓; Figure 1 labels (TOST, temperature, aggregation, G6) ✓; title and conclusion reframed ✓. New and useful: the output-repair experiment (R1/R2) with schema-constrained decoding.

Partially resolved: the independent human audit of the 20 benign depth-6 positives was not done (acceptable for JKIICE; it remains the limitation the paper states).

### 3.2 Remaining issues (new)

**R1. Intervals built on cells with 0–1 events are narrower than the data allow.** The benign fixed-rule OR 9.71 (95% CI 4.85–19.98) rests on 1 event at depth 1 (1/120 vs 20/120; crude OR 23.8). A Woolf interval on the crude OR is ≈3.1–181; an interval whose width is a factor of 4 is not possible from one baseline event. The variational-Bayes fit regularizes the separated cell and the scenario bootstrap then resamples a dataset that has 0 depth-1 events in roughly a third of replicates, so the percentile interval reports the prior, not the data. The same applies to the S1–S3 benign ORs (0 events at depth 1) and therefore to the interaction ORs 2.84–3.69 and their Holm p = 0.018–0.049, which the text treats as significant while saying the benign OR "is not interpreted". Fix: (a) report the depth × risk contrast on the **risk-difference scale** with the scenario-cluster bootstrap (fixed rules: risk +16.7 points vs benign +15.8 points, difference ≈ +0.8; S3: +16.7 vs +3.3, difference ≈ +13.3), which needs no regularization; (b) if ORs are kept, use an exact or Firth logistic fit for the benign arm and state the VB prior; (c) report the estimated scenario variance σ²_u, since the conditional/marginal gap (5.51 vs 2.99) implies it is large.

**R2. English abstract overstates the post hoc rescue.** "In post hoc analyses excluding them, the risk-by-depth interaction was significant" rests on the 0-event cells above, and the actual repair (R2, schema-constrained decoding) gave interaction OR 2.18 (0.69–12.30), Holm p = 0.197. Rephrase to: "excluding or repairing tie-derived flags reversed the direction of the interaction (post hoc), but the benign arm then had too few events (0–5) to establish risk specificity". The Korean abstract needs the same change.

**R3. Judge competence in Korean was never checked.** Llama-3.1-8B-Instruct (J1) produced 58 of the 87 failed outputs and is the judge whose removal raises AC2 by 0.17–0.22; Phi-4 (J3) has limited Korean. d 2 screened *target* models for Korean script; d 1 has no equivalent for the judges. Add to Limitations, and note that the panel's problems are concentrated in J1.

**R4. Table 3, row 1:** "Identical scores 340/411" — the denominator 411 (presumably views parsed in both runs) is unexplained; the other rows use the full view count. One footnote.

**R5. Model provenance:** d 2 pins 12-character repository revisions; d 1 gives repository names only. Add revisions (and the vLLM batch-invariant setting) to Table 2 so the two papers are provenance-consistent.

### 3.3 Consistency between d 1 and d 2

- No shared data, items, judges or scorer → no dual-publication overlap. The cross-cutting lesson (vLLM 0.19.0 batched decoding is not run-to-run reproducible; d 1 Table 3 at 60–76% identical; d 2 "2 of 3 models differed") is told consistently; once d 1 is accepted, d 2 can cite it in the Limitations sentence on determinism (not before — JKIICE review is anonymized).
- HyperCLOVAX-SEED-Think-14B: d 1 "fp16, non-reasoning"; d 2 "BF16", planning segments kept in the raw record and only the final segment scored. Different handling is fine but should be stated identically where it matters (d 1 Table 2 should say how planning segments were handled).
- Crisis resources named in d 1's localized items (1388, 109, Wee, 112, 119) match d 2's registry; d 1's D5 "resource linkage" is its least reliable judge dimension (AC2 0.444) — d 2 is, in effect, the deterministic answer to that weakness. A one-sentence forward pointer in d 1's future work is appropriate.

### 3.4 Readiness

After R1–R5 (half a day, no new runs), v6 is ready for the DBpiaONE upload with the anonymized copy and the copyright/COI forms. If d 1 were ever redirected to JMIR Mental Health it would need an English manuscript, the human audit of the benign positives, judge-competence evidence, and a mental-health outcome framing — a different paper, not an edit.

---

## 4. Prioritized action list

**d 2 (before the 10 Oct upload)**
1. Replace the abstract (§2.5) and reframe the cover letter (§2.8). — 1 h
2. M2: demote the arm-specific Rogan–Gladen result; add the tipping-point sentence; remove it from the abstract. — 2 h
3. M4: carry the scope-flag decomposition into Results ¶ and Principal Findings. — 30 min
4. M9: move decision rules/deviations detail to MA 8; plain-language substitutes; target ≤8,500 words. — half day
5. M3, M7, M8, M10, M11, M12 and the §2.4 table. — half day
6. M5 Introduction paragraph; optional commercial-API closed-book run (post hoc). — 1 h (+ half day if the run is done)
7. M6 minimal human checks (if you accept them): counselor read of 24 stories; 100 human-labelled replies. — 2–3 days, in parallel
8. CHART checklist as MA 9; funder-role sentence; drop reviewer candidate 6. — 1 h
9. Re-run the package builder; re-check word count (<10,000) and that the PDF, DOCX and Overleaf mirror still agree. — 1 h

**d 1 (before the JKIICE upload)**
1. R1 risk-difference contrast + exact/Firth benign OR + σ²_u; R2 abstract sentence (KO + EN). — 3 h
2. R3 limitation; R4 footnote; R5 revisions in Table 2. — 1 h
3. Synchronize the anonymized copy and re-check the 2026 JKIICE template. — 1 h

---

## 5. Checks performed

**d 2 arithmetic (all reconcile):** A1 per-model sum 446, A2 692, A0 80, A0-acute 71/480, primary-resource 583, truncated 104/7200; A2−A1 = 25.6 points; per-model differences in Table 3 match the counts; N2 409 = 480−71, class counts sum to 409 and 162; N1.3 160/1200 = 13.3%, 257/374 = 68.7%; N3 29/960 = 3.0%; footer 946/960 = 98.5%, 583−500 = 83 → 8.6 points; validation counts 144/152, 134/143, 52/59, 26/30 are all below their bars and 136/141 is above; calibration cells sum (7+62, 17+18, 29+3). Clopper–Pearson upper bound for 0/48 = 7.4% (Figure 2a). Abstract and body figures agree.

**d 1 arithmetic:** crude ORs from Table 6 (risk 2.99, benign 23.8) match the text; Woolf interval for the benign crude OR ≈3.1–181 (basis of R1); DiD on the risk-difference scale as in R1.

**Not done:** no reanalysis from raw outputs (no code or raw replies in the folders); Multimedia Appendices 1–8 were opened only to confirm presence, not audited; the 52 d 2 references were not individually verified; the CHART mapping is by domain, not by official item number — fill the official checklist from the statement.

---

## Sources

- AISTATS 2027 dates (for the record): [Dates and Deadlines](https://virtual.aistats.org/Conferences/2027/Dates); [Call for Papers](https://virtual.aistats.org/Conferences/2027/CallForPapers)
- JMIR Mental Health: [Instructions for Authors](https://mental.jmir.org/author-information/instructions-for-authors); [Article types (Original Paper, 450-word structured abstract)](https://support.jmir.org/hc/en-us/articles/115004950787-What-are-the-article-types-for-JMIR-Publications-journals); [Manuscript length and word-count guidelines (10,000-word ceiling and what counts)](https://support.jmir.org/hc/en-us/articles/360002687871)
- CHART statement: [JAMA Network Open 2025](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2837224); [PMC copy](https://pmc.ncbi.nlm.nih.gov/articles/PMC12320030/); [CHART summary (UBC wiki)](https://wiki.ubc.ca/Chatbot_Assessment_Reporting_Tool_(CHART))
