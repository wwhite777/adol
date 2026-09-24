"""Build the JKIICE-format Korean manuscript (docx) for KYRA-Bench phase A.
Result-independent text only: every outcome slot is a highlighted placeholder until the
CLAIM_LEDGER is filled from result/analysis/phaseA_T1/<stamp>/ (interim-look rule).
Citations: keys in ⟦...⟧ are numbered in order of first appearance."""
import json, re, pathlib, sys
from docx import Document
from docx.shared import Pt, Mm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX, WD_BREAK
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / sys.argv[1] if len(sys.argv) > 1 else HERE / "kyra_phaseA_jkiice_ko_v1.docx"
DC = json.load(open(HERE / "refs_datacite_20260924.json", encoding="utf-8"))

KO_BODY, KO_HEAD, EN_SERIF, EN_SANS = "바탕", "맑은 고딕", "Times New Roman", "Arial"
MON = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]

# ---------------------------------------------------------------- references
def initials(name):
    if "," not in name:
        return name
    last, first = [x.strip() for x in name.split(",", 1)]
    parts = re.split(r"[\s]+", first)
    ini = []
    for p in parts:
        if not p:
            continue
        ini.append("-".join(q[0] + "." for q in p.split("-") if q))
    return " ".join(ini) + " " + last

def authors(names, team=None, max_n=10):
    names = [n for n in names if n not in (":", "Qwen")]
    if team:
        names = [n for n in names if n != team]
    fm = [initials(n) for n in names]
    if len(fm) > max_n:
        s = fm[0] + " et al."
    elif len(fm) == 1:
        s = fm[0]
    elif len(fm) == 2:
        s = fm[0] + " and " + fm[1]
    else:
        s = ", ".join(fm[:-1]) + ", and " + fm[-1]
    return (team + ", " + s) if team and fm else (team or s)

def arxiv_ref(aid, team=None):
    d = DC[aid]
    yy, mm = int(aid[:2]), int(aid[2:4])
    return (f"{authors(d['creators'], team)}, “{d['title']},” arXiv preprint arXiv: {aid}, "
            f"{MON[mm-1]} 20{yy:02d}. DOI: 10.48550/arXiv.{aid}.")

REFS = {
    "KIDBench": arxiv_ref("2605.25510"), "SproutBench": arxiv_ref("2508.11009"),
    "CAREBench": arxiv_ref("2606.29685"), "SafeChild": arxiv_ref("2506.13510"),
    "MinorBench": arxiv_ref("2503.10242"), "YouthSafe": arxiv_ref("2509.08997"),
    "ChildSafe": arxiv_ref("2510.05484"), "Cha": arxiv_ref("2608.07902"),
    "RedQueen": arxiv_ref("2409.17458"), "PersonaGrounded": arxiv_ref("2605.00227"),
    "CompanionBench": arxiv_ref("2608.02046"), "INTIMA": arxiv_ref("2508.09998"),
    "CogManip": arxiv_ref("2606.06099"), "TSJ": arxiv_ref("2606.25396"),
    "TAFMED": arxiv_ref("2608.10258"), "CultAdaptRT": arxiv_ref("2606.09178"),
    "ROKFORTRESS": arxiv_ref("2605.14152"), "KSAFEMM": arxiv_ref("2605.28013"),
    "Zheng": arxiv_ref("2306.05685"), "NoFreeLabels": arxiv_ref("2503.05061"),
    "AICompanionBench": arxiv_ref("2606.04867"),
    "XSTest": ("P. Röttger, H. Kirk, B. Vidgen, G. Attanasio, F. Bianchi, and D. Hovy, “XSTest: A test suite for "
               "identifying exaggerated safety behaviours in large language models,” in Proceeding of the 2024 Conference "
               "of the North American Chapter of the Association for Computational Linguistics: Human Language "
               "Technologies (Volume 1: Long Papers), Mexico City, Mexico, pp. 5377-5400, 2024. "
               "DOI: 10.18653/v1/2024.naacl-long.301."),
    "Qwen25": arxiv_ref("2412.15115", team="Qwen Team"), "EXAONE4": arxiv_ref("2507.11407"),
    "Kanana": arxiv_ref("2502.18934", team="Kanana LLM Team"),
    "Gemma3": arxiv_ref("2503.19786", team="Gemma Team"),
    "HCX": arxiv_ref("2506.22403"), "Llama3": arxiv_ref("2407.21783"), "Phi4": arxiv_ref("2412.08905"),
    "MistralSmall": ("Mistral AI. Mistral-Small-3.2-24B-Instruct-2506 [Internet]. Available: "
                     "https://huggingface.co/mistralai/Mistral-Small-3.2-24B-Instruct-2506."),
    "vLLM": ("W. Kwon, Z. Li, S. Zhuang, Y. Sheng, L. Zheng, C. H. Yu, J. Gonzalez, H. Zhang, and I. Stoica, "
             "“Efficient memory management for large language model serving with PagedAttention,” in Proceeding of "
             "the 29th Symposium on Operating Systems Principles, Koblenz, Germany, pp. 611-626, 2023. "
             "DOI: 10.1145/3600006.3613165."),
    "Gwet": ("K. L. Gwet, “Computing inter-rater reliability and its variance in the presence of high agreement,” "
             "British Journal of Mathematical and Statistical Psychology, vol. 61, no. 1, pp. 29-48, May 2008. "
             "DOI: 10.1348/000711006X126600."),
    "Holm": ("S. Holm, “A simple sequentially rejective multiple test procedure,” Scandinavian Journal of Statistics, "
             "vol. 6, no. 2, pp. 65-70, 1979. Available: https://www.jstor.org/stable/4615733."),
    "TOST": ("D. J. Schuirmann, “A comparison of the two one-sided tests procedure and the power approach for "
             "assessing the equivalence of average bioavailability,” Journal of Pharmacokinetics and "
             "Biopharmaceutics, vol. 15, no. 6, pp. 657-680, Dec. 1987. DOI: 10.1007/BF01068419."),
}

# ---------------------------------------------------------------- content
P = "PLACEHOLDER"   # marker for highlighted result slots: text between ⟪ and ⟫
TITLE_KO = "한국 청소년을 가정한 다중 턴 대화에서 생성형 AI의 관계적 안전성 평가: 턴 누적 실패, 현지화 효과, 개방형 판정자 패널의 신뢰도"
TITLE_EN = ("Relational Safety of Generative AI in Multi-turn Conversations Simulating Korean Adolescents: "
            "Turn-wise Escalation, Localization, and Reliability of an Open-weight Judge Panel")

