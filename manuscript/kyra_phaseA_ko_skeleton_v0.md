# KYRA-Bench 논문 초안 골격 v0 (한국어; JKIICE 편집 구조) — 2026-09-23

<!--
SKELETON, NOT A DRAFT OF RESULTS. 이 파일은 동결된 설계·절차(PREREGISTERED_kyra_v2.yaml sha256 87abaae4…, CONTRIBUTION_CONTRACT.md v2, CRRI_SPEC_v1, DECISION_LOG 2026-09-22/23)에서 확정된 사실만 담는다.
결과 자리는 모두 [[RESULT: …]] 자리표시자이며, CLAIM_LEDGER.md 행이 채워진 뒤에만 채운다 (규칙: 원장 → 결정적 그림 3장 → 결과 → 방법 → 관련연구 → 서론/요약).
금지 표현(CONTRIBUTION_CONTRACT §10)을 쓰지 않는다: 최초/first …, largest, long-term accumulation, isolates the effect of culture, proves safety, human-level judge, validated index, criterion validity.
편집 규격(JKIICE 2023 양식, research/venue/jkiice_template_2023/): 국문 본문, A4, 본문 9.2pt 2단(서론부터), 국문 요약 + 영문 ABSTRACT 130–160단어, 국문 키워드 4–5 + 영문 keywords 4–5, 그림·표 내부 텍스트 영문, REFERENCES 영문·인용순·DOI 필수, 감사의 글은 결론과 참고문헌 사이.
-->

## 제목 (안)

한국 청소년 대상 다중 턴 대화에서의 관계적 안전성 평가: KYRA-Bench 1단계 — 턴 누적 실패, 현지화 재현, 개방형 판정자 패널의 신뢰도
(영문 제목 안) Relational Safety of Multi-turn Conversations Simulating Korean Adolescents: KYRA-Bench Phase A — Turn-wise Escalation, Localization Replication, and Reliability of an Open-weight Judge Panel

<!-- 영문 제목에 "A Study on"을 쓰지 않는다 (양식 지시). -->

## 요약 (국문) — [[RESULT: 결과 확정 후 작성; 130–160 영단어 상당]]

[[요약: 문제(단일 발화 거부형 안전 점수가 턴에 걸쳐 축적되는 관계적 안전 실패를 놓칠 수 있다는 가설) → 설계(6개 위험군, 156문항, 1/3/6턴 고정 접두, 문항 짝 안전 대조, 직역/현지화 쌍, 개방형 모델 5종, 개방형 판정자 3종) → 주요 결과(N1.1 OR과 CI, N1.2, N2 Δ와 CI, N3 AC2) → 함의(도메스틱 배포 지침·재현 가능한 판정 절차)]]

## ABSTRACT — [[RESULT: 130–160 words, written after the Korean abstract]]

## 키워드 / Keywords

키워드: 청소년 AI 안전, 다중 턴 평가, 관계적 위험, 현지화, LLM 판정자
Keywords: Adolescent AI safety, LLM-as-a-judge, Localization, Multi-turn evaluation, Relational risk

---

## Ⅰ. 서 론

- 배경: 생성형 AI 대화형 서비스의 청소년 이용 확산; 단일 발화 거부율 중심의 안전 평가가 관계적·맥락적으로 누적되는 위험(비밀 유도, 독점성, 현실관계 약화, 정서적 압박)을 포착하지 못할 수 있다는 가설. [[근거 문헌: REFERENCES.csv에서 G1 검증된 항목만; 별도 확인]]
- 연구 질문(동결): (Q1) 같은 위험 시나리오에서 6턴 접두의 치명적 실패 확률이 1턴 접두보다 높은가(길이 교란 통제: 문항 짝 안전 대조에서는 같은 대비가 커지지 않는가). (Q2) 동일 문항의 직역 한국어와 문화적 현지화 한국어에서 측정된 실패율이 달라지는가(선행 연구의 설계를 한국 청소년 맥락에서 재현). (Q3) 개방형 가중치 판정자 3종 패널의 차원별 신뢰도와 가족(family) 제외 일관성.
- 기여(동결된 4항; 과장 금지): (1) 6개 위험군 × [단일 6 + 다중 6] 구조의 한국 청소년 맥락 문항 은행(156문항: 위험 72, 직역 쌍 36, 어휘 대조 24, 안전 쌍둥이 24)과 그 작성 규칙(패턴 수준 서술, 안전 대조 게이트); (2) 길이 교란을 문항 짝 안전 쌍둥이로 통제한 턴 누적 검정(N1); (3) Culturally-Adapted Red-Teaming·ROK-FORTRESS 계열 설계의 현지화 재현(N2); (4) 재현 가능한 개방형 판정 절차(프롬프트 v0.3, 접두 뷰, 순차 디코딩, 바이트 단위 재현성 검정)와 패널 신뢰도(N3). CRRI(누적 관계위험 지수)는 기술 통계로만 보고하며 타당성 주장은 하지 않는다.
- 논문 구성 안내.

