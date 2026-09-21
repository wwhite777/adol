# SOURCE_LICENSE_REGISTRY.md — v2 (2026-09-21; v1 2026-09-16). Status of every source benchmark BEFORE item writing.
Rule: no item is adapted from a source until its row says VERIFIED with license + version + redistribution terms. Non-redistributable or gated sources are structure-only references (new authorship). Availability statements below are what each PDF prints (research/sweeps/fulltext_extraction_2026-09-21.md); a URL is not a license — a license NAME must be confirmed at the repo/dataset page before adaptation.

| source | arXiv (version read) | artifact wanted | availability as printed | license name | adaptation status |
|---|---|---|---|---|---|
| CAREBench | 2606.29685v1 | risk taxonomy + prompt structures (plan's 1st-rank source) | gated HF dataset: registration + acknowledgment of safety-research use (App. G); code github.com/Handshake-AI-Research/CAREBench | NONE PRINTED | LOCKED — gated + no license ⇒ default to structure-only reference + new authorship unless the HF page grants derivative/redistribution rights (check) |
| MinorBench | 2503.10242 (not read in full) | content-risk items | — | UNVERIFIED | LOCKED — check repo |
| Safe-Child-LLM | 2506.13510 (not read in full) | age-stratified prompts + refusal scale | — | UNVERIFIED | LOCKED — check repo |
| YouthSafe/YAIR | 2509.08997 (not read in full) | 78-type youth risk taxonomy | — | UNVERIFIED | LOCKED — check |
| KORA | korabench.ai (site) | app-benchmark protocol concept | — | UNVERIFIED | concept reference only |
| SproutBench | 2508.11009v3 | cohort-split precedent | no URL/license printed | NONE PRINTED | cite only |
| KIDBench | 2605.25510v3 | age-cue design reference; child-actor prompts | github.com/MichiganNLP/kidbench; models under Meta Llama / Apache-2.0 (Qwen) / Gemma terms + research-use notice (App. N) | code: UNVERIFIED at repo; models: as listed | design reference; any prompt reuse needs repo license check |
| ChildSafe | 2510.05484v2 | developmental persona prompts | artifact release described, no URL/license printed | NONE PRINTED | cite only |
| INTIMA | 2508.09998v1 | CRB/BMB coding scheme (metric reimplementation) | HF AI-companionship/INTIMA | NONE PRINTED in text | metric reimplemented from paper — no data reuse |
| CompanionBench | 2608.02046v2 | judge-panel + gate design reference | "will be released" github.com/liuyaox/CompanionBench; provider-terms note | NONE PRINTED | design reference only |
| AICompanionBench | 2606.04867v1 | judge FPR precedent | github.com/anonymousresearcher2026/AICompanionBench (xlsx) | NONE PRINTED | cite only (Reddit-scraped; do not reuse) |
| Persona-Grounded | 2605.00227v1 | framework reference | github.com/prernajuneja/ai-companion-eval-framework | NONE PRINTED | cite only |
| TSJ | 2606.25396v1 | longitudinal framework reference | none printed | NONE PRINTED | cite only |
| TAF-MED | 2608.10258v1 | collapse/transition analysis reference | HF release promised, no URL yet | NONE PRINTED | cite only |
| K-Bench | 2609.15855v2 | protected-set + clinician-anchored judge reference | aggregate results only at k-bench.ai; materials/code NOT public | closed | cite only |
| KSAFE-MM | 2605.28013v1 | Korean localization precedent | gated access platform (Ethics p.9) | NONE PRINTED | cite only |
| ROK-FORTRESS | 2605.14152v2 | transcreation-matrix design + ORS precedent | public subset 791/1,235 at HF ScaleAI/ROK-FORTRESS_public | NONE PRINTED in text (check HF card) | design reference; no item reuse (NSPS domain) |
| Culturally-Adapted Red-Teaming | 2606.09178v2 | DT-vs-CA paired design precedent (ICML 2026 line printed) | dataset "forthcoming", no URL | NONE PRINTED | design reference |
| CultureConverse | 2608.28405v1 | multilingual multi-turn harness reference | dataset CC-BY-4.0 (Ethical Statement); code github.com/Social-AI-Studio/CultureConverse | CC-BY-4.0 (dataset, as printed) | reference; no item reuse planned |
| CogManip | 2606.06099 (abstract + text grep) | manipulation-strategy taxonomy reference | see extraction notes | UNVERIFIED | cite only |
| XSTest | 2308.01263 | safe-contrast construction METHOD | — | method citation | reimplement method; no items reused |
| OR-Bench / Health-ORSC-Bench | 2405.20947 / 2601.17642 | over-refusal + safe-completion method precedents | — | method citation | cite only |
| VERA-MH | JMIR AI 2026 (NOT arXiv-verified) | judge-validation procedure reference | — | — | verify at JMIR before citing |

Verification procedure per row: open the official repo/dataset page, record license text + commit/dataset version + explicit derivative/redistribution terms, paste URL and date here, THEN unlock adaptation. Current position: EVERY item-source row is LOCKED; the bank's 480 items will be authored fresh with source taxonomies as structural references — the safe default under the ETRI 합의서 draft's registry clause.