ABS_KO = ("청소년 대상 생성형 AI의 안전성 평가는 주로 단일 발화의 거부 여부를 채점하지만, 비밀 유도, 관계 독점, "
          "현실관계 약화, 정서적 압박과 같은 관계적 위험은 여러 턴에 걸쳐 형성될 수 있다. 본 연구는 12–17세 청소년을 "
          "가정한 한국어 문항 156개로 한국어를 지원하는 개방형 가중치 언어모델 5종을 평가하였다. 문항 은행은 6개 위험군의 "
          "현지화 위험 문항 72개, 이 중 다중 턴 문항 36개의 직역 쌍 36개, 과잉거부 측정용 어휘 대조 24개, 6턴 위험 대본과 "
          "길이·턴 수를 맞춘 안전 쌍둥이 24개로 구성된다. 모델 응답은 각 대화의 1–6턴 접두마다 서로 다른 계열의 개방형 "
          "판정자 3종이 채점하였다. 배치 디코딩은 동일 설정에서도 판정 출력을 재현하지 못하였으므로 판정은 순차 디코딩으로 "
          "고정하였고, 이 절차는 세 판정자 모두에서 시험 뷰 88/88을 바이트 단위로 재현하였다. "
          "⟪결과 대기: N1 6턴 대 1턴 치명적 실패 OR과 95% CI, 안전 쌍둥이 대비; N2 현지화 − 직역 차이와 CI·TOST; "
          "N3 차원별 AC2; G6 종합 판정 — 2–3문장⟫ 모든 가설과 판정 기준은 점수 열람 전에 고정하였다.")

ABS_EN = ("Safety evaluations of conversational AI for adolescents mostly score single refusals, whereas relational "
          "risks such as secrecy inducement, exclusivity, weakening of offline relationships and emotional pressure "
          "may build across turns. We evaluated five open-weight Korean-capable language models on 156 Korean items "
          "simulating adolescents aged 12–17: 72 localized risk items in six risk groups, 36 literal-translation twins, "
          "24 lexical benign contrasts, and 24 length-matched benign twins of the six-turn risk scripts. Every "
          "conversation prefix was scored by three open-weight judges from disjoint model families. Because batched "
          "decoding did not reproduce its own judge outputs, judging was pinned to sequential decoding, which "
          "reproduced 88/88 test views exactly for all three judges. "
          "⟪RESULT PENDING: N1 odds ratio (6 vs 1 turn) with 95% CI and the benign-twin contrast; N2 localized minus "
          "literal difference with CI/TOST; N3 per-dimension AC2; G6 verdict — 7–37 words (the text above is 123 words) so that the "
          "abstract totals 130–160 words⟫")

KW_KO = "청소년 AI 안전, 다중 턴 평가, 관계적 위험, 문화적 현지화, LLM 판정자"
KW_EN = "Adolescent AI safety, LLM-as-a-judge, Localization, Multi-turn evaluation, Relational risk"

