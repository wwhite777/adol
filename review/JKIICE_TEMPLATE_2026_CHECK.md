# JKIICE_TEMPLATE_2026_CHECK — the 2026 Korean-journal kit compared with our 2023 kit
Checked 2026-09-27 (fetch times 23:35 GMT). Read-only apart from the saved kit.

## What was fetched
| item | URL | result |
|---|---|---|
| Society notice "국문지 논문 투고양식 및 방법 안내 (2026)" (게시일 2025-12-29, 조회수 3086) | https://kiice.org/board/data/article/271327 | HTTP 200; saved as research/venue/jkiice_template_2026/notice_271327_2026-09-27.html |
| Template ZIP "한국정보통신학회_국문지양식2026.zip" (the notice's attachment link) | https://kiice.org/homepage/boardMedia/207972 | HTTP 200, application/x-zip-compressed, 891,493 bytes; **sha256 73a551e7d2ae7a2f6463b43ae1ead4491059b5c3314db066cb8be049e46bb230** |
| Fee table "국문지 게재료 산출표(2026).png" (the second attachment) | https://kiice.org/homepage/boardMedia/200923 | HTTP 200, PNG 1680×2000; sha256 330a578fdb70783a468ea7ea2a7f780e6c08ccbe3d5143f1b972f329e0ea0f72 |

The notice text says:
- Submission goes through the 국문지 투고 시스템 at https://www.dbpiaone.com/jkiice/index.do. It needs a separate DBpiaOne account, because membership information is not shared with the society homepage.
- "규정을 준수하지 않으면 접수가 반려될 수 있습니다."
- 심사료 is 4만원 for 일반 and 8만원 for 긴급, paid after submission.
- 게재료 cannot be prepaid and is invoiced after acceptance.
- "게재 논문의 모든 저자는 학회 회원이어야 하며, 연회비 및 입회비를 납부해야 합니다."
- Contact: 051-463-3683 / journal@kiice.org.

ZIP contents, unzipped with `unzip -O cp949` into `research/venue/jkiice_template_2026/한국정보통신학회_국문지양식(2026)/`. The zip entries are dated 2026-04-20, so the attachment was replaced after the notice was posted.
| file | sha256 (first 16) | vs 2023 kit |
|---|---|---|
| [일반] 한국정보통신학회논문편집양식_2026.hwp | fd51b56bc926546e | updated (differences below) |
| [Short Paper] 한국정보통신학회논문편집양식_2026.hwp | 71f7eee1971563e3 | updated |
| ★★★심사용 파일 편집양식★★★ 반드시 확인.pdf (2 pp.) | 9558fe0aeba6f290 | **new**; replaces the 2023 "심사투고양식" HWP |
| 심사답변서양식.hwp | d6e4270624a6a52b | **new** (response-to-reviewers form A/B/C) |
| Conflict of Interest Form(JKIICE).hwp | 8ce1d40e343e8fbd | byte-identical to 2023 ("Last update: Jan. 5, 2017") |
| Copyright Transfer Agreement(JKIICE).hwp | 09b8ee57e38555e0 | byte-identical to 2023 |

Text extraction:
- `~/envs/jeongwoncheol_adol/bin/hwp5txt` is present (pyhwp) and worked on every HWP.
- hwp5txt leaves table cells out ("<표>"), so I also ran `hwp5html` to get the text inside tables (header block, ACKNOWLEDGEMENTS box, biography box).
- The PDF was read with pypdf. Its two embedded page images show the author-block and biography regions. The numbered red boxes ①–⑤ are vector overlays that I could not render (no pdftoppm on the host), but the PDF's own text states the rule (quoted below).
- The extracts were kept in the session scratchpad only. The 2023 kit's .txt extracts were not modified.
- The unzipped files carry world-writable modes (666, directory 777) from the archive. Consider `chmod -R go-w` on that folder.

## Differences that matter for submission (2026 vs 2023)
| # | topic | 2023 kit | 2026 kit | our manuscript v4 | action |
|---|---|---|---|---|---|
| 1 | **English abstract length** | no word count in the 2023 full-paper template text. wiki/venues.md recorded "130–160", but that range is not in the 2023 kit. | "★ 영문초록 단어 수 140 ~160 개" (full paper); "100 ~130 개" (short paper) | 136 words (`wc -w`, line 11 of manuscript_v4_text.txt) | **FIX: add 4–24 words** to reach 140–160 |
| 2 | **Review (blind) file** | separate 심사투고양식 HWP with the author block already removed | PDF: "심사용 파일은 블라인드 심사를 위하여 '저자정보를 삭제한 파일'입니다. 원문파일에서 모든 저자 정보, 사사 문구, 저자 약력을 삭제한 한글파일을 심사용 파일에 업로드해주시기 바랍니다. … Short Paper도 동일하게 적용됩니다." | the review copy is kyra_phaseA_jkiice_ko_v4_review.docx (DOCX) | Make the review file from the full manuscript with **all author info (KO/EN names, affiliations, corresponding-author footnote), the funding acknowledgement and both biographies deleted**. It must be a **한글(HWP) file** ("한글파일"). DOCX alone may be refused. The AI-use disclosure names no author and can stay. |
| 3 | Acknowledgements block | "ACKNOWLEDGEMENTS … 내용은 모두 영문으로" | same, plus explicit formatting: heading 윤고딕140 11 pt centred; body "들여쓰기 10, Times New Roman, 9.2, 양쪽정렬" | heading reads "감사의 글"; English body | Rename the heading to **ACKNOWLEDGEMENTS** and set the body to TNR 9.2 pt justified |
| 4 | Algorithm captions | none | "Algorithm. 1 영문제목" caption style added (윤고딕120/Arial 8 pt) | no algorithms | n/a |
| 5 | Reference rules | English, citation order, DOI required, "양식 정확도 30% 이하 → 접수거부" | adds: "9) arXiv" format (`…,” arXiv preprint arXiv: 1406.2661, Jun. 2014. DOI: 10.48550/arXiv.1406.2661.`); the conference example now ends with a DOI; "※ 참고문헌은 7개 이상"; citation example punctuation "[1,4,7]." | 34 refs in the arXiv format, which matches exactly | OK. Apply REFERENCE_AUDIT_v1 fixes. Replacing arXiv entries with the proceedings versions keeps DOIs. |
| 6 | Recent-reference rule | none | **Short Paper only**: "온라인 링크를 제외한 참고문헌의 반 이상이 최근 5년 이내의 자료여야 합니다." Not in the full-paper template. | full paper; most refs are 2023–2026 anyway | none |
| 7 | Biography | photo + name (산돌고딕M 10p) + 약력 (산돌고딕L 7.5) + 관심분야 | same box; example now shows year-first lines ("2024년 – 현재 …"); a template memo says "각 항목 앞 연도 기재" | year-first lines present; photos? (check the HWP build) | Keep year-first; include a photo per author |
| 8 | Header/issue line | Vol. 23 … 2019 | Vol. 29 … 2026 (publisher fills it in) | — | none |
| 9 | Fees | 심사료 4만/8만 (2023 notice) | same 심사료. **게재료 (2026 table)**: general 200,000 KRW up to 6 pp, 30,000/page for p.7–8, 40,000/page from p.9; **+100,000 if an acknowledgement / funded-project sentence is included**; urgent review → 게재료 ×2 (the table's example: 9 pp funded = 400,000; urgent = 700,000). Short paper: 심사료 8만, 게재료 400,000 for 4 pp, no extra pages allowed, +100,000 for acknowledgement. No prepayment. | full paper with a funding acknowledgement | Budget = 200,000 + page surcharge + 100,000. The final page count is not measured here: the HWP layout is not built and the DOCX page count is not the journal layout. |
| 10 | Page limit | none stated | none for full papers (fees scale with pages); short paper fixed at 4 pp | — | none |
| 11 | Unchanged format items | A4; 한글 (template for 아래한글 2010, "글 3.0 이상"); margins top/bottom 38.5 mm, left/right 30 mm, header/footer 10 mm; 2 columns from 서론; body 윤명조120 9.2 pt, 150%; title 산돌고딕B 17 pt; KO names 산돌명조B 12 pt; EN title Arial 12.5 pt (no "A Study on"); EN names TNR 10.5 pt; affiliations TNR 9 pt with explicit position; 요약 윤명조120 9.2 pt; ABSTRACT TNR 8.5 pt; 키워드/Keywords 4–5, English alphabetical; section headings 윤고딕140 11 pt (Ⅰ. 서 론 … Ⅴ. 결 론; no numerals on appendix/references); figures **jpeg/jpg** embedded, **all text inside figures in English**; figure/table captions "Fig. 1 영문제목" / "Table. 1 영문제목"; table text 8 pt; equations numbered at right; references TNR 8 pt, 150% | identical | keywords 5/5, alphabetical OK; positions given; figures exist as .jpg (manuscript/jkiice_v1/fig*_*.jpg) | Captions: the template writes "Table. 1". Our text has "Table 1."; align it. Confirm the jpg versions are the ones embedded. |
| 12 | Author block | positions must be explicit ("직위를 명확히 기입") | same | "Research Professor", "Associate Professor" | OK |
| 13 | AI-use policy | none in the kit | **none in the kit or the notice** (searched for 생성형/ChatGPT/generative/AI; the only hit is the GAN title in the reference example). Consistent with the 2026-09-23 site check (wiki venues.md). | a 4-sentence "생성형 AI 활용 공개" section after the acknowledgement | Keep it; the template has no slot, so place it after ACKNOWLEDGEMENTS. It contains no author information, so it can stay in the review file. |
| 14 | COI and copyright forms | 2017 versions | byte-identical | — | Submit both (corresponding author signs) |
| 15 | Revision response | no form | 심사답변서양식.hwp: per reviewer (A, B, C), quote each comment, then "→ 반영 내용", with page/column/line locations ("pp. 2, 1단 13줄 ~ 2단 11줄") | — | Use it at revision |
| 16 | Submission channel and membership | DBpiaONE (2023 notice) | DBpiaOne, separate account; **all authors must be members with paid dues** | two authors | Both authors need KIICE membership (entry + annual fees) before publication |

## Blocking items before upload
1. The English abstract has 136 words and must have **140–160**.
2. The **review file must be HWP**, with author info, the acknowledgement and the biographies removed.
3. Rename the acknowledgement heading to **ACKNOWLEDGEMENTS** (English, TNR 9.2).
4. Apply the reference corrections in review/REFERENCE_AUDIT_v1.md. The notice warns that non-compliant submissions can be returned, and the template says ≤30% reference-format accuracy means rejection.
5. Budget: 심사료 40,000 KRW, plus 게재료 from 200,000 KRW with +100,000 for the funded-project acknowledgement and page surcharges above 6 pp. Membership dues come on top.
