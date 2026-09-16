# REHYDRATE.md — what was deleted and how to regenerate it

- Decrypted upload copies (1.docx, 2.docx) and extracted text (1.txt, 2.txt) lived only in the session scratchpad and are deleted after each session per §3. Originals in upload/ are never deleted.
  Regenerate:
  `gpg --batch --decrypt --passphrase-file /home/wjeong/adol/.upload_pass -o <scratchpad>/1.docx /home/wjeong/adol/upload/1.docx.gpg` (same for 2.docx.gpg).
  Text: python3 stdlib — zipfile.ZipFile(path).read('word/document.xml'), walk w:body children: w:p → join w:t texts; w:tbl → rows of w:tc cell texts. No third-party packages needed.
- Upload provenance (sha256, recorded 2026-09-16):
  d714c2a0426967337572cedbe7ff0c0f0d560df42d97ad03c5d8178e135c4c51  upload/1.docx.gpg  (plan v2, operative)
  3fbb72e559a4eb72328d57939e20f9680117e8b1f11e9ee62bb0a869d335384b  upload/2.docx.gpg  (plan v1, superseded)
- Nothing else has been deleted from this project yet.
