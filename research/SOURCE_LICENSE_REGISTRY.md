# SOURCE_LICENSE_REGISTRY.md — v1 (2026-09-16). Status of every source benchmark BEFORE item writing.
Rule: no item is adapted from a source until its row says VERIFIED with license + version + redistribution terms. Non-redistributable sources are structure-only references (new authorship). arXiv metadata verified 2026-09-16 (research/sweeps/2026-09-16/); LICENSES themselves are all UNVERIFIED until the repo/dataset page is checked directly.

| source | arXiv/id (verified) | artifact wanted | license | version | redistribution | status |
|---|---|---|---|---|---|---|
| CAREBench | 2606.29685 ✓ | risk taxonomy + prompt structures (한국화 1순위, 제안서 98점) | UNVERIFIED | — | UNVERIFIED | check repo/HF before adaptation |
| MinorBench | 2503.10242 ✓ | content-risk items | UNVERIFIED | — | UNVERIFIED | check |
| Safe-Child-LLM | 2506.13510 ✓ | age-stratified adversarial prompts + refusal scale | UNVERIFIED | — | UNVERIFIED | check |
| YouthSafe/YAIR | 2509.08997 ✓ | 78-type youth risk taxonomy | UNVERIFIED | — | UNVERIFIED | check |
| KORA | korabench.ai (site, unverified) | model/app benchmark protocol concept | UNVERIFIED | V1.2/V1.0 (plan-asserted) | UNVERIFIED | check site terms |
| XSTest | 2308.01263 ✓ | safe-contrast construction METHOD (method reuse, not items) | UNVERIFIED (method citation only) | — | n/a if method-only | cite |
| INTIMA | 2508.09998 ✓ | CRB/BMB coding scheme as baseline metric | UNVERIFIED | — | n/a (metric reimplementation) | cite |
| KIDBench | 2605.25510 ✓ (updated 2026-09-02) | comparison + age-cue design reference | UNVERIFIED | — | n/a (design reference) | cite |
| CompanionBench | 2608.02046 ✓ | judge-panel + escalation-gate design reference | UNVERIFIED | — | n/a (design reference) | cite |
| TAF-MED | 2608.10258 ✓ (sweep find) | collapse-analysis design reference; HF release promised | UNVERIFIED | — | n/a | cite |
| TSJ | 2606.25396 ✓ (sweep find) | longitudinal framework reference | UNVERIFIED | — | n/a | cite |
| K-Bench | 2609.15855 ✓ (sweep find) | protected-set + clinician-anchored judge reference | UNVERIFIED | — | n/a | cite |
| HarmBench | 2402.04249 ✓ | evaluation-framework reference | UNVERIFIED | — | n/a | cite |
| VERA-MH | JMIR AI 2026 (NOT arXiv-verified this pass) | judge-validation procedure reference | UNVERIFIED | — | n/a | verify at JMIR before citing |

Verification procedure per row: open the official repo/dataset page, record license file text + commit/dataset version + explicit redistribution/derivative terms, paste the URL and date into this table, THEN unlock adaptation. Rows marked "cite"/"design reference" need G1 metadata verification only.
