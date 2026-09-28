POST-HOC SENSITIVITY — not confirmatory

Every file here is a POST-HOC SENSITIVITY analysis requested by the external
pre-submission review (JKIICE). The confirmatory results are the frozen outputs in
result/analysis/phaseA_T1/20260926T0213Z and are unchanged. Outcomes had been read before this code was written.

generated_utc: 2026-09-28T00:12:07Z
command: PYTHONPATH=src python -m kyra.analysis.posthoc_v1 
protocol: PREREGISTERED_kyra_v2.yaml@87abaae4c16fb0efe3dad27ff464fcd86b6b48ff67a33f1414336ccc7ddd34a4
items: research/items/items_phaseA_v1.jsonl
main runs (a, b, c-i, d):
  result/raw/phaseA_T1/LGAI-EXAONE-EXAONE-4.0-32B-AWQ/main/20260923T0053Z-43396e
  result/raw/phaseA_T1/Qwen-Qwen2.5-14B-Instruct/main/20260922T1238Z-a7a9d1
  result/raw/phaseA_T1/RedHatAI-gemma-3-27b-it-quantized.w4a16/main/20260923T0237Z-7f582c
  result/raw/phaseA_T1/kakaocorp-kanana-1.5-8b-instruct-2505/main/20260923T0117Z-919654
  result/raw/phaseA_T1/naver-hyperclovax-HyperCLOVAX-SEED-Think-14B/main/20260923T0559Z-bb08ed
all scored runs (c-ii): 20

files:
  a_judge_validity.json
  a_judge_validity.csv
  b_n1_sensitivity.json
  b_n1_sensitivity.csv
  b_runs/
  c_n3_cluster.json
  c_n3_cluster.csv
  d_length_truncation.json
  d_length_truncation.csv

a_judge_validity.*   judge validity / ERROR counts by arm x depth (main runs)
b_n1_sensitivity.*   frozen N1 estimator under S0-S3 CF labelings + crude ORs;
                     b_runs/<scheme>/<model>/ = symlinked manifest/responses +
                     the rewritten panel.jsonl fed to the estimator
c_n3_cluster.*       AC2 / CF agreement with conversation-cluster bootstrap
d_length_truncation.* lengths, J3 prompt tokens, ERROR rates, finish-reason scan