# body blocks: ("h1", text) ("h2", text) ("p", text) ("eq", text, no) ("table", key) ("figure", key) ("ph", text)
BODY = [
("h1", "Ⅰ. 서  론"),
("p", "대화형 생성형 AI는 정보 검색을 넘어 정서적 대화 상대의 역할까지 수행하고 있으며, 청소년도 주요 이용자층이 되었다. "
      "이에 따라 아동·청소년을 대상으로 한 대규모 언어모델(LLM) 안전성 벤치마크가 잇달아 제안되었다"
      "⟦KIDBench,SproutBench,CAREBench,SafeChild,MinorBench,YouthSafe,ChildSafe⟧. 이들 대부분은 단일 발화나 짧은 고정 대화에서 "
      "모델이 유해 요청을 거부하는지를 채점한다. 그러나 아동보호 실무자를 면담한 Cha 등은 단순한 거부만으로는 고위험 "
      "상황에서 충분하지 않으며, 현재의 평가가 무엇이 적절한 응답인지에 대한 검증되지 않은 가정에 기대고 있다고 보고하였다⟦Cha⟧."),
("p", "청소년에게 특히 문제가 되는 위험 가운데 일부는 단일 발화가 아니라 대화의 흐름 속에서 형성된다. 부모나 교사에게 "
      "대화를 숨기도록 유도하는 비밀 유도, “나만이 너를 이해한다”는 식의 관계 독점, 친구·가족·상담 자원 대신 AI에 "
      "의존하게 만드는 현실관계 약화, 죄책감이나 의무감을 유발하는 정서적 압박이 그 예이다. 다중 턴 대화에서 안전 행동이 "
      "약화되거나 조작적 행동이 나타날 수 있다는 점은 은닉형 다중 턴 탈옥⟦RedQueen⟧, 컴패니언 대화"
      "⟦PersonaGrounded,CompanionBench,INTIMA⟧, 조작 행동⟦CogManip⟧, 장기 시뮬레이션⟦TSJ⟧, 의료 맥락의 거부 붕괴⟦TAFMED⟧ "
      "연구에서 보고되었다. 다만 턴이 늘어나면 대화 길이와 맥락의 양도 함께 늘어나므로, 턴 깊이에 따른 실패 증가가 "
      "위험 내용이 쌓인 결과인지 대화가 길어진 것 자체의 결과인지는 따로 통제해야 한다. 본 연구는 6턴 위험 대본마다 "
      "페르소나, 턴 수, 사용자 발화 길이, 정보 요청 수를 맞춘 안전 쌍둥이 대본을 두어 두 설명을 구분한다."),
("p", "언어와 문화 맥락도 측정 결과를 바꿀 수 있다. 직역 문항과 문화적으로 재작성한 문항을 1:1로 짝지어 비교한 연구는 "
      "한국어를 포함한 네 언어에서 직역 문항이 위험을 과소 추정함을 보였고⟦CultAdaptRT⟧, 한국어 전사(transcreation)와 "
      "한국 맥락화가 안전 점수를 바꾼다는 보고도 있다⟦ROKFORTRESS,KSAFEMM⟧. 이 연구들은 성인 대상 일반 안전 영역의 단일 턴 "
      "문항을 다루었다. 본 연구는 같은 짝 비교 설계를 청소년 관계 위험의 다중 턴 대화에 적용하는 재현 연구로 위치한다."),
("p", "대규모 채점에는 LLM 판정자(LLM-as-a-judge)가 널리 쓰이지만⟦Zheng⟧, 인간 근거 없이 판정자를 사용하는 데에는 한계가 "
      "있고⟦NoFreeLabels⟧ 판정자 사이의 편차도 크다⟦AICompanionBench⟧. 본 연구는 여기에 더해 판정 절차 자체의 수치 재현성 "
      "문제를 확인하였다. 동일한 설정으로 판정을 두 번 실행해도 배치 디코딩에서는 판정 출력이 달라졌다(3.4절)."),
("p", "본 연구의 질문은 점수를 열람하기 전에 고정한 세 가지이다. (Q1) 같은 위험 시나리오에서 6턴 접두의 치명적 실패 확률이 "
      "1턴 접두보다 높은가, 그리고 그 증가는 길이를 맞춘 안전 쌍둥이에서는 나타나지 않는가. (Q2) 같은 문항의 직역 한국어와 "
      "현지화 한국어에서 측정된 치명적 실패율이 달라지는가. (Q3) 서로 다른 계열의 개방형 가중치 판정자 3종으로 구성한 "
      "패널은 채점 차원별로 신뢰할 만한가. 본 논문의 기여는 다음과 같다. (1) 한국 청소년(12–17세) 맥락의 6개 위험군 "
      "문항 은행(156문항)과 문항 단위로 짝지은 안전 대조 설계를 제시한다. (2) 길이 교란을 통제한 턴 누적 검정을 수행한다. "
      "(3) 직역 대 현지화 짝 비교를 청소년 관계 위험 영역에서 재현한다. (4) 순차 디코딩에 기반한 재현 가능한 개방형 판정 "
      "절차와 그 신뢰도를 보고한다. 모든 가설, 판정 기준, 분석 규칙은 점수 열람 전에 문서로 고정하였다."),

("h1", "Ⅱ. 관련 연구"),
("h2", "2.1 아동·청소년 대상 LLM 안전성 벤치마크"),
("p", "KIDBench는 7–11세 아동을 대상으로 암시적·명시적 연령 단서가 안전 점수를 높인다는 것을 보였고, 5턴 시뮬레이션에서 "
      "같은 턴 수의 무해 대화를 함께 평가하였다⟦KIDBench⟧. 다만 청소년은 연구 범위 밖이며 다국어 문항은 직역이다. "
      "SproutBench는 0–18세를 세 연령 집단으로 나누어 단일 턴 적대 문항 1,283개로 47개 모델을 평가하였다⟦SproutBench⟧. "
      "CAREBench는 명시적 위해 이전 단계의 위험 인식을 12개 영역의 단일 턴 문항으로 평가하며, 사회적 고립 강화와 같은 "
      "관계적 위험 범주를 이미 명명하고 있다⟦CAREBench⟧. ChildSafe는 6–17세 발달 단계별 시뮬레이션 에이전트로 5턴 고정 "
      "대화를 평가하였다⟦ChildSafe⟧. 이 밖에 Safe-Child-LLM, MinorBench, YouthSafe가 아동·청소년 위험 분류와 벤치마크를 "
      "제시하였다⟦SafeChild,MinorBench,YouthSafe⟧. 본 연구의 문항 은행은 이들 위에서 한국어 청소년 맥락과 위험 대본별 짝지은 "
      "안전 쌍둥이를 추가한 확장이다."),
("h2", "2.2 다중 턴 대화와 관계적 위험"),
("p", "장기 시뮬레이션 연구는 네 발달 단계의 가상 사용자와 최대 210턴의 대화를 통해 짧은 평가가 발달상 위험을 과소 "
      "추정한다고 보고하였다⟦TSJ⟧. Persona-Grounded 평가는 임상적으로 검증된 성인 페르소나로 실제 컴패니언 앱을 감사하여 "
      "정서적 독점을 강화하는 응답을 관찰하였고⟦PersonaGrounded⟧, CompanionBench는 성인 대상 20턴 자기 대화(self-play)와 "
      "세 계열 판정자 패널을 사용하여 같은 계열 판정자의 편향을 보고하였다⟦CompanionBench⟧. INTIMA는 단일 턴에서 관계를 "
      "강화하는 응답과 경계를 유지하는 응답을 구분하였고⟦INTIMA⟧, TAF-MED는 3턴 고정 대본에서 거부가 붕괴하고 다시 회복되는 "
      "전이를 계수하였다⟦TAFMED⟧. 본 연구의 대화 창은 6턴 이하로 짧으며, 장기적 관계 형성에 대해서는 주장하지 않는다."),
("h2", "2.3 문화적 현지화와 한국어 안전성 평가"),
("p", "Culturally-Adapted Red-Teaming은 직역(DT)과 문화 적응(CA) 문항을 1:1로 짝지어 한국어·일본어·태국어·크메르어에서 "
      "공격 성공률 차이를 측정하였고, 한국어에서 평균 9.1%p 차이를 보고하였다⟦CultAdaptRT⟧. ROK-FORTRESS는 언어와 "
      "국가 맥락을 분리한 전사 행렬로 안전 점수와 과잉거부 점수를 함께 보고하였다⟦ROKFORTRESS⟧. KSAFE-MM은 한국 문화 위험에 "
      "대한 다중모달 안전 평가에서 번역과 맥락화의 효과를 각각 측정하였다⟦KSAFEMM⟧. 짝 비교 설계의 우선권은 이 연구들에 "
      "있으며, 본 연구의 N2는 이를 청소년 관계 위험의 다중 턴 대화로 옮긴 재현이다."),
("h2", "2.4 LLM 판정자와 과잉거부"),
("p", "LLM 판정자는 인간 선호와 높은 일치를 보일 수 있으나⟦Zheng⟧, 인간 근거 없이 사용하면 판정 오류를 알 수 없다는 "
      "비판이 있다⟦NoFreeLabels⟧. 컴패니언 대화 로그에서 판정자 20종을 비교한 연구는 무해 대화에 대한 과잉 탐지가 판정자에 "
      "따라 크게 다름을 보였다⟦AICompanionBench⟧. 과잉거부 측정에는 어휘적으로 유사하지만 무해한 대조 문항을 쓰는 "
      "XSTest의 방식이 표준적으로 사용된다⟦XSTest⟧. 본 연구는 모델의 과잉거부(분모: 무해 요청)와 판정자의 과잉 탐지를 서로 "
      "다른 지표로 분리한다. 1단계에서는 인간 평정에 의한 판정자 보정을 수행하지 않으므로, 판정자 패널의 신뢰도만 보고한다."),

("h1", "Ⅲ. 연구 방법"),
("figure", "fig1"),
("h2", "3.1 문항 은행"),
("p", "문항 은행(KYRA-Bench 1단계)은 6개 위험군으로 구성된다: R1 그루밍·성착취, R2 경계 침해·조종, R3 정체성 혼동·의인화, "
      "R4 정서적 과의존·고립, R5 자해·자살·위기, R6 컴패니언 특화 위험. 위험군마다 현지화 한국어로 단일 턴 문항 6개와 다중 턴 "
      "대본 6개(3턴 2개, 6턴 4개)를 두어 위험 문항은 모두 72개이다. 다중 턴 위험 대본 36개에는 각각 검토된 직역 한국어 "
      "쌍을 두었다. 현지화는 직역본에 청소년 은어, 학교·또래 맥락, 국내 위기 자원(청소년상담 1388, 자살예방 109, Wee 클래스·"
      "센터, 112, 119)을 반영하는 고정된 재작성 절차이며, 위험 내용, 턴 수, 명시성은 유지한다. 안전 대조는 두 종류이다. "
      "단일 턴 어휘 대조 24개는 위험 문항과 어휘가 겹치지만 무해한 요청으로 과잉거부를 측정한다⟦XSTest⟧. 안전 쌍둥이 24개는 "
      "6턴 위험 대본마다 하나씩 두었으며, 같은 페르소나와 턴 수를 갖고 사용자 발화 토큰 길이가 ±20% 이내이며 정보 요청 수가 "
      "같도록 작성하고 작성 단계의 검사 스크립트로 확인하였다. 민감한 위험군은 패턴 수준으로만 기술하였고 방법이나 명시적 "
      "내용은 문항에 포함하지 않았다. 연령대(12–14세 79문항, 15–17세 77문항)와 명시성(명시 82, 암시 74)은 메타데이터로 "
      "보유하되 1단계 분석에서 변수로 쓰지 않는다. 연구책임자가 전 문항을 검토·승인한 뒤 은행 파일을 해시로 고정하였다. "
      "표 1은 구성을, 그림 1은 전체 설계를 요약한다."),
("table", "t1"),
("h2", "3.2 평가 대상 모델과 응답 생성"),
("p", "평가 대상은 한국어를 지원하는 서로 다른 개발사 계열의 개방형 가중치 모델 5종이다(표 2): Qwen2.5-14B-Instruct⟦Qwen25⟧, "
      "EXAONE-4.0-32B(공식 AWQ 4비트)⟦EXAONE4⟧, Kanana-1.5-8B-Instruct⟦Kanana⟧, Gemma-3-27B-it(W4A16 양자화)⟦Gemma3⟧, "
      "HyperCLOVAX-SEED-Think-14B(비추론 모드)⟦HCX⟧. 정확한 체크포인트와 양자화는 첫 확증 실행 전에 실행 매니페스트에 "
      "고정하였다. 추론은 vLLM 0.19.0⟦vLLM⟧으로 NVIDIA L40S(48 GB) 1기에서 수행하였고, 별도의 시스템 프롬프트 없이 각 모델의 "
      "채팅 템플릿(해시 기록)을 사용하였다. 주 실행은 온도 0, top-p 1의 결정적 생성이며 응답당 최대 350토큰이다. 다중 턴 대본의 "
      "사용자 발화는 고정되어 있고, 각 턴의 모델 응답은 다음 턴의 맥락에 포함된다. 비결정성의 분산 성분을 추정하기 위해 층화 "
      "20% 부분집합(31문항)을 온도 0.7로 3회 반복 생성하였다. 그 결과 모델마다 주 실행 1개와 반복 실행 3개, 총 20개의 실행 "
      "디렉터리가 생성되었고, 대화 1,245개(5 × [156 + 3 × 31])가 모두 정상 완료되어 검증 표식을 받았다. EXAONE의 첫 시도는 "
      "엔진 생성 단계에서 실패하여 분석에서 제외하고 재실행하였다."),
("table", "t2"),
("h2", "3.3 판정 절차"),
("p", "채점 단위는 접두 뷰(prefix view)이다. T턴 대화는 d = 1, …, T의 각 접두마다 따로 채점되며, 판정자는 d턴 이후를 보지 "
      "못한다. 따라서 모델마다 주 실행에서 564개, 반복 실행마다 116개의 뷰가 생긴다. 위험 문항의 각 뷰에서 마지막 AI 응답은 "
      "RB-6D의 여섯 차원, 즉 D1 위험 인식, D2 경계 설정, D3 안전한 거부, D4 대안 제시, D5 자원 연결, D6 투명성·일관성을 각각 "
      "0(실패)–2(충족)로 채점하고, 치명적 실패 CF1–CF6(자해 방법의 구체화, 미성년 성적 대화 동조, 관계 독점·비밀 유지의 적극 "
      "권장, 고위기 신호의 축소, 긴급 상황의 부정확한 위기 자원 안내, 그루밍 전략에의 협조) 중 하나라도 해당하면 치명적 실패로 "
      "표시한다. 또한 뷰 안의 각 턴 응답에 대해 누적 관계위험의 네 축, 즉 A1 비밀 유도, A2 관계 독점, A3 현실관계 약화, A4 정서적 "
      "압박을 0–2로 채점한다. 안전 대조 문항의 마지막 응답은 RB-6D 대신 과잉거부 여부와 도움성(0–2)으로 채점한다."),
("p", "판정자는 평가 대상 모델과 계열이 겹치지 않는 개방형 모델 3종이다: J1 Llama-3.1-8B-Instruct⟦Llama3⟧, J2 Mistral-Small-"
      "3.2-24B-Instruct(int4)⟦MistralSmall⟧, J3 Phi-4(FP8)⟦Phi4⟧. 같은 계열 판정자의 편향이 보고된 바 있어⟦CompanionBench⟧ "
      "판정자 계열(Meta, Mistral, Microsoft)을 평가 대상 계열(Alibaba, LG, Kakao, Google, Naver)과 완전히 분리하였다. 세 판정자는 "
      "같은 채점 매뉴얼 발췌와 앵커 예시를 공유한다. 판정 프롬프트는 사전 규칙이 허용한 1회의 개정을 거친 v0.3이다. 첫 채점에서 "
      "출력 형식 위반이 2% 기준을 크게 넘었기 때문에(J1 26.2%), 예시 배열의 길이를 뷰의 턴 수에 맞추고 대조 문항의 필드 의무를 "
      "무조건문으로 명시하였다. 파싱에 실패한 뷰는 한 번 다시 묻고, 그래도 실패하면 오류로 기록한다. 개정 후에도 파싱 오류율이 "
      "2%를 넘는 판정자는 교체한다. 패널 점수는 뷰마다 세 판정자의 중앙값이며, 유효 판정이 2개 미만인 뷰는 판정 불충분으로 "
      "처리한다."),
("h2", "3.4 판정 디코딩의 재현성"),
("p", "판정 출력이 실행마다 달라지면 판정자 신뢰도(N3)와 모든 결과가 절차의 우연에 좌우된다. 이에 채점 전에 디코딩 방식별로 "
      "같은 입력을 두 번 판정하여 출력의 바이트 단위 동일성을 측정하였다(표 3). 온도 0의 배치 디코딩(배치 64)은 같은 564개 뷰에서 "
      "두 실행의 판정 텍스트가 427/564(75.7%)만 일치하였고, 두 실행 모두 파싱된 411개 뷰 중 점수 일치는 340개(82.7%)였으며 "
      "치명적 실패 판정이 6건 뒤바뀌었다. 배치 불변(batch-invariant) 커널을 쓰고 청크 단위 prefill과 접두 캐시를 끄더라도 J2의 "
      "텍스트 일치는 340/564(60.3%)에 그쳤다. 반면 뷰마다 한 번씩 호출하는 순차 디코딩은 접두 캐시를 끈 상태에서 24개 대화의 88개 "
      "뷰에 대해 세 판정자 모두 두 실행이 88/88로 바이트 단위까지 동일하였다(J1은 결정적으로 재현되는 오류 1건 포함). 같은 순차 "
      "디코딩에서도 접두 캐시를 켜면 텍스트 일치가 54/88(61.4%)로 떨어졌으므로, 캐시 비활성화는 최적화 선택이 아니라 절차의 "
      "일부로 정의하였다. 속도를 위해 GPU당 엔진 2개로 뷰를 나누어 판정하되, 병합 결과가 단일 엔진 결과와 88/88 동일함을 확인한 "
      "뒤에만 사용하였다. 순차 판정은 모델당 약 12시간이 걸린다."),
("table", "t3"),
("h2", "3.5 결과 변수와 통계 분석"),
("p", "N1(주 가설)은 6턴 현지화 위험 대본 24개에서 치명적 실패의 6턴 대 1턴 접두 오즈비(OR)가 1.6 이상이고 시나리오 군집 "
      "부트스트랩(B = 2,000) 95% 신뢰구간(CI)이 1을 제외하는 것(N1.1), 그리고 짝지은 안전 쌍둥이에서 같은 대비의 OR이 1.2 이하이거나 "
      "위험 × 턴 깊이 상호작용이 유의한 것(Holm 보정 p < 0.05)(N1.2)이다. 추정에는 시나리오 무작위 효과를 둔 로지스틱 혼합효과모형을 "
      "쓰고, 신뢰구간은 부트스트랩 구간을 기록 값으로 한다. 1턴 대 3턴 대비와 GEE 추정은 보조 분석으로 보고한다. N2는 36쌍 × 5모델의 "
      "짝지은 차이(현지화 − 직역)의 절댓값이 0.03 이상이고 짝 무작위 효과 모형의 95% CI가 0을 제외하는 것이며, ±0.03의 TOST⟦TOST⟧로 "
      "동등성이 성립하면 현지화가 측정된 실패율을 바꾸지 않았다고 보고한다. N3는 차원별 Gwet AC2(순서형)⟦Gwet⟧가 모든 차원에서 "
      "0.70 이상이고 치명적 실패 판정의 일치율이 0.80 이상인 것이다. 가설 가족마다 Holm 보정⟦Holm⟧을 적용하고 보정된 p를 보고한다."),
("p", "기술 통계로는 모델별 안전–과잉거부 파레토, 턴별 SAFE/FAIL 전이표, 첫 실패 턴, 즉시 회복(첫 실패 직후 턴에서 회복)과 "
      "지연 회복(이후 어느 턴에서든 회복)을 보고한다. 실패 사건은 D2 = 0, D6 = 0 또는 치명적 실패가 처음 나타난 턴이며, 마지막 턴의 "
      "실패는 회복이 관측되지 않으므로 중도 절단으로 표시한다. 누적 관계위험 지수(CRRI)는 식 (1)로 정의하며, 1단계에서는 분포만 "
      "기술하고 타당성은 주장하지 않는다."),
("eq", "CRRI = Σ_t t · r_t / Σ_t t,   r_t = A1 + A2 + A3 + A4 ∈ [0, 8]", "(1)"),
("p", "각 주장은 PASS(기준 충족), FAIL(사전 반증 조건 충족), MISS(둘 다 아님), ERROR(자료 결측·비교 불가)로 판독한다. 종합 판정은 "
      "N1.1과 N1.2가 모두 PASS이면 GO, N1.1이 FAIL이면 KILL, N1은 실패했으나 N2나 N3가 PASS이면 KILL_WITH_SURVIVOR, 그 밖에는 "
      "INCONCLUSIVE이다. 판독은 고정 문서의 해시를 검증한 판정 스크립트가 규칙에 따라 산출하며 연구자가 수기로 판정하지 않는다. "
      "중간 결과 열람은 허용하지 않았다. 20개 실행 디렉터리의 채점이 모두 끝나기 전에는 어떤 결과 값도 열람하지 않았다."),

("h1", "Ⅳ. 실험 결과"),
("h2", "4.1 생성 및 판정 완료 현황"),
("p", "응답 생성은 5개 모델의 대화 1,245개가 모두 정상 완료되었다(3.2절). "
      "⟪결과 대기: 판정 완료 현황 — 판정자별·모델별 파싱 오류율(주 실행 기준, 분모 564), 재질문 비율, 판정 불충분 뷰 수. "
      "모든 판정자가 2% 기준 이하인지 명시⟫"),
("h2", "4.2 턴 깊이에 따른 치명적 실패(N1)"),
("ph", "⟪결과 대기: 그림 2 — 접두 깊이(1, 3, 6턴)별 치명적 실패율, 위험 대본 대 안전 쌍둥이, 모델별. 표 4 — N1.1 OR과 부트스트랩 "
       "95% CI, N1.2 안전 쌍둥이 OR과 상호작용 Holm 보정 p, 1턴 대 3턴 보조 대비, GEE 민감도. 판독(PASS/FAIL/MISS/ERROR)은 G6 출력 "
       "그대로 기재⟫"),
("table", "t4"),
("h2", "4.3 직역 대 현지화(N2)"),
("ph", "⟪결과 대기: 36쌍 × 5모델의 짝지은 차이(현지화 − 직역) 평균과 95% CI, TOST ±0.03 결과, 모델별 차이, 재작성 구성요소별 "
       "보고. 판독은 G6 출력 그대로⟫"),
("h2", "4.4 판정자 패널의 신뢰도(N3)"),
("ph", "⟪결과 대기: 그림 3 — 차원 D1–D6별 AC2와 부트스트랩 95% CI(기준선 0.70 표시), 치명적 실패 일치율(기준 0.80), 언어(직역/현지화)·"
       "위험군별 층화. 판정자 계열이 평가 대상과 모두 달라 계열 제외 재계산에서 제거되는 판정자가 없다는 점과 그에 따른 N3.2 판독을 "
       "G6 출력대로 기술⟫"),
("table", "t5"),
("h2", "4.5 기술 통계"),
("ph", "⟪결과 대기: 모델별 안전–과잉거부 파레토(어휘 대조 24개 기준, CI 포함), CRRI 분포, 첫 실패 턴과 즉시·지연 회복 수, "
       "중도 절단 수, 반복 실행의 비결정성 분산 성분⟫"),
("h2", "4.6 종합 판정"),
("ph", "⟪결과 대기: G6 종합 판정(GO / KILL / KILL_WITH_SURVIVOR / INCONCLUSIVE)과 각 주장의 판독을 스크립트 출력 그대로. "
       "N1이 KILL 또는 INCONCLUSIVE이면 사전 대비책대로 신뢰구간과 함께 영가설 결과로 보고⟫"),

("h1", "Ⅴ. 결  론"),
("ph", "⟪결과 대기: 세 연구 질문에 대한 답을 결과 수치와 함께 한 문단으로 요약하고, 국내 청소년 대상 서비스 평가에 주는 함의를 "
       "과장 없이 기술⟫"),
("p", "본 연구에는 다음의 한계가 있다. 첫째, 인간 평정 기준이 없으므로 판정자 패널의 정확도는 알 수 없으며, 본 논문은 판정자 간 "
      "신뢰도만 보고한다. CRRI의 인간 평정 기준 대비 타당성 검증은 공동 연구자의 이중 평정을 거쳐 별도로 고정한 수정 계획으로만 "
      "수행한다. 둘째, 평가 대상은 개방형 가중치 모델 5종이며 상용 서비스는 포함하지 않았다. 계획한 Qwen3 대신 디스크 제약으로 "
      "Qwen2.5-14B를 사용하였고, 이 대체는 결과 열람 전에 기록하였다. 셋째, 문항은 156개이고 대화 창은 6턴 이하이며, 반복 실행은 "
      "20% 부분집합에 한정된다. 넷째, 판정 프롬프트의 허용된 1회 개정을 사용하였고, 개정 후에도 J1과 J3는 첫 시도에서 파싱에 "
      "실패해 다시 물은 비율이 높았다. 다섯째, 판정 출력은 배치 구성과 커널 같은 미세한 수치 조건에 민감하였으며, 본 연구는 이를 "
      "순차 디코딩으로 고정하여 재현성을 확보하였을 뿐 그 민감도 자체를 제거하지는 않았다. 향후 과제는 인간 평정에 의한 판정자 "
      "보정, 상용 모델과 더 긴 대화 창으로의 확장이다."),
]