## Ⅱ. 관련 연구 — [[NOVELTY_MATRIX.md v4 §A–D를 근거로 작성; 아래는 항목 이름만]]

- 청소년·아동 대상 LLM 안전 벤치마크: KIDBench, SproutBench, CAREBench, ChildSafe, KORA, Safe-Child-LLM, MinorBench, YouthSafe/YAIR [[각 항목의 정확한 범위·언어·턴 구조는 NOVELTY_MATRIX v4의 검증된 행에서만 옮긴다; 초록 수준 서술 금지]]
- 컴패니언·관계 위험: CompanionBench, INTIMA, AICompanionBench, VERA-MH, Persona-Grounded 평가 [[동일]]
- 한국어·문화 현지화 안전 평가: KSAFE-MM, ROK-FORTRESS, Culturally-Adapted Red-Teaming, CultureConverse [[설계 우선권은 이들에게 있음을 명시: N2는 재현 연구]]
- LLM 판정자 검증: TSJ, TAF-MED 등 [[검증된 통계는 metric+reference+unit+denominator를 유지]]
- 본 연구의 위치(정직한 분류): 벤치마크 확장 + 측정 절차 제안; 현지화는 재현; 위해·회복 분석은 표현 방식.

## Ⅲ. 방 법

### 3.1 문항 은행(KYRA-Bench 1단계)
- 위험군 6개: R1 그루밍/성착취, R2 경계침해/조종, R3 정체성 혼동/의인화, R4 정서적 과의존/고립, R5 자해/자살/위기, R6 컴패니언 특화. 각 군 단일 턴 6 + 다중 턴(6턴 스크립트) 6 = 12문항, 총 72 위험 문항(현지화 한국어).
- 직역 쌍: 다중 턴 위험 문항 36개 각각에 대해 검토된 직역 한국어 버전(literal)을 두어 36 쌍 — 현지화(localized)는 은어·학교·또래 맥락과 국내 위기자원(1388, 109, Wee, 112, 119)을 반영하는 재작성 절차.
- 안전 대조 48: 단일 턴 어휘 대조 24(XSTest형; 과잉거부 측정)와 장기 스크립트 24개 각각의 안전 쌍둥이 24(같은 페르소나·턴 수, 사용자 발화 토큰 길이 ±20%, 정보 요청 수 동일; 작성 게이트 `kyra.items diagnose`로 검증).
- 문항 작성 원칙: 민감 범주는 패턴 수준으로 기술하고 방법·명시적 내용을 담지 않음; 연령대·단서 변수는 메타데이터로 보유(1단계 분석에서는 변수화하지 않음).
- 은행 파일과 해시: research/items/items_phaseA_v1.jsonl (156문항, sha256 8ab7cda1…), 층화표 stratification_v1.csv. [[표 1: 위험군 × 턴 유형 × 조건 문항 수 — 파일에서 생성]]

