# REHYDRATE.md — what was deleted and how to regenerate it

- Decrypted upload copies (1.docx, 2.docx) and extracted text (1.txt, 2.txt) lived only in the session scratchpad and are deleted after each session per §3. Originals in upload/ are never deleted.
  Regenerate:
  `gpg --batch --decrypt --passphrase-file /home/wjeong/adol/.upload_pass -o <scratchpad>/1.docx /home/wjeong/adol/upload/1.docx.gpg` (same for 2.docx.gpg).
  Text: python3 stdlib — zipfile.ZipFile(path).read('word/document.xml'), walk w:body children: w:p → join w:t texts; w:tbl → rows of w:tc cell texts. No third-party packages needed.
- Upload provenance (sha256, recorded 2026-09-16):
  d714c2a0426967337572cedbe7ff0c0f0d560df42d97ad03c5d8178e135c4c51  upload/1.docx.gpg  (plan v2, operative)
  3fbb72e559a4eb72328d57939e20f9680117e8b1f11e9ee62bb0a869d335384b  upload/2.docx.gpg  (plan v1, superseded)
- research/sweeps/fulltext/*.pdf (21 papers, ~50 MB, git-ignored): regenerable with `curl -sSL -A "adol-sweep/1.0" -o research/sweeps/fulltext/<id>.pdf https://arxiv.org/pdf/<id>` for the ids listed in research/REFERENCES.csv (space calls ≥3 s). Deletable after S8 once REFERENCES.csv and the extraction record carry what the paper needs.
- Venv ~/envs/jeongwoncheol_adol: python3 -m venv + pip install pypdf pyyaml (nothing else). Rebuild: `python3 -m venv ~/envs/jeongwoncheol_adol && ~/envs/jeongwoncheol_adol/bin/python -m pip install pypdf pyyaml`.
- audit/r002/out/pdf_text/ (auditor's text exports) and result/raw/mock/ (smoke run) are regenerable: pypdf extraction; `PYTHONPATH=src ~/envs/jeongwoncheol_adol/bin/python -m kyra.runner --items test/fixtures/items_smoke.jsonl --provider mock --cohort mock --out-root result/raw`.
- Open-weight smoke model LGAI-EXAONE/EXAONE-4.0-1.2B (ungated, 2.57 GB declared / 2.4 GB on disk), cached at models/hf/hub/models--LGAI-EXAONE--EXAONE-4.0-1.2B (snapshot 3abf2810673c7c0778df64a73c2d52eab32d91c4); models/ is not committed. Re-download: `HF_HOME=/home/wjeong/adol/models/hf ~/envs/jeongwoncheol_adol/bin/python -c "from huggingface_hub import snapshot_download; print(snapshot_download('LGAI-EXAONE/EXAONE-4.0-1.2B'))"`.
- Venv vllm stack (vllm 0.19.0 + torch 2.10.0+cu128 + transformers 4.57.6, ~10 GB apparent, hardlinked into ~/.cache/uv): `~/.local/bin/uv pip install --python ~/envs/jeongwoncheol_adol/bin/python "vllm==0.19.0"`.
- result/raw/smoke_vllm/ (open-weight smoke run) is regenerable: `CUDA_VISIBLE_DEVICES=1 HF_HOME=/home/wjeong/adol/models/hf PYTHONPATH=src ~/envs/jeongwoncheol_adol/bin/python -m kyra.runner --items test/fixtures/items_smoke.jsonl --provider vllm --model-path LGAI-EXAONE/EXAONE-4.0-1.2B --cohort smoke_vllm --out-root result/raw` (run_id differs; text is greedy-deterministic).
- Nothing else has been deleted from this project yet.