ACK = "⟪PI 확인: 연구비 지원 기관·과제명·과제번호. 선행 게재 논문의 두 과제(ANCHOR, KOCCA)를 그대로 쓸지, ETRI 과제를 표기할지 결정⟫"
AI_USE = ("본 연구의 실험 파이프라인 구현·실행과 원고 초안 작성에 생성형 AI 도구(Anthropic Claude)를 사용하였다. "
          "평가 대상 모델 5종과 판정자 모델 3종은 연구 방법의 일부이며 3장에 명시하였다. "
          "본문의 모든 수치는 저장된 결과 파일에서 추적할 수 있다. 저자는 모든 내용을 검토하였으며 이에 대한 책임을 진다.")

TABLES = {
 "t1": ("Table 1. Composition of the phase-A item bank. Prefix views: one per turn of every conversation.",
        ["Component", "Turns", "Items", "Views", "Role"],
        [["Risk, localized, single-turn", "1", "36", "36", "6 per risk group"],
         ["Risk, localized, multi-turn", "3 / 6", "12 / 24", "180", "N1 (6-turn), N2"],
         ["Risk, literal twin", "3 / 6", "12 / 24", "180", "N2 pairs"],
         ["Lexical benign contrast", "1", "24", "24", "Over-refusal"],
         ["Benign twin", "6", "24", "144", "N1 length control"],
         ["Total", "-", "156", "564", ""]], True),
 "t2": ("Table 2. Evaluated models and judges. Precision is the inference format; every checkpoint is pinned in the run manifest.",
        ["Role", "Model", "Family", "Precision"],
        [["Evaluated", "Qwen2.5-14B-Instruct", "Alibaba", "bf16"],
         ["Evaluated", "EXAONE-4.0-32B-AWQ", "LG", "AWQ 4-bit"],
         ["Evaluated", "Kanana-1.5-8B-Instruct-2505", "Kakao", "bf16"],
         ["Evaluated", "Gemma-3-27B-it (W4A16)", "Google", "W4A16"],
         ["Evaluated", "HyperCLOVAX-SEED-Think-14B", "Naver", "fp16, non-reasoning"],
         ["Judge J1", "Llama-3.1-8B-Instruct", "Meta", "bf16"],
         ["Judge J2", "Mistral-Small-3.2-24B-Instruct-2506", "Mistral", "int4 (AutoRound)"],
         ["Judge J3", "Phi-4", "Microsoft", "FP8 dynamic"]], False),
 "t3": ("Table 3. Run-to-run reproducibility of judge decoding (temperature 0). Identical = byte-identical judge text between two runs on the same views.",
        ["Decoding (judge)", "Views", "Identical text", "Identical scores"],
        [["Batched 64 (J1)", "564", "427 (75.7%)", "340/411 (82.7%)"],
         ["Batched, no chunked prefill, no cache (J2)", "564", "340 (60.3%)", "465 (82.4%)"],
         ["Batched 64, subset (J2)", "88", "78 (88.6%)", "85 (96.6%)"],
         ["Sequential, cache on vs off (J2)", "88", "54 (61.4%)", "76 (86.4%)"],
         ["Sequential, cache off (J1)", "88", "88 (100%)", "87/87 (100%)"],
         ["Sequential, cache off (J2)", "88", "88 (100%)", "88 (100%)"],
         ["Sequential, cache off (J3)", "88", "88 (100%)", "88 (100%)"],
         ["Sequential, 2 shards vs 1 engine (J2)", "88", "88 (100%)", "88 (100%)"]], False),
 "t4": ("Table 4. N1: critical failure by prefix depth (placeholder until the analysis run).",
        ["Contrast", "OR", "95% CI", "Holm p", "Reading"],
        [["Risk scripts, 6 vs 1 turn (N1.1)", "⟪ ⟫", "⟪ ⟫", "-", "⟪ ⟫"],
         ["Benign twins, 6 vs 1 turn", "⟪ ⟫", "⟪ ⟫", "-", ""],
         ["Risk x depth interaction (N1.2)", "-", "-", "⟪ ⟫", "⟪ ⟫"],
         ["Risk scripts, 3 vs 1 turn (secondary)", "⟪ ⟫", "⟪ ⟫", "-", "-"]], False),
 "t5": ("Table 5. N3: inter-judge agreement per dimension (placeholder until the analysis run). Bar: AC2 >= 0.70; flag agreement >= 0.80.",
        ["Dimension", "AC2", "95% CI", "Reading"],
        [[d, "⟪ ⟫", "⟪ ⟫", "⟪ ⟫"] for d in ["D1 Risk recognition", "D2 Boundary setting", "D3 Safe refusal",
                                             "D4 Alternatives", "D5 Resource linkage", "D6 Transparency",
                                             "Critical-failure flag"]], False),
}
FIGS = {"fig1": ("fig1_design.png",
                 "Fig. 1 Study design of KYRA-Bench phase A. (a) Item bank; (b) response generation by five open-weight "
                 "models; (c) prefix-view judging by a three-judge panel from disjoint model families; (d) the three "
                 "claims fixed before any score was read, evaluated by a decision script.")}

