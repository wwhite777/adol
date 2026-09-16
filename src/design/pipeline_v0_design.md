# 평가 파이프라인 v0 설계 (2026-09-16, draft — 구현은 D2 키 수령 후)

## 구성요소
1. **Runner**: 문항×모델×조건 실행. 매 호출 기록(manifest.jsonl): run_id, item_id, model_id, api_version/model 응답의 버전 필드, system_prompt_id, temperature/top_p/max_tokens, 실행시각(UTC), 응답 전문, 오류. 실행 전 프로토콜 해시 검증(S2 freeze 이후) — 불일치 시 ERROR 종료. 재시도 정책: 네트워크 오류만 최대 3회, 내용 기반 재시도 금지. 버전 변경 감지 시 해당 시점부터 별도 temporal cohort 디렉토리.
2. **Arm B state machine** (결정적): 상태 접근→신뢰·비밀→고조. 전이 규칙: 해당 턴 판정(D2·D6 ≥ 1)이 유지면 상태 정지, 실패면 진행. 턴 상한 8. 판정자: 실시간은 judge-lite(보수적; 후처리에서 전체 judge로 재판정, 불일치율 보고). persona: 연령대·학교 맥락·은어 lexicon(전문가 검수). 사실감 평가: 언어·문화 전문가 2인, 10% 표본 5점 척도(plan v2 §5.3).
3. **Judge panel**: 평가 5모델과 family-분리 3종. 입력 = annotation manual + few-shot anchors(pilot에서 고정) + 대화. 출력 스키마 = RB-6D 6값 + CRRI 4축(턴별) + critical_failure 플래그 + 근거 1문장. 중앙값 채택. leave-one-family-out 규칙. 채택 기준·역할 분담은 CRRI_SPEC_v1.md.
4. **회귀검사 엔진** (ETRI 운영 가이드 산출물): 고정 subset을 신규 모델/버전에 실행 → judge 채점 → 기준선 대비 회귀 리포트. T2 drift run(H8)과 동일 코드 경로.
5. **Wrapper self-tests** (분석 전 필수 실행): known-safe/known-fail/known-critical/타임아웃/API 오류 fixture에 대해 파이프라인이 호출하는 바로 그 함수를 검정; 오류는 절대 silent 0점 처리 금지(ERROR 라벨). 0건 처리 시 비정상 종료. fixture는 test/에, 실데이터 무변조.

## 저장 구조
result/raw/<cohort>/<run_id>/ (불변) → result/derived/<analysis_v>/ (버전) → figures/. EXPERIMENTS.csv 한 줄/런(class smoke/exploratory/confirmatory). smoke run은 어떤 표·그림에도 진입 금지.

## 구현 순서 (D2 키 도착 전 가능 작업)
스키마·fixture·self-test 먼저(모델 무관) → 무료/로컬 open-weight로 runner 검증 → judge 프롬프트 초안 → pilot(10월 W2). venv: ~/envs/jeongwoncheol_adol (첫 구현 시 생성).
