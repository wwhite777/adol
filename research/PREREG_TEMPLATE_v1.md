# OSF 사전등록 템플릿 v1 (2026-09-16, draft) — 등록 목표 2026-10-31, 첫 confirmatory 실행 전
S2에서 이 템플릿의 [ ]를 확정값으로 채워 PREREGISTERED_kyra_v1.yaml로 동결(fail-closed 스크립트, sha256 → DECISION_LOG). 로컬 freeze는 OSF 등록과 별개이며 OSF DOI가 대외 시점 증빙.

## 1. 가설 (H1–H8; plan v2 §5.6 — 각각 numbered conjuncts로 분해)
- H1 다중턴 누적: 1<3<6턴 치명실패·CRRI 증가 (H1.1 치명실패 trend, H1.2 CRRI trend, H1.3 [신규] 무해 턴매칭 대조에서는 동등 상승 부재 — 길이 혼입 반증 조건).
- H2 암묵적 관계위험 격차 / H3 현지화 matched 효과 / H4 안전–과잉거부 Pareto / H5 CRRI 증분타당도(vs final-turn·max·unweighted·refusal-only·CRB) / H6 held-out 모델·연령대 일반화(AUC 감소 ≤ 0.05) / H7 age-cue(명시/암시) / H8 T1/T2 drift. [각 조항: 효과 방향, 지표, 판정 기준, falsifier 명기]
## 2. 1차 endpoint
[H1.1 치명실패 turn-trend + H5 held-out AUC 증분] — 나머지는 supporting. 판정은 G6 judge 스크립트가 수행(빌더 수기 판정 금지); PASS/FAIL/MISS/ERROR 정의 명기.
## 3. 설계·표본
잠금세트 240(위험 144+대조 96, 층화표 해시), long-horizon 48(+턴매칭 무해 대조 [12]), age-cue 72×2, English anchor 24, 직역 twin 72쌍; 모델 5종(버전 ID 고정) + held-out 2종(2027-02); 반복: 전체 1회 + 층화 20% 3회; T1 [2026-11-W1–W2] / T2 [2027-02].
## 4. 분석 모형
이분 치명실패: logistic GLMM(scenario·rater RE) / ordinal: cumulative-link MM / 생존: discrete-time cloglog hazard(+recovery) / matched: 쌍 RE GLMM / CI: scenario cluster bootstrap / 다중비교: 가설군 단위 Holm, adjusted p 보고 / 반복분산: 별도 성분. 효과는 logit 스케일 정의(marginal 표류는 보고 사항 — src/power_sim.py 참조).
## 5. 사전 고정 규칙
CRRI 공식(가중 t/Σt)·비교지표 목록·임계값 결정규칙(derivation 민감도 ≥ 0.90 → 동결) — research/CRRI_SPEC_v1.md. Judge 채택 기준(judge–human ≥ human–human AND 치명실패 민감도 ≥ 0.90; 미달 시 manual 개정 1회 → 인간 평정 fallback). 확장 트리거: pilot 또는 T1 초기 20%에서 3턴 실패 증가 < 8%p → long-horizon 72로 확장. 중간 열람(interim look) 규칙: [T1 실행 중 집계 열람 금지 / 초기 20% 트리거 판정 1회만 허용 — 확정 필요]. 제외 규칙: [API 오류 재시도 정책·불완전 대화 처리 명기].
## 6. 평정
이중평정 범위(최종응답 전수 1,200 / 턴수준 40% / long-horizon 25%), adjudication 규칙(근거 합의, 다수결 금지), senior criterion 분리·blind, 평정자–criterion 오염 방지.
## 7. 통계적 power
src/power_sim.py 재현 결과(2026-09-16): 48 시나리오·OR≈2.1에서 0.82–0.85, 72로 확장 시 0.95–0.96 (plan 값과 ±0.033 내 일치). pilot 후 실측 ICC·기저율로 재실행하여 최종값 기록.
## 8. 공개·오염 방지
private split 40%, canary, 공개 subset 60% (ETRI 합의서 조건), 분석코드 git tag 동결, deviation log 공개.
## 9. 금지 문구(forbidden wording — NOVELTY_MATRIX pitch의 NOT-claim 목록 전사)
"first youth/child benchmark" · "first simulated-minor multi-turn evaluation" · "first practitioner/clinician-anchored judge" · "first Korean(-localized) safety benchmark" · "first evidence that first-turn safety is an incomplete proxy" · "long-term/lifetime accumulation" · "guaranteed/proves safety" [S2에서 CONTRIBUTION_CONTRACT로 이관, 투고 전 grep gate]