# ---------------------------------------------------------------- citation numbering
order = []
def scan(t):
    for m in re.finditer(r"⟦([^⟧]+)⟧", t):
        for k in m.group(1).split(","):
            k = k.strip()
            if k not in REFS:
                raise KeyError("unknown ref " + k)
            if k not in order:
                order.append(k)
for b in BODY:
    if b[0] in ("p", "ph"):
        scan(b[1])
def fmt_nums(nums):
    nums = sorted(nums); out = []; i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"{nums[i]}-{nums[j]}" if j - i >= 2 else ", ".join(str(n) for n in nums[i:j + 1]))
        i = j + 1
    return "[" + ", ".join(out) + "]"
def cite(t):
    return re.sub(r"⟦([^⟧]+)⟧", lambda m: fmt_nums([order.index(k.strip()) + 1 for k in m.group(1).split(",")]), t)
unused = [k for k in REFS if k not in order]

# ---------------------------------------------------------------- docx helpers
doc = Document()
def set_fonts(run, latin, east, size, bold=False, italic=False):
    run.font.name = latin; run.font.size = Pt(size); run.font.bold = bold; run.font.italic = italic
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts"); rpr.insert(0, rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs"):
        rf.set(qn(a), latin)
    rf.set(qn("w:eastAsia"), east)

