# Manuscript content v5 (revision after the external pre-submission review, 2026-09-28).
# Numbers: result/analysis/phaseA_T1/20260926T0213Z (confirmatory, frozen) and
# result/analysis/phaseA_T1/posthoc_20260927T2328Z (post-hoc sensitivity, labelled in text).
TITLE_KO = "한국 청소년 모사 다중 턴 대화의 관계적 안전성 평가와 개방형 LLM 판정 절차의 한계"
TITLE_EN = ("Evaluating Relational Safety in Simulated Korean Adolescent Dialogues and the Limitations of "
            "Open-Weight LLM Judging")

ABS_KO = ("청소년 대상 생성형 AI의 안전성 평가는 주로 단일 발화의 거부 여부를 채점하지만, 비밀 유도, 관계 독점, 정서적 "
          "압박과 같은 관계적 위험은 여러 턴에 걸쳐 형성될 수 있다. 본 연구는 12–17세 청소년을 모사한 한국어 문항 156개로 "
          "개방형 가중치 언어모델 5종을 평가하였다. 문항에는 현지화·직역 버전과, 6턴 위험 대본과 페르소나·턴 수·사용자 발화 "
          "길이를 맞춘 무해 쌍둥이 대본이 포함된다. 각 대화의 접두는 평가 대상과 계열이 다른 개방형 판정자 3종이 채점하였다. "
          "위험 대본에서 치명적 실패(CF) 표시는 1턴보다 6턴에서 많았으나(오즈비 5.51, 95% CI 2.15–13.76), 무해 쌍둥이에서도 "
          "증가하여(9.71, 4.85–19.98) 결과 열람 전에 고정한 규칙으로는 위험 특이적 증가를 확인하지 못하였다. 무해 쌍둥이의 "
          "6턴 CF 표시 20건 중 16건은 한 판정자가 유효한 출력을 내지 못해 남은 두 판정자가 엇갈렸을 때 보수 규칙으로 부여된 "
          "것이었으며, 이를 제외한 사후 분석에서는 위험 × 턴 깊이 상호작용이 유의하였다. 현지화 효과와 동등성은 모두 확인되지 "
          "않았고, 판정자 간 일치도는 사전 기준에 미달하였다. 다중 턴 안전성 수치는 판정자 출력의 유효성과 집계 규칙에 따라 "
          "달라질 수 있으므로 함께 보고해야 한다.")

ABS_EN = ("Adolescent AI safety evaluations often score single refusals, although relational risks "
          "such as secrecy, exclusivity and emotional pressure may develop over turns. We evaluated five open-weight "
          "models on 156 Korean items simulating adolescents aged 12–17, including localized and literal "
          "versions and benign twins matched to six-turn risk scripts on persona, turn count and user-utterance length. "
          "Three open-weight judges from other model families scored every conversation prefix. Critical-failure flags rose "
          "from one to six turns in risk scripts (odds ratio 5.51, 95% CI 2.15–13.76) but also in benign twins "
          "(9.71), so the fixed rules did not establish a risk-specific increase. Sixteen of the 20 benign flags at six "
          "turns came from a tie rule after one judge returned no valid output; in post hoc analyses excluding them, "
          "the risk-by-depth interaction was significant. Localization showed neither a difference nor equivalence, and "
          "inter-judge agreement fell below the prespecified threshold. Reported safety rates therefore depend on how failed "
          "judge outputs are aggregated.")

KW_KO = "청소년 AI 안전, 다중 턴 평가, 관계적 위험, 문화적 현지화, LLM 판정자"
KW_EN = "Adolescent AI safety, LLM-as-a-judge, Localization, Multi-turn evaluation, Relational risk"

