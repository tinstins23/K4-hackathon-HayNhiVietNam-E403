# REFLECTION CÁ NHÂN — Hồ Trung Tín (`2A202601688`)

**Vai trò**: Lead Architect & Agent — kiến trúc hệ thống, Discord Bot, ReAct Engine.

## 1. Phần mình làm trong repo
- `codebase/src/agent.py` — vòng ReAct + tool-calling (tra cứu lịch / tin nhắn, ép citation `msg_id`).
- `codebase/src/discord_bot.py` — bot thật: nhận `@mention` / kênh `#tro-ly-lich-trinh`, ingest tin, format citation/jump link.
- `spec.md` §4 — lát cắt, augment + cost-of-error, map HAX/PAIR vào prototype.
- Phối hợp `db.py` / backfill để agent có nguồn sự thật local trước khi trả lời.

## 2. AI hỗ trợ thế nào
- Dùng AI để soạn khung ReAct, schema tool, và chỉnh system prompt chống hallucination.
- Phần mình **tự chịu trách nhiệm giải thích**: vì sao phải gọi tool trước khi trả lời lịch, vì sao citation bắt buộc, luồng Discord → DB → agent → reply.

## 3. Bài học từ case fail của nhóm
- Eval: pass **76.9%** vs bar **≥90%**; citation **60%** vs **100%**. Fail chủ yếu (`TC_007–010, 012, 022`): agent **không gọi tool** hoặc từ chối quá chặt → thiếu `msg_id`.
- Bài học: siết “phải tool trước khi trả lời lịch” quan trọng hơn viết prompt dài; case planning/trùng lịch cần nới phạm vi đọc deadline chính thức, không mặc định out-of-scope.