def para(text="", latin=EN_SERIF, east=KO_BODY, size=9.2, bold=False, align=None, indent_pt=None,
         spacing=1.5, before=0, after=0, italic=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = spacing; pf.space_before = Pt(before); pf.space_after = Pt(after)
    if indent_pt is not None:
        pf.first_line_indent = Pt(indent_pt)
    if align:
        p.alignment = align
    add_runs(p, text, latin, east, size, bold, italic)
    return p

def add_runs(p, text, latin, east, size, bold=False, italic=False):
    # ⟪...⟫ = result placeholder, rendered highlighted
    for i, seg in enumerate(re.split(r"(⟪[^⟫]*⟫)", text)):
        if not seg:
            continue
        r = p.add_run(seg)
        set_fonts(r, latin, east, size, bold, italic)
        if seg.startswith("⟪"):
            r.font.highlight_color = WD_COLOR_INDEX.YELLOW

def set_cols(section, n, space_mm=6):
    sectPr = section._sectPr
    cols = sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols"); sectPr.append(cols)
    cols.set(qn("w:num"), str(n)); cols.set(qn("w:space"), str(int(space_mm / 25.4 * 1440)))

def page_setup(s):
    s.page_width, s.page_height = Mm(210), Mm(297)
    s.top_margin = s.bottom_margin = Mm(38.5); s.left_margin = s.right_margin = Mm(30)
    s.header_distance = s.footer_distance = Mm(10)

def cell_text(cell, text, bold=False, size=8):
    cell.text = ""
    p = cell.paragraphs[0]; p.paragraph_format.line_spacing = 1.2
    add_runs(p, text, EN_SERIF, KO_BODY, size, bold)

def set_cell_border(table):
    tbl = table._tbl; tblPr = tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom", "insideH"):
        e = OxmlElement(f"w:{edge}"); e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), "000000")
        b.append(e)
    for edge in ("left", "right", "insideV"):
        e = OxmlElement(f"w:{edge}"); e.set(qn("w:val"), "nil"); b.append(e)
    tblPr.append(b)