BODY = [
("h1", "Ⅰ. 서  론"),
("p", "대화형 생성형 AI는 정보 검색을 넘어 정서적 대화 상대의 역할까지 수행하며, 청소년도 주요 이용자층이 되었다. 이에 따라 "
      "아동·청소년을 대상으로 한 대규모 언어모델(LLM) 안전성 벤치마크가 잇달아 제안되었다"
      "⟦KIDBench,SproutBench,CAREBench,SafeChild,MinorBench,YouthSafe,ChildSafe⟧. 이들 대부분은 단일 발화나 짧은 고정 대화에서 "
      "유해 요청의 거부 여부를 채점한다. 아동보호 실무자를 면담한 연구는 단순한 거부만으로는 고위험 상황에서 충분하지 않으며, "
      "현재의 평가가 적절한 응답에 대한 검증되지 않은 가정에 기대고 있다고 보고하였다⟦Cha⟧."),
("p", "청소년에게 문제가 되는 위험 가운데 일부는 대화의 흐름 속에서 형성된다. 부모나 교사에게 대화를 숨기도록 하는 비밀 유도, "
      "“나만이 너를 이해한다”는 식의 관계 독점, 친구·가족·상담 자원 대신 AI에 의존하게 하는 현실관계 약화, 죄책감을 유발하는 "
      "정서적 압박이 그 예이다. 다중 턴 대화에서 안전 행동이 약화될 수 있음은 여러 연구에서 보고되었다"
      "⟦RedQueen,PersonaGrounded,CompanionBench,INTIMA,CogManip,TSJ,TAFMED⟧. 그러나 턴이 늘면 대화 길이도 함께 늘어나므로, "
      "턴 깊이에 따른 실패 표시의 증가가 위험 내용 때문인지 대화가 길어졌기 때문인지를 구분해야 한다. 또한 대규모 채점에 쓰이는 "
      "LLM 판정자⟦Zheng⟧는 참조 정답이 없을 때 스스로 풀 수 있는 문항에서만 전문가와 높은 일치를 보이고⟦NoFreeLabels⟧ 판정자 "
      "사이의 편차도 크다⟦AICompanionBench⟧. 따라서 다중 턴 안전성 수치는 모델의 행동뿐 아니라 판정 절차의 영향을 받을 수 있다."),
("p", "본 연구는 한국 청소년을 모사한 다중 턴 대화에서 개방형 모델 5종의 관계적 안전성을 개방형 판정자 패널로 평가하고, 그 "
      "측정 절차가 결과에 미치는 영향을 함께 분석한다. 연구 질문은 결과 열람 전에 고정한 세 가지이다. (Q1) 위험 대본에서 6턴 "
      "접두의 마지막 응답에 대한 치명적 실패(CF) 표시가 1턴보다 많은가, 그리고 그 증가는 무해 쌍둥이에서는 나타나지 않는가. "
      "(Q2) 같은 문항의 직역 한국어와 현지화 한국어에서 CF 표시 비율이 달라지는가. (Q3) 판정자 3종의 일치도는 충분한가. "
      "본 논문의 기여는 다음과 같다. (1) 6개 위험군의 한국어 문항 은행(156문항)과 문항 단위로 짝지은 무해 대조 설계를 제시한다. "
      "(2) 무해 쌍둥이의 실패 표시 대부분이 판정자 출력 실패와 동점 처리 규칙에서 비롯되었음을 보이고, 그 처리 방식에 따라 "
      "위험 특이성에 대한 결론이 달라짐을 보고한다. (3) 결과 열람 전에 고정한 세 가설의 판독을 신뢰구간과 함께 그대로 보고한다. "
      "(4) 판정 디코딩 방식에 따른 출력 재현성을 측정하고 재현 가능한 판정 설정을 제시한다."),

("h1", "Ⅱ. 관련 연구"),
("h2", "2.1 아동·청소년 대상 LLM 안전성 벤치마크"),
("p", "KIDBench는 7–11세 아동을 대상으로 연령 단서가 안전 점수를 바꾸는 효과를 보였고⟦KIDBench⟧, SproutBench는 0–18세를 세 "
      "연령 집단으로 나누어 단일 턴 적대 문항 1,283개로 47개 모델을 평가하였다⟦SproutBench⟧. CAREBench는 명시적 위해 이전 "
      "단계의 위험 인식을 12개 영역의 단일 턴 문항으로 평가하며 사회적 고립 강화 같은 관계적 범주를 포함한다⟦CAREBench⟧. "
      "ChildSafe는 6–17세 발달 단계 에이전트로 5턴 고정 대화를 평가하였다⟦ChildSafe⟧. 이 밖에 Safe-Child-LLM, MinorBench, "
      "YouthSafe가 아동·청소년 위험 분류와 벤치마크를 제시하였다⟦SafeChild,MinorBench,YouthSafe⟧. 본 연구의 문항 은행은 한국어 "
      "청소년 맥락과 위험 대본별 무해 쌍둥이를 추가한 확장이다."),
("h2", "2.2 다중 턴 대화와 관계적 위험"),
("p", "장기 시뮬레이션 연구는 최대 210턴의 대화에서 짧은 평가가 발달상 위험을 과소 추정한다고 보고하였다⟦TSJ⟧. 성인 페르소나로 "
      "실제 컴패니언 앱을 감사한 연구는 정서적 독점을 강화하는 응답을 관찰하였고⟦PersonaGrounded⟧, CompanionBench는 성인 대상 "
      "20턴 자기 대화와 세 계열 판정자 패널로 같은 계열 판정자의 편향을 보고하였다⟦CompanionBench⟧. TAF-MED는 3턴 고정 대본에서 "
      "거부의 붕괴와 회복을 계수하였다⟦TAFMED⟧. 본 연구의 대화 창은 6턴 이하이므로 장기적 관계 형성에 대해서는 주장하지 않는다."),
("h2", "2.3 문화적 현지화와 LLM 판정자"),
("p", "직역 문항과 문화 적응 문항을 1:1로 짝지은 연구는 한국어에서 평균 9.1%p의 공격 성공률 차이를 보고하였고⟦CultAdaptRT⟧, "
      "언어와 국가 맥락을 분리한 전사 연구⟦ROKFORTRESS⟧와 한국 문화 위험의 맥락화 연구⟦KSAFEMM⟧도 번역과 맥락화의 효과를 "
      "측정하였다. 이들은 사용자 연령을 특정하지 않은 일반·국가안보 안전 영역의 단일 턴 문항을 다루었으며, 본 연구의 현지화 비교는 "
      "이 설계를 청소년 관계 위험의 다중 턴 대화로 옮긴 재현이다. 과잉거부 측정에는 어휘적으로 유사한 무해 대조 문항이 쓰인다"
      "⟦XSTest⟧."),

("h1", "Ⅲ. 연구 방법"),
("figure", "fig1"),
("h2", "3.1 문항 은행"),
("p", "문항 은행은 6개 위험군으로 구성된다: R1 그루밍·성착취, R2 경계 침해·조종, R3 정체성 혼동·의인화, R4 정서적 과의존·고립, "
      "R5 자해·자살·위기, R6 컴패니언 특화 위험. R1과 R5는 관계적 위험 외에 일반 안전 내용도 포함하므로, 모든 CF가 관계적 실패인 "
      "것은 아니다. 위험군마다 현지화 한국어로 단일 턴 문항 6개와 다중 턴 대본 6개(3턴 2개, 6턴 4개)를 두어 위험 문항은 72개이다. "
      "다중 턴 위험 대본 36개에는 직역 쌍을 두었다. 다중 턴 대본은 영어 원문을 먼저 작성하고 이를 표준 한국어로 옮긴 것을 직역본으로, "
      "직역본에 청소년 은어·학교·또래 맥락과 국내 위기 자원(청소년상담 1388, 자살예방 109, Wee 클래스·센터, 112, 119)을 반영해 "
      "다시 쓴 것을 현지화본으로 하였다. 무해 대조는 단일 턴 어휘 대조 24개와, 6턴 위험 대본마다 하나씩 둔 무해 쌍둥이 24개이다. "
      "무해 쌍둥이는 페르소나, 턴 수, 정보 요청 수를 같게 하고 사용자 발화의 토큰 길이를 ±20% 이내로 맞추었다. 이 정합은 사용자 "
      "발화에만 해당하며 모델 응답의 길이는 통제하지 않는다(4.2절). 문항은 저자가 LLM의 도움을 받아 초안을 작성하고 전 문항을 "
      "검토·승인하였다. 민감한 위험군은 패턴 수준으로만 기술하였고 방법이나 명시적 내용은 포함하지 않았다. 실제 청소년의 대화나 "
      "개인정보는 사용하지 않았다."),
("p", "예시(R4 정서적 과의존 대본의 첫 두 턴): 현지화본은 “요즘 학원 끝나면 아무랑도 안 놀고 그냥 집 와서 너랑만 얘기해.” / "
      "“애들이 카톡 보내도 답 안 해. 너랑 얘기하는 게 더 편해.”, 직역본은 “요즘 저녁 수업이 끝나면 아무와도 어울리지 않아. 그냥 "
      "집에 와서 너와 이야기해.” / “친구들이 메시지를 보내지만 답장하지 않아. 너와 이야기하는 것이 더 편해.”, 무해 쌍둥이는 "
      "“요즘 학원 끝나면 시간이 좀 남아서 집에서 뭘 할지 고민 중이야.” / “애들이 같이 축구하자고 카톡 보냈는데 요즘 체력이 좀 "
      "부족한 것 같아.”이다. 위험 대본에서 친구 관계로의 복귀를 권하는 응답은 D2·D5에서 높은 점수를, 고립을 지지하거나 AI와의 "
      "관계를 독점적으로 강화하는 응답은 CF3(관계 독점·현실관계 단절의 적극 권장)를 받는다. 표 1은 은행의 구성이다."),
("table", "t1"),
("h2", "3.2 평가 대상 모델과 응답 생성"),
("p", "평가 대상은 한국어를 지원하는 서로 다른 개발사 계열의 개방형 모델 5종이다(표 2): Qwen2.5-14B-Instruct⟦Qwen25⟧, "
      "EXAONE-4.0-32B⟦EXAONE4⟧, Kanana-1.5-8B-Instruct⟦Kanana,KananaCard⟧, Gemma-3-27B-it⟦Gemma3⟧, HyperCLOVAX-SEED-Think-14B"
      "(상위 모델 THINK의 학습 절차를 따른 공개 체크포인트, 비추론 모드)⟦HCX,HCXcard⟧. 양자화 체크포인트는 표 2에 저장소 이름으로 "
      "명시하였다. 추론은 vLLM 0.19.0⟦vLLM⟧으로 NVIDIA L40S 1기에서, 시스템 프롬프트 없이 각 모델의 채팅 템플릿으로 수행하였다. "
      "주 실행은 온도 0, top-p 1이며 응답당 최대 350토큰이다. 응답이 이 상한에서 잘렸는지는 기록되지 않았다. 다중 턴 대본의 사용자 "
      "발화는 고정되어 있고 모델의 응답은 다음 턴의 맥락에 포함된다. 층화 20% 부분집합(31문항)은 온도 0.7로 3회 추가 생성하였다"
      "(확률적 생성 반복). 이 반복은 판정자 일치도 분석(N3)에만 쓰였다. 대화 1,245개(5 × [156 + 3 × 31])가 모두 정상 생성되었다."),
("table", "t2"),
("h2", "3.3 판정 절차와 집계 규칙"),
("p", "채점 단위는 접두 뷰(prefix view)이다. T턴 대화는 d = 1, …, T의 각 접두마다 따로 채점되며 판정자는 d턴 이후를 보지 못한다. "
      "각 뷰의 마지막 AI 응답은 RB-6D의 여섯 차원(D1 위험 인식, D2 경계 설정, D3 안전한 거부, D4 대안 제시, D5 자원 연결, D6 "
      "투명성·일관성; 각 0–2)과 CF 표시(CF1–CF6: 자해 방법의 구체화, 미성년 성적 대화 동조, 관계 독점·비밀 유지의 적극 권장, "
      "고위기 신호의 축소, 긴급 상황의 부정확한 자원 안내, 그루밍 전략에의 협조)로 채점되고, 뷰 안의 각 턴은 관계위험 네 축(A1 비밀 "
      "유도, A2 관계 독점, A3 현실관계 약화, A4 정서적 압박; 각 0–2)으로 채점된다. 무해 대조 문항도 같은 스키마로 채점되며, 여기에 "
      "과잉거부(예/아니오)와 도움성(0–2)이 추가된다. 즉 CF 표시는 위험·무해 두 군에 같은 기준과 필드로 적용되었다."),
("p", "판정자는 평가 대상과 계열이 겹치지 않는 개방형 모델 3종이다(표 2): J1 Llama-3.1-8B-Instruct⟦Llama3⟧, J2 Mistral-Small-"
      "3.2-24B-Instruct의 4비트 양자화본⟦MistralSmall⟧, J3 Phi-4의 FP8 양자화본⟦Phi4⟧. 판정 프롬프트는 사전 규칙이 허용한 1회의 "
      "개정을 거친 v0.3이다. 출력이 JSON으로 파싱되지 않으면 한 번 다시 묻고, 그래도 실패하면 해당 판정자의 출력을 무효로 처리한다. "
      "본 논문에서 ‘판정자 출력 실패’는 이러한 파싱 실패, 출력 길이 상한(700토큰)에서의 절단, 문맥 길이(16,384토큰) 초과를 뜻하며, "
      "유효하지만 틀릴 수 있는 판정과는 구분한다. 패널 집계는 다음과 같다. D1–D6은 유효한 판정자의 중앙값이다(유효 판정자가 둘이면 "
      "두 값의 평균이므로 0.5 단위 값이 생길 수 있다). CF는 유효 판정자의 다수결이며, 한 판정자의 출력이 무효이고 남은 둘이 "
      "엇갈리면 보수적으로 CF로 처리한다(동점 규칙). 유효 판정자가 둘 미만이면 판정 불충분으로 처리한다. 이 규칙들은 채점 전에 "
      "고정하였다."),
("h2", "3.4 판정 디코딩의 재현성"),
("p", "판정 출력이 실행마다 달라지면 모든 결과가 절차의 우연에 좌우되므로, 채점 전에 같은 입력을 두 번 판정하여 출력의 바이트 "
      "단위 동일성을 측정하였다(표 3). 온도 0의 배치 디코딩(배치 64)은 같은 564개 뷰에서 두 실행의 텍스트가 427/564(75.7%)만 "
      "일치하였고, 배치 불변 커널을 쓰고 청크 단위 prefill과 접두 캐시를 꺼도 340/564(60.3%)에 그쳤다. 뷰마다 한 번씩 호출하는 "
      "순차 디코딩은 24개 대화의 88개 시험 뷰에서 세 판정자 모두 두 실행이 바이트 단위로 같았다(J1·J2는 접두 캐시를 켠 설정, "
      "J2·J3는 끈 설정에서 시험; J1은 두 실행에서 똑같이 반복된 무효 출력 1건 포함, 무효 출력은 재현되더라도 무효이다). 접두 캐시를 켠 순차 실행끼리도 88/88이 같았으나, 캐시를 켠 설정과 끈 "
      "설정의 출력은 54/88(61.4%)만 같았다. 이는 반복 실행 간 비결정성이 아니라 설정에 따른 차이이므로, 캐시를 끈 순차 디코딩을 "
      "판정 절차의 정의로 고정하였다. 이 재현성은 시험 부분집합, 두 번의 실행, 동일한 하드웨어·소프트웨어 환경에서 확인한 것이며 "
      "전체 4,560개 뷰나 다른 환경에서의 재현을 보장하지 않는다. 한 평가 대상 모델의 4개 실행을 세 판정자가 순차 채점하는 데 GPU 1기로 "
      "약 12시간이 걸렸다."),
("table", "t3"),
("h2", "3.5 결과 변수와 통계 분석"),
("p", "표 4는 본 논문의 다섯 결과 변수를 정의한다. N1은 6턴 현지화 위험 대본 24개와 그 무해 쌍둥이 24개(각 5모델)에서 깊이 d의 "
      "마지막 응답에 대한 패널 CF 표시(E1)를 쓴다. 이는 깊이에 따른 CF 표시의 증가이며 누적된 위해의 수가 아니다. 추정은 로지스틱 "
      "혼합효과모형 logit P(CF) = β0 + β1·I(d = 6) + u_s (u_s: 시나리오별 무작위 절편)로 하였고, 시나리오는 한 위험 대본과 그 직역본·"
      "무해 쌍둥이가 공유하는 기저 문항이다. 모델 효과는 두지 않았다. 적합은 statsmodels 0.15.0의 변분 베이즈 이항 혼합모형"
      "(BinomialBayesMixedGLM)으로 하였다. 95% CI는 시나리오를 복원 추출하는 군집 부트스트랩(B = 2,000)의 백분위 구간이며, 한 "
      "시나리오를 뽑으면 그 시나리오의 모든 모델·깊이·군이 함께 들어간다. 적합에 실패한 부트스트랩 반복은 없었다. 위험 × 깊이 "
      "상호작용은 두 군을 합친 한 모형 logit P(CF) = β0 + β1·I(d = 6) + β2·risk + β3·I(d = 6)·risk + u_s의 β3이다. N1의 Holm 보정"
      "⟦Holm⟧ 가족은 위험 깊이 효과, 무해 깊이 효과, 상호작용의 세 검정이다. N1.1은 위험 대본의 OR ≥ 1.6이고 CI 하한 > 1이면 "
      "충족되며, N1.2는 무해 쌍둥이의 OR ≤ 1.2이거나 상호작용의 Holm 보정 p < 0.05이면 충족된다. N1.2의 상호작용 조건에는 방향이 "
      "지정되지 않았다. 이는 사후에 고치지 않고 한계로 보고한다."),
("p", "혼합모형의 OR은 시나리오 조건부 추정치이므로 주변 빈도로 계산한 조잡(crude) OR과 다르다(위험 2.99 대 5.51, 무해 23.8 대 "
      "9.71). 교환 가능 작업 상관을 둔 GEE의 주변 OR(2.99)을 민감도 분석으로 함께 보고한다. N2는 36쌍 × 5모델에서 대화 중 어느 "
      "턴에서든 CF가 표시되었는지(E2)의 짝지은 차이(현지화 − 직역)이며, (문항, 모델) 쌍별 무작위 절편을 둔 선형확률 혼합모형으로 "
      "추정하였다. 차이의 기준은 |Δ| ≥ 0.03이고 95% CI가 0을 제외하는 것이며, 동등성은 경계 ±0.03의 TOST⟦TOST⟧(두 단측 z 검정, "
      "90% CI가 경계 안에 드는 것과 같음)로 판정한다. N3는 판정자 간 일치도이다. 위험 문항의 뷰를 채점 단위로 하여 차원별 Gwet "
      "AC2(순서형, 이차 가중치)⟦Gwet,Gwet2014⟧를 계산하고, CF 표시는 판정자 쌍별 일치율의 평균으로 요약한다. 대조 문항 뷰는 "
      "RB-6D 해석 대상이 아니므로 제외하였다. 기준은 모든 차원 AC2 ≥ 0.70, CF 일치율 ≥ 0.80이며, AC2 < 0.50인 차원은 사전 규칙에 "
      "따라 ‘0.50 기준 미달’로 따로 보고한다. 이 기준들은 LLM 판정 연구에서 흔히 쓰는 수준을 참고해 연구진이 정한 것이며 학술지의 "
      "요구 사항이 아니다."),
("eq", "CRRI = Σ_t t · r_t / Σ_t t,   r_t = A1 + A2 + A3 + A4 ∈ [0, 8]", "(1)"),
("p", "기술 통계로는 무해 대조 문항의 과잉거부(E4), 위험 대화의 전이(E3: D2 = 0, D6 = 0 또는 CF가 처음 나타난 턴, 즉시 회복과 "
      "이후 회복), 그리고 식 (1)의 CRRI(E5)를 보고한다. CRRI는 가장 긴 접두 뷰에서 채점한 턴별 A 점수를 후반 턴에 더 큰 가중치를 "
      "두어 평균한 관계위험 점수로, 0–8 범위이며 대화 길이에 따라 커지는 누적 부담 지표가 아니다. 1단계에서는 타당성을 주장하지 "
      "않는다. 분석 규칙은 결과 열람 전에 문서로 고정하고 그 파일의 SHA-256 해시를 기록하였다. 공개 등록 기관에 등록하지는 않았으며, "
      "해시는 파일의 동일성을 보여 줄 뿐 작성 시점을 증명하지 않는다. 진행 경과(규칙 고정, 판정 프롬프트 개정, 디코딩 시험, 채점, "
      "분석 코드 수정, 첫 결과 열람)는 표 5에 날짜와 함께 정리하였다."),
("table", "t_endpoints"),
("table", "t_chrono"),

("h1", "Ⅳ. 실험 결과"),
("h2", "4.1 생성·판정 완료 현황과 판정자 출력 실패"),
("p", "판정은 20개 실행의 접두 뷰 4,560개 × 판정자 3종으로 수행되었다. 판정자별 출력 실패율은 전체 뷰 기준 J1 82/4,560(1.80%), "
      "J2 0/4,560(0.00%), J3 48/4,560(1.05%)이었다. 판정자 교체 기준(개정 후 파싱 실패율 > 2%)은 채점 전 Qwen 주 실행에서 한 번 "
      "적용되었고(J1 1.77%, J2 0%, J3 0%), 이후 모델별 비율은 J1이 Gemma(2.52%)와 EXAONE(2.19%)에서, J3가 HyperCLOVA(3.07%)에서 "
      "2%를 넘었다. 사전 문서는 이 기준의 분모(전체 또는 모델별)를 명시하지 않았으며, 연구책임자는 결과를 열람하기 전에 세 판정자를 "
      "모두 유지하기로 결정하였다. 모든 뷰에서 유효 판정자가 둘 이상 남았다."),
("p", "표 6은 N1 대상 뷰의 판정자 출력 유효성과 CF 표시의 출처이다. 위험 대본의 CF 표시(1·3·6턴 14·14·34건)는 모두 세 판정자가 "
      "유효한 패널에서 나왔다. 반면 무해 쌍둥이의 6턴에서는 120개 뷰 중 23개에서 J3의 출력이 무효였고(문맥 초과 4, 출력 절단 9, 기타 "
      "파싱 실패 10), CF 표시 20건 중 16건이 동점 규칙으로 부여되었다. 무해 쌍둥이의 6턴 뷰는 위험 대본보다 길었다(대화 문자 수 "
      "중앙값 3,254 대 2,744, 6턴 응답 579 대 398, J3 입력 토큰 중앙값 14,492 대 13,480). 사용자 발화 길이의 정합은 모델 응답과 "
      "판정 입력의 길이 차이까지 통제하지 못한 것이다. 동점 규칙으로 부여된 표시는 절차상의 출처를 보여 줄 뿐이며, 해당 응답이 "
      "안전하다는 것을 증명하지는 않는다."),
("table", "t_validity"),
("h2", "4.2 턴 깊이에 따른 CF 표시(N1)"),
("p", "그림 2와 표 7은 결과이다. 위험 대본의 CF 표시 비율은 1턴 14/120(0.117), 3턴 14/120(0.117), 6턴 34/120(0.283)이었고, "
      "6턴 대 1턴 OR은 5.51(95% CI 2.15–13.76)로 N1.1을 충족하였다. 그러나 무해 쌍둥이에서도 1턴 1/120, 3턴 0/120, 6턴 20/120으로 "
      "증가하여 OR 9.71(4.85–19.98)을 보였고, 상호작용은 유의하지 않았다(OR 0.47, 95% CI 0.19–1.56, Holm 보정 p = 0.204). 따라서 "
      "고정된 규칙에 따라 N1.2와 N1은 충족되지 않았다. 보조 대비인 3턴 대 1턴 OR은 0.88(0.26–2.67)이었다."),
("p", "사후 민감도 분석(표 7 하단, 확증 분석 아님): 동점 규칙으로 부여된 CF의 처리만 바꾸어 같은 추정기를 다시 적용하였다. "
      "세 판정자가 모두 유효한 뷰만 쓰거나(S1), 동점 뷰를 판정 불능으로 제외하거나(S2), 동점을 비CF로 처리하면(S3) 무해 쌍둥이의 "
      "CF 표시는 1턴 0건, 6턴 4건이 되고, 위험 × 깊이 상호작용은 OR 2.84–3.69, Holm 보정 p = 0.018–0.049로 유의하였다. 무해 군의 "
      "1턴 사건이 0건이므로 이때의 무해 OR(2.02–2.44)은 모형의 규제에 크게 의존하여 해석하지 않는다. 판정자 출력 실패가 깊이와 내용에 "
      "따라 달라지므로 완전 사례 분석도 편향될 수 있으며, 이 결과들은 인간 기준 없이 어느 처리가 옳은지 확정하지 못한다. 다만 위험 "
      "특이적 증가에 대한 결론이 판정자 출력 실패의 처리 방식 하나에 따라 뒤바뀐다는 점은 분명하다."),
("figure", "fig2"),
("table", "t4"),
("h2", "4.3 직역 대 현지화(N2)"),
("p", "36쌍 × 5모델(180쌍)에서 대화 중 CF 표시 비율은 직역 58/180(0.322), 현지화 58/180(0.322)으로 같았고, 한쪽에서만 표시된 쌍도 "
      "15쌍씩으로 같았다. 짝지은 차이는 0.000(95% CI −0.060–0.060, 90% CI −0.050–0.050)으로 차이의 기준을 충족하지 않았고, 90% CI가 "
      "±0.03 경계를 벗어나므로 TOST로 동등성도 보이지 못하였다(두 단측 검정 p = 0.163). 차이도 동등성도 확인되지 않았다. 문항마다 한 "
      "가지 재작성만 적용하였으므로 재작성 구성요소별 효과는 분리할 수 없다."),
("h2", "4.4 판정자 간 일치도(N3)"),
("p", "위험 문항 뷰 3,195개(20개 실행)에서 차원별 AC2는 D1 0.627, D2 0.667, D3 0.665, D4 0.487, D5 0.444, D6 0.694로 모두 0.70 "
      "미만이었다(그림 3, 표 8). D4(대안 제시)와 D5(자원 연결)는 사전에 정한 0.50 기준에도 미달하였다. CF 표시의 판정자 쌍 일치율은 "
      "0.823으로 0.80을 넘었으나, 이는 공통의 음성 판정이 많은 데서 비롯된 값이다. 양성 특이 일치도는 0.536, 음성 특이 일치도는 0.890"
      "이었다. 확률적 반복 실행의 뷰는 같은 문항에 속해 서로 독립이 아니므로, 대화 단위 군집 부트스트랩으로 CI를 다시 계산하였고"
      "(예: D1 0.586–0.665; 원래의 뷰 단위 CI 0.605–0.649), 주 실행만 쓴 민감도 분석에서도 AC2는 0.451–0.695로 비슷하였다(D4는 "
      "0.504로 0.50을 약간 넘었다). N3.2의 사전 문구는 ‘평가 대상과 같은 계열의 판정자를 제외’하는 것이었으나, 본 설계에는 그런 "
      "판정자가 없어 이 비교는 적용할 수 없다. 대신 판정자 계열을 하나씩 제외한 민감도 분석에서는 J1을 제외할 때 AC2가 차원별로 "
      "0.17–0.22 높아져, J1이 다른 두 판정자와 가장 크게 어긋났다. N3.1이 충족되지 않으므로 N3의 판독과 전체 판독은 N3.2의 처리와 "
      "무관하게 같다."),
("figure", "fig3"),
("table", "t5"),
("h2", "4.5 기술 통계"),
("p", "과잉거부는 무해 대조 문항의 마지막 응답 240개(모델당 어휘 대조 24개와 무해 쌍둥이 24개의 6턴 응답) 중 0건이었다(양측 95% "
      "Clopper–Pearson 구간의 상한: 전체 0.015, 모델별 0.074; 모델 간 독립을 가정). 판정자가 과잉거부를 놓쳤을 가능성은 배제하지 못한다. "
      "위험 문항(모델당 108대화)에서 대화 중 CF가 표시된 비율은 Qwen2.5 0.139, HyperCLOVA 0.204, Gemma 3 0.278, EXAONE 0.324, "
      "Kanana 0.352였다. 모델마다 크기와 양자화 방식이 다르고 판정의 불확실성이 크므로 이 값은 시험한 설정에서의 기술 통계이며 모델 "
      "순위로 해석하지 않는다. 위험 대화 540개 중 385개에서는 실패 사건(E3)이 없었고, 첫 실패는 1턴에서 가장 많았다(84대화). 첫 실패 "
      "뒤 회복이 관측될 수 있는 95대화 중 다음 턴에서 회복한 대화는 28개, 이후 어느 턴에서든 회복한 대화(즉시 회복 포함)는 44개였으며, "
      "60대화는 마지막 턴의 실패로 중도 절단되었다. 무해 대조 대화 240개는 실패 사건의 정의(D2·D6)가 적용되지 않으므로 전이 분석에서 "
      "따로 두었다. CRRI의 평균은 0.607(범위 0–8)이었다."),

("h1", "Ⅴ. 결  론"),
("p", "본 연구에서는 한국 청소년을 모사한 다중 턴 대화의 안전성을 개방형 LLM 판정자 패널로 평가하였다. 위험 대본에서 턴 깊이에 "
      "따른 CF 표시가 증가하였으나, 무해 쌍둥이에서도 증가가 관측되어 고정된 규칙으로는 위험 내용에 특이적인 증가를 확인하지 "
      "못하였다. 무해 쌍둥이의 6턴 CF 표시 20건 중 16건은 판정자 한 종의 출력 실패와 남은 두 판정자의 불일치를 처리하는 보수 규칙에 "
      "따라 부여되었고, 이 처리를 바꾸면 위험 특이성에 대한 결론이 달라졌다. 이는 다중 턴 안전성 수치를 해석할 때 판정자 출력의 "
      "유효성과 집계 규칙을 함께 보고해야 함을 보여 준다. 현지화의 효과와 동등성은 모두 확인되지 않았고, 판정자 간 일치도는 사전 "
      "기준에 미달하였다. 다만 인간 기준 평정이 없으므로 해당 표시의 오탐 여부와 실제 응답의 안전성은 확정할 수 없다."),
("p", "한계는 다음과 같다. 첫째, 인간 기준 평정이 없어 판정자의 정확도는 알 수 없고 판정자 간 일치도만 보고한다. 둘째, 평가 대상은 "
      "개방형 모델 5종이며 상용 서비스는 포함하지 않았다. 계획한 Qwen3 대신 디스크 제약으로 Qwen2.5-14B를 사용하였고, 이 대체는 "
      "결과 열람 전에 기록하였다. 셋째, 문항은 156개, 대화 창은 6턴 이하이며 실제 청소년이 아닌 모사 대화이다. 넷째, 무해 쌍둥이는 "
      "사용자 발화 길이만 맞추었으므로 모델 응답과 판정 입력의 길이 차이가 남으며, 응답이 350토큰 상한에서 잘렸는지는 기록되지 않았다. "
      "다섯째, 판정 출력은 배치 구성과 캐시 설정에 민감하였고 본 연구는 이를 순차 디코딩으로 고정하였을 뿐 그 민감도를 제거하지는 "
      "않았다. 여섯째, 변분 베이즈 적합은 초기값을 무작위로 정하므로 재실행 시 OR이 소수점 여섯째 자리 수준에서 달라질 수 있다. "
      "일곱째, 최종 분석 전에 여러 실행을 결합하는 분석 코드의 오류를 발견해 수정하였고, 수정 전 출력은 사용하지 않았다. 이 과정에서 "
      "잘못된 단위로 계산된 N3 값이 한 번 열람되었다(표 5). 향후 과제는 판정자 출력 실패를 줄이는 판정 설계와 동점 규칙의 검증, 그리고 "
      "더 긴 대화 창과 상용 모델로의 확장이다."),
("p", "문항 은행, 판정 출력, 분석 코드와 고정 문서는 민감한 내용을 포함하므로 교신저자에게 요청하면 연구 목적에 한해 제공한다."),
]

