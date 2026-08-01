# REFLECTION CÁ NHÂN — Hồ Trung Tín (`2A202601688`)

**Vai trò**: Kiến trúc agent, Discord bot, ReAct loop, mock UI, chỗ khó §5–§6, golden set + eval.

## 1. Phần mình làm trong repo
- `codebase/src/agent.py` — vòng ReAct + tool-calling (tra cứu lịch / tin nhắn, ép citation `msg_id`).
- `codebase/src/discord_bot.py` — bot thật: `@mention` / `#tro-ly-lich-trinh`, ingest tin, format citation/jump link.
- `codebase/mock_ui/index.html` — mock UI Discord demo flow chính.
- `spec.md` §5–§6 — 4 lớp chỗ khó + kịch bản và 4 đường trải nghiệm.
- `eval/golden_set.json` + `eval/eval_results.md` — golden set và bảng kết quả chạy eval.
- `spec.md` §4 — lát cắt, augment + cost-of-error, map HAX/PAIR vào prototype.

## 2. AI hỗ trợ thế nào
- Dùng AI để soạn khung ReAct, case eval, và chỉnh prompt chống hallucination.
- Phần mình **tự chịu trách nhiệm giải thích**: luồng Discord → DB → agent → reply; vì sao bắt buộc tool + citation; cách golden set map 4 lớp chỗ khó.

## 3. Bài học từ case fail của nhóm...
- Eval: pass **76.9%** vs bar **≥90%**; citation **60%** vs **100%**. Fail chủ yếu (`TC_007–010, 012, 022`): agent **không gọi tool** hoặc từ chối quá chặt → thiếu `msg_id`.
- Bài học: siết “phải tool trước khi trả lời lịch” quan trọng hơn viết prompt dài; case planning/trùng lịch cần nới phạm vi đọc deadline chính thức, không mặc định out-of-scope.