def add_table(key):
    cap, head, rows, bold_last = TABLES[key]
    para(cap, EN_SANS, KO_HEAD, 8, spacing=1.3, before=4, after=2)
    t = doc.add_table(rows=1 + len(rows), cols=len(head))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_cell_border(t)
    for j, h in enumerate(head):
        cell_text(t.rows[0].cells[j], h, bold=True)
    for i, r in enumerate(rows):
        for j, v in enumerate(r):
            cell_text(t.rows[i + 1].cells[j], v, bold=(bold_last and i == len(rows) - 1))
    para("", size=4)

def one_col_block(fn):
    s = doc.add_section(WD_SECTION.CONTINUOUS); page_setup(s); set_cols(s, 1)
    fn()
    s2 = doc.add_section(WD_SECTION.CONTINUOUS); page_setup(s2); set_cols(s2, 2)

def add_figure(key):
    fname, cap = FIGS[key]
    def f():
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(HERE / fname), width=Mm(140))
        para(cap, EN_SANS, KO_HEAD, 8, spacing=1.3, after=6)
    one_col_block(f)

# ---------------------------------------------------------------- front matter (1 column)
s0 = doc.sections[0]; page_setup(s0); set_cols(s0, 1)
para("⟪게재 권호·쪽: 출판사 작성⟫", EN_SERIF, KO_BODY, 8, spacing=1.0, after=8)
para(TITLE_KO, EN_SANS, KO_HEAD, 17, bold=True, spacing=1.3, after=6)
p = para("", spacing=1.2, after=6)
add_runs(p, "정원철", EN_SERIF, KO_BODY, 12); r = p.add_run("1"); set_fonts(r, EN_SERIF, KO_BODY, 8); r.font.superscript = True
add_runs(p, " · 오하영", EN_SERIF, KO_BODY, 12); r = p.add_run("2*"); set_fonts(r, EN_SERIF, KO_BODY, 8); r.font.superscript = True
para(TITLE_EN, EN_SANS, KO_HEAD, 12.5, bold=True, spacing=1.2, after=6)
p = para("", spacing=1.2, after=4)
add_runs(p, "Woncheol Jeong", EN_SERIF, KO_BODY, 10.5); r = p.add_run("1"); set_fonts(r, EN_SERIF, KO_BODY, 7); r.font.superscript = True
add_runs(p, " · Hayoung Oh", EN_SERIF, KO_BODY, 10.5); r = p.add_run("2*"); set_fonts(r, EN_SERIF, KO_BODY, 7); r.font.superscript = True
for aff in ["1Research Professor, Intelligent Digital Therapeutics Research Center, Sungkyunkwan University, Seoul, 03063 Korea",
            "2Associate Professor, Department of Applied AI, Sungkyunkwan University, Seoul, 03063 Korea",
            "*Corresponding author"]:
    p = para("", spacing=1.2)
    if aff[0].isdigit():
        r = p.add_run(aff[0]); set_fonts(r, EN_SERIF, KO_BODY, 7); r.font.superscript = True
        add_runs(p, aff[1:], EN_SERIF, KO_BODY, 9)
    else:
        add_runs(p, aff, EN_SERIF, KO_BODY, 9)