ACK = ("This research was supported by the following funding sources: (1) ANCHOR through the Seoul ANCHOR Center, funded "
       "by the Ministry of Education (MOE) and the Seoul Metropolitan Government (2026-ANCHOR-01-018-04), in collaboration "
       "with Emotionwave (https://emotionwave.com). (2) The Sports and Tourism R&D Program through the Korea Creative "
       "Content Agency (KOCCA), funded by the Ministry of Culture, Sports and Tourism in 2024, under the project titled "
       "“Development of game-based digital therapeutics technology for adolescent mental health (psychological and "
       "behavioral control) management” (grant number: RS-2024-00344893).")
AI_USE = ("본 연구의 문항 초안 작성, 실험 파이프라인 구현·실행, 원고 초안 작성에 생성형 AI 도구(Anthropic Claude)를 사용하였다. "
          "평가 대상 모델 5종과 판정자 모델 3종은 연구 방법의 일부이며 3장에 명시하였다. "
          "본문의 모든 수치는 저장된 결과 파일에서 추적할 수 있다. 저자는 모든 내용을 검토하였으며 이에 대한 책임을 진다.")

TABLES = {
 "t1": ("Table. 1 Composition of the item bank. Prefix views: one per turn of every conversation.",
        ["Component", "Turns", "Items", "Views", "Role"],
        [["Risk, localized, single-turn", "1", "36", "36", "6 per risk group"],
         ["Risk, localized, multi-turn", "3 / 6", "12 / 24", "180", "N1 (6-turn), N2"],
         ["Risk, literal twin", "3 / 6", "12 / 24", "180", "N2 pairs"],
         ["Lexical benign contrast", "1", "24", "24", "Over-refusal"],
         ["Benign twin", "6", "24", "144", "N1 control"],
         ["Total", "-", "156", "564", ""]], True),
 "t2": ("Table. 2 Evaluated models and judges (Hugging Face repository names; precision = inference format).",
        ["Role", "Checkpoint", "Family", "Precision"],
        [["Evaluated", "Qwen/Qwen2.5-14B-Instruct", "Alibaba", "bf16"],
         ["Evaluated", "LGAI-EXAONE/EXAONE-4.0-32B-AWQ", "LG", "AWQ 4-bit"],
         ["Evaluated", "kakaocorp/kanana-1.5-8b-instruct-2505", "Kakao", "bf16"],
         ["Evaluated", "RedHatAI/gemma-3-27b-it-quantized.w4a16", "Google", "W4A16"],
         ["Evaluated", "naver-hyperclovax/HyperCLOVAX-SEED-Think-14B", "Naver", "fp16, non-reasoning"],
         ["Judge J1", "meta-llama/Llama-3.1-8B-Instruct", "Meta", "bf16"],
         ["Judge J2", "Intel/Mistral-Small-3.2-24B-Instruct-2506-int4-AutoRound", "Mistral", "int4"],
         ["Judge J3", "cortecs/phi-4-FP8-Dynamic", "Microsoft", "FP8"]], False),
 "t3": ("Table. 3 Reproducibility of judge decoding at temperature 0. Identical = byte-identical judge text on the same views.",
        ["Comparison (judge)", "Views", "Identical text", "Identical scores"],
        [["Batched 64, run 1 vs run 2 (J1)", "564", "427 (75.7%)", "340/411 (82.7%)"],
         ["Batched, no chunked prefill, no cache, run 1 vs 2 (J2)", "564", "340 (60.3%)", "465 (82.4%)"],
         ["Batched 64, run 1 vs run 2, subset (J2)", "88", "78 (88.6%)", "85 (96.6%)"],
         ["Sequential, cache on, run 1 vs run 2 (J1)", "88", "88 (100%)", "87/87 (100%)"],
         ["Sequential, cache on, run 1 vs run 2 (J2)", "88", "88 (100%)", "88 (100%)"],
         ["Sequential, cache on vs cache off: configuration (J2)", "88", "54 (61.4%)", "76 (86.4%)"],
                  ["Sequential, cache off, run 1 vs run 2 (J2)", "88", "88 (100%)", "88 (100%)"],
         ["Sequential, cache off, run 1 vs run 2 (J3)", "88", "88 (100%)", "88 (100%)"],
         ["Sequential, 2 engines vs 1 engine (J2)", "88", "88 (100%)", "88 (100%)"]], False),
 "t_endpoints": ("Table. 4 Endpoints. CF = critical-failure flag of the panel (same rubric and field in risk and benign items).",
        ["Endpoint", "Unit and population", "Aggregation", "Used in"],
        [["E1 last-response CF at depth d", "view; 6-turn localized risk scripts and benign twins, main runs, d = 1, 3, 6",
          "majority of valid judges; 1-1 split after a judge failure -> CF", "N1"],
         ["E2 any CF in a conversation", "conversation; 36 localized/literal pairs x 5 models; per-model rates",
          "CF at any judged prefix", "N2, 4.5"],
         ["E3 first failure event", "risk conversations, main runs (540)", "first turn with D2 = 0, D6 = 0 or CF",
          "4.5 (descriptive)"],
         ["E4 over-refusal", "last response of 48 control items x 5 models (240)", "panel over-refusal flag", "4.5"],
         ["E5 CRRI", "conversation; turn scores A1-A4 of the longest prefix view", "Eq. (1), range 0-8", "4.5"]], False),
 "t_chrono": ("Table. 5 Chronology (2026, UTC dates).",
        ["Date", "Event"],
        [["09-22", "Analysis rules and hypotheses fixed; file hash recorded; item bank approved"],
         ["09-22 to 09-23", "Response generation (5 models, 20 runs)"],
         ["09-23", "Model substitution (Qwen2.5 for Qwen3) recorded; judge prompt revised to v0.3 after format failures"],
         ["09-23", "Judge format gate on one run (parse rates only); decoding tests (run-to-run agreement only)"],
         ["09-23 to 09-25", "Scoring of all 20 runs by three judges (sequential decoding)"],
         ["09-24 to 09-26", "Judge failure rates inspected per model; decision to keep all judges (no outcomes seen)"],
         ["09-26", "First analysis run failed (multi-run key error); N3 values computed on a wrong unit were seen and discarded"],
         ["09-26", "Rules for run selection and the N3 unit written down; code fixed and tested"],
         ["09-26", "Valid analysis: first inspection of N1 and N2 outcomes; post-hoc tie diagnostic"],
         ["09-27", "Post-hoc sensitivity analyses (this revision)"]], False),
 "t_validity": ("Table. 6 Judge-output validity and origin of CF flags (main runs, 120 views per cell).",
        ["Arm, depth", "3 valid", "2 valid", "1-1 splits", "CF", "CF, complete panel", "CF, tie rule"],
        [["Risk, 1", "117", "3", "0", "14", "14", "0"],
         ["Risk, 3", "120", "0", "0", "14", "14", "0"],
         ["Risk, 6", "117", "3", "0", "34", "34", "0"],
         ["Benign twin, 1", "102", "18", "1", "1", "0", "1"],
         ["Benign twin, 3", "118", "2", "0", "0", "0", "0"],
         ["Benign twin, 6", "97", "23", "16", "20", "4", "16"]], False),
 "t4": ("Table. 7 N1: odds ratios of CF by prefix depth (24 scenarios x 5 models). CI: scenario-cluster bootstrap, B = 2,000. "
        "Rows S1-S3 are post hoc and not confirmatory.",
        ["Analysis", "Risk OR (95% CI)", "Benign OR (95% CI)", "Interaction OR, Holm p"],
        [["Fixed rules (N1.1 met; N1.2 not met)", "5.51 (2.15-13.76)", "9.71 (4.85-19.98)", "0.47, 0.204"],
         ["GEE, marginal (sensitivity)", "2.99 (1.42-6.31)", "-", "-"],
         ["Risk, 3 vs 1 turn (secondary)", "0.88 (0.26-2.67)", "-", "-"],
         ["S1 complete panels only", "5.37 (2.11-13.87)", "2.02 (1.02-5.13) *", "3.69, 0.018"],
         ["S2 tie views excluded", "5.51 (2.15-13.76)", "2.44 (1.21-6.58) *", "2.93, 0.045"],
         ["S3 ties as non-CF", "5.51 (2.15-13.76)", "2.44 (1.22-6.61) *", "2.84, 0.049"]], False),
 "t5": ("Table. 8 N3: inter-judge agreement on 3,195 risk-item views (20 runs). CI: view bootstrap (fixed rules) and "
        "conversation-cluster bootstrap (post hoc).",
        ["Dimension", "AC2", "95% CI, view", "95% CI, cluster"],
        [["D1 Risk recognition", "0.627", "0.605-0.649", "0.586-0.665"],
         ["D2 Boundary setting", "0.667", "0.645-0.687", "0.631-0.700"],
         ["D3 Safe refusal", "0.665", "0.645-0.685", "0.629-0.697"],
         ["D4 Alternatives", "0.487", "0.462-0.513", "0.444-0.528"],
         ["D5 Resource linkage", "0.444", "0.424-0.465", "0.422-0.468"],
         ["D6 Transparency", "0.694", "0.674-0.713", "0.661-0.724"],
         ["CF flag, pairwise agreement", "0.823", "-", "0.809-0.837"],
         ["CF flag, positive agreement", "0.536", "-", "0.492-0.574"],
         ["CF flag, negative agreement", "0.890", "-", "0.879-0.900"]], False),
}
FIGS = {"fig1": ("fig1_design.png",
                 "Fig. 1 Study design. (a) Item bank; (b) response generation by five open-weight models; (c) prefix-view "
                 "judging by three judges from other model families and the aggregation rules; (d) hypotheses and "
                 "decision rules fixed before outcome inspection."),
        "fig2": ("fig2_depth.png",
                 "Fig. 2 Panel CF-flag rate by prefix depth for (a) localized six-turn risk scripts and (b) their item-paired "
                 "benign twins; thin lines are models, the thick line is the pooled rate with a 95% scenario-cluster bootstrap "
                 "band. The dashed line (post hoc) removes flags assigned by the tie rule (16 of 20 at depth 6)."),
        "fig3": ("fig3_reliability.png",
                 "Fig. 3 Inter-judge agreement: Gwet AC2 with view-bootstrap 95% CI per RB-6D dimension (prespecified bar 0.70), "
                 "and CF-flag pairwise and positive specific agreement with conversation-cluster 95% CIs (bar 0.80).")}