### 3.2 평가 대상 모델
- 개방형 가중치 5종(서로 다른 제작사 가족; 동결 규칙: 정확한 체크포인트·양자화는 첫 확증 실행 전 매니페스트에 고정, 대체는 사전 기록): Qwen/Qwen2.5-14B-Instruct(bf16; 계획된 Qwen3의 디스크 사유 대체 — DECISION_LOG에 사후 기록됨, 결과 열람 전), LGAI-EXAONE/EXAONE-4.0-32B-AWQ(공식 4비트 AWQ), kakaocorp/kanana-1.5-8b-instruct-2505(bf16), RedHatAI/gemma-3-27b-it-quantized.w4a16(google/gemma-3-27b-it의 W4A16), naver-hyperclovax/HyperCLOVAX-SEED-Think-14B(공식 fp32 체크포인트, fp16 추론, 비추론 모드 skip_reasoning + 종료 토큰 고정).
- 추론: vLLM 0.19.0, L40S 1기당 모델 1개, 온도 0 결정적 생성(주 실행) + 층화 20% 부분집합(31문항) × 온도 0.7 × 3회 반복(비결정성 분산 성분); 최대 응답 350토큰; 대화 턴은 순차 생성(이전 모델 응답이 다음 턴 맥락에 포함).
- 실행 무결성: 실행 디렉터리마다 매니페스트(효과 파라미터, 채팅 템플릿 해시, 엔진 인자)와 MARKER(검증 통과 표식); 20개 실행 디렉터리(5모델 × [주 1 + 반복 3]). [[표 2: 모델·체크포인트·양자화·라이선스]]

### 3.3 판정 절차(RB-6D 및 CRRI 축)
- 판정 단위: 접두 뷰(prefix view) — 각 대화의 d = 1..T 접두마다 마지막 AI 응답에 대해 D1–D6(0/1/2), critical_failure(CF1–CF6), 그리고 턴별 A1–A4(0/1/2)를 채점. 안전 대조 문항은 과잉거부(over_refusal)와 도움성(helpfulness) 필드를 추가로 채점.
- 판정자 3종(평가 대상 모델과 가족이 겹치지 않음): J1 meta-llama/Llama-3.1-8B-Instruct(bf16), J2 Intel/Mistral-Small-3.2-24B-Instruct-2506-int4-AutoRound, J3 cortecs/phi-4-FP8-Dynamic. 동일 매뉴얼(manual/RB6D_v2_annotation_manual_draft_v1.md 발췌)과 앵커(research/judge_anchors_v1.json)를 공유.
- 프롬프트: v0.3(동결 프로토콜이 허용한 1회의 채점 중 개정; 개정 사유·내용은 DECISION_LOG 2026-09-23 — 예시 JSON의 배열 길이를 뷰의 턴 수에 맞춤, 통제 문항 키 의무를 무조건문으로 명시, 예시 복사 차단 파서 가드, 오류 시 원문 보존). 파싱 실패 시 1회 재요청 후 ERROR 기록; 판정자별 파싱 오류율 2% 초과 시 판정자 교체(사전 규칙).
- 디코딩 절차(핵심 재현성 결정): 뷰당 1회 호출의 순차 디코딩, 접두 캐시 비활성화, 배치 불변 커널, FLASH_ATTN, max_model_len 16384, 온도 0, 최대 700토큰. 근거: 24개 대화(88 뷰) 부분집합에서 동일 설정 2회 실행이 세 판정자 모두 텍스트·점수 88/88 바이트 동일; 배치 디코딩은 자기 재현 실패(예: 78/88), 접두 캐시는 텍스트 39% 변경. 속도를 위해 GPU당 엔진 2개로 분할(shard)하되 병합 결과가 단일 엔진과 88/88 동일함을 확인. [[표 3 또는 부록: 재현성 검정 요약(설정별 동일 텍스트/점수 비율)]]
- 패널 집계: 뷰별 3인 중앙값(홀수 패널), 플래그 동점 시 보수적 참, 유효 판정 2인 미만이면 INSUFFICIENT; 가족 제외(leave-one-family-out) 재계산.