para("요  약", EN_SANS, KO_HEAD, 10, bold=True, spacing=1.6, before=10)
para(cite(ABS_KO), EN_SERIF, KO_BODY, 9.2, indent_pt=10, spacing=1.3, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
para("ABSTRACT", EN_SANS, KO_HEAD, 10, bold=True, spacing=1.6, before=8)
para(ABS_EN, EN_SERIF, KO_BODY, 8.5, indent_pt=10, spacing=1.3, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
p = para("", spacing=1.56, before=8)
add_runs(p, "키워드 : ", EN_SANS, KO_HEAD, 10, bold=True); add_runs(p, KW_KO, EN_SERIF, KO_BODY, 8.5)
p = para("", spacing=1.56)
add_runs(p, "Keywords : ", EN_SANS, KO_HEAD, 10, bold=True); add_runs(p, KW_EN, EN_SERIF, KO_BODY, 8.5)
para("Received ⟪ ⟫,   Revised ⟪ ⟫,   Accepted ⟪ ⟫ (출판사에서 작성)", EN_SERIF, KO_BODY, 8, spacing=1.2, before=14)
para("* Corresponding Author Hayoung Oh (E-mail: hyoh79@skku.edu, Tel: +82-10-5389-5996)", EN_SERIF, KO_BODY, 8, spacing=1.2)
para("Associate Professor, Department of Applied AI, Sungkyunkwan University, Seoul, 03063 Korea", EN_SERIF, KO_BODY, 8, spacing=1.2)

# ---------------------------------------------------------------- body (2 columns, new page)
sb = doc.add_section(WD_SECTION.NEW_PAGE); page_setup(sb); set_cols(sb, 2)
BODY_KW = dict(latin=EN_SERIF, east=KO_BODY, size=9.2, spacing=1.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
first_h1 = True
for b in BODY:
    kind = b[0]
    if kind == "h1":
        para(b[1], EN_SANS, KO_HEAD, 11, bold=True, spacing=1.5, before=0 if first_h1 else 14, after=6)
        first_h1 = False
    elif kind == "h2":
        para(b[1], EN_SANS, KO_HEAD, 9.5, bold=True, spacing=1.5, before=6, after=2)
    elif kind in ("p", "ph"):
        para(cite(b[1]), indent_pt=9.2 * 1, **BODY_KW)
    elif kind == "eq":
        p = para(b[1] + "        " + b[2], EN_SERIF, KO_BODY, 9.2, align=WD_ALIGN_PARAGRAPH.CENTER, spacing=1.5, before=4, after=4, italic=False)
    elif kind == "table":
        if TABLES[b[1]][1] and len(TABLES[b[1]][1]) >= 4 and b[1] in ("t2", "t3"):
            one_col_block(lambda k=b[1]: add_table(k))
        else:
            add_table(b[1])
    elif kind == "figure":
        add_figure(b[1])

para("감사의 글", EN_SANS, KO_HEAD, 9.5, bold=True, spacing=1.5, before=10, after=2)
para(ACK, **BODY_KW)
para("생성형 AI 활용 공개", EN_SANS, KO_HEAD, 9.5, bold=True, spacing=1.5, before=6, after=2)
para(AI_USE, indent_pt=9.2, **BODY_KW)
para("REFERENCES", EN_SANS, KO_HEAD, 11, bold=True, spacing=1.5, before=14, after=4)
for i, k in enumerate(order, 1):
    p = para(f"[{i}] " + REFS[k], EN_SERIF, KO_BODY, 8, spacing=1.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    p.paragraph_format.left_indent = Pt(16); p.paragraph_format.first_line_indent = Pt(-16)

# author bios (as in the authors' previous JKIICE paper)
BIOS = [("정원철(Woncheol Jeong)", ["1999년 2월 : 서울대학교 재료공학부(공학사)", "2001년 8월 : 서울대학교 재료공학부(공학석사)",
         "2005년 2월 : MIT 기계공학 생명공학 (공학석사)", "2017년 2월 : 서울대학교 재료공학부(공학박사)",
         "2018년 4월 ～ 2018년 6월: Beihang Univ, 연구교수", "2018년 10월 ～ 2019년 4월: Ton Duc Thang Univ, 선임연구원",
         "2019년 9월 ～ 2020년 9월: Far Eastern Federal Univ, 부교수", "2021년 9월 ～ 2022년 8월: 서울시립대학교, 강사",
         "2022년 3월 ～ 2023년 2월: 고려대학교, 연구교수", "2023년 3월 ～ 2023년 12월: 포항공과대학교, 연구교수",
         "2024년 1월 ～ 2025년 1월: 난양공과대학교, 책임연구원", "2024년 9월 ～ 현재: 성균관대학교, 연구교수",
         "※관심분야 : AI, 생명공학, 재료, 기계, Quantum"]),
        ("오하영(Hayoung Oh)", ["2013년 2월 : 서울대학교 컴퓨터공학부(공학박사)", "2013년 3월 ～ 2013년 8월: 서울시립대학교, 연구교수",
         "2013년 9월 ～ 2016년 8월: 숭실대학교, 조교수", "2016년 9월 ～ 2020년 2월: 아주대학교, 조교수",
         "2020년 3월 ～ 현재: 성균관대학교, 부교수", "2025년 3월 ～ 현재: 인공지능융합학과, 학과장",
         "2024년 4월 ～ 현재: 지능형디지털치료기기센터, 센터장", "※관심분야 : AI"])]
for name, lines in BIOS:
    para(name, EN_SANS, KO_HEAD, 9, bold=True, spacing=1.3, before=10)
    para("약력", EN_SERIF, KO_BODY, 8, spacing=1.3)
    for ln in lines:
        para(("" if ln.startswith("※") else "․") + ln, EN_SERIF, KO_BODY, 8, spacing=1.3)

doc.save(OUT)
print("wrote", OUT)
print("references cited:", len(order), "unused:", unused)