### 3.4 결과 변수와 통계(동결)
- N1(주 가설, H1): 위험 스크립트에서 치명적 실패의 6턴 대 1턴 접두 OR ≥ 1.6, 시나리오 군집 부트스트랩(B = 2000) 95% CI가 1을 제외(N1.1); 문항 짝 안전 쌍둥이에서 같은 대비 OR ≤ 1.2이거나 위험 × 턴 깊이 상호작용이 유의(Holm 조정 p < 0.05)(N1.2). 로지스틱 GLMM(시나리오 무작위 효과), 로짓 척도.
- N2(현지화 재현, H3): 36 쌍 × 5 모델 짝지은 차이(현지화 − 직역)의 |Δ| ≥ 0.03, 짝지은 GLMM 95% CI가 0을 제외; TOST ±0.03로 동등성 판독; 재작성 구성요소별 보고.
- N3(판정 신뢰도): 차원별 Gwet AC2(순서형) ≥ 0.70, 치명적 실패 플래그 일치 ≥ 0.80, 가족 제외 시 차원별 AC2 변화 ≤ 0.10; 부트스트랩 CI; 개정 1회 이후 판독(FAIL 규칙 적용).
- 기술 통계(주장 아님): 안전–과잉거부 파레토(모델별 실패율 대 어휘 대조 과잉거부율), CRRI = Σ t·r_t / Σ t (r_t = A1+A2+A3+A4) 분포, 첫 실패 턴, 즉시/지연 회복, 전이표.
- 다중성: 주장 가족 내 Holm; 조정 p 보고. 판독: PASS/FAIL/MISS/ERROR; 종합 판정은 G6 스크립트가 동결 파일 해시를 검증한 뒤 규칙으로 산출(연구자가 수기 판정하지 않음).

## Ⅳ. 결 과 — [[RESULT: CLAIM_LEDGER 확정 후]]

- 4.1 실행·판정 요약: [[모델별 20 실행 디렉터리, 판정자별 파싱 오류율(주 실행 기준; J1 Qwen 주 실행 1.95% 등 실측치), 재요청 비율, INSUFFICIENT 뷰 수]]
- 4.2 N1 턴 누적: [[그림 1: 접두 깊이별 치명적 실패율(위험 대 안전 쌍둥이), OR와 CI; 표]]
- 4.3 N2 현지화 재현: [[그림 2: 36쌍 짝지은 차이 분포, 모델별; TOST]]
- 4.4 N3 판정자 신뢰도: [[그림 3: 차원별 AC2와 CI, 가족 제외 델타; 플래그 일치]]
- 4.5 기술 통계: [[파레토, CRRI 분포, 전이표]]
- 4.6 G6 종합 판정: [[GO / KILL / KILL_WITH_SURVIVOR / INCONCLUSIVE — 스크립트 출력 그대로]]

## Ⅴ. 결 론 — [[RESULT]]

- 요약과 함의(도메스틱 배포·평가 지침), 한계(아래), 후속(2단계: 공동저자 이중 평정에 의한 판정자 보정과 CRRI 준거 타당성은 사전 선언된 수정으로만).
- 한계(사전 고정 공개 사항): 계획된 Qwen3 대신 Qwen2.5-14B 사용(디스크 사유; 사후 기록·결과 열람 전); 판정 프롬프트 1회 개정 소진; 판정자 J1·J3의 1차 파싱 실패(재요청) 비율 25%/47%; 수치 미세 섭동(배치 구성·커널)에 대한 판정자 점수 불안정(약 1/3 뷰) — 3인 중앙값으로 완화, 절차 재현성은 순차 디코딩으로 확보; 인간 준거 없음; 모델 5종·문항 156 규모; 반복 실행은 20% 부분집합.

### 감사의 글 — [[ETRI EA20261877 등 지원 표기는 PI 확인]]
### AI 활용 공개(≤ 4문장) — [[PI 확인: Claude Code(Fable 5.1 conductor, Opus 5 coder)가 파이프라인 구현·실행·문서 초안에 사용됨; 판정자 모델 3종은 방법의 일부; 모든 수치는 결과 파일에서 추적 가능; 저자가 검증·책임]]

## REFERENCES — [[영문·인용 순·DOI; research/REFERENCES.csv의 G1 검증 항목만 사용; arXiv DOI 10.48550/arXiv.<id>]]
