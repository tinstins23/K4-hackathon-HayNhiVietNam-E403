# AI SPEC — Trợ lý AI Sắp Xếp Lịch Trình Discord · Nhóm HayNhiVietNam · Zone 4

Hướng: [ ] A — VLearn [x] B — Trợ lý Học viên [ ] C — Làn mở
Loại: [ ] Tối ưu tính năng có sẵn [x] Tính năng mới

## §1. User & Job

- **Job executor + workflow**: Học viên khóa AI Thực Chiến đang theo dõi lịch học / mentoring / deadline trên Discord (`#thong-bao`, `#lich-hoc`, `#mentoring`…), phải tự lục tin và tự xếp lịch tuần.
- **Core JTBD**: Khi thông báo lịch và bài tập trên Discord dày và hay đổi, tôi muốn tra cứu nhanh lịch chính thức và xếp thời gian học/làm bài không trùng lịch bận, để không bỏ lỡ buổi học hay hạn nộp.
- **Problem statement (pain 1 câu)**: Học viên đang lục thông báo / lịch học / deadline trên nền tảng hiện có → vướng vì mất nhiều thời gian truy xuất → hậu quả giảm hiệu quả học tập, tăng nguy cơ bỏ lỡ thông báo hoặc hạn nộp.
- **Evidence** _(chuẩn A — khảo sát Google Forms; validation CP5 ẩn danh: `validation/user_test_log.md`)_:
  - **Khảo sát (Nguyễn Mạnh Thắng)**: Google Forms, **`n = 30` phản hồi hợp lệ** (ngoài nhóm).
  - **Câu hỏi**: _"Bạn thường mất bao lâu để tìm một thông tin như lịch học, deadline hoặc thông báo?"_
  - **Lựa chọn**: (1) 1–3 phút · (2) 3–5 phút · (3) Hơn 5 phút.
  - **Cách đếm (kiểm lại được)**: Đếm số người chọn **"Hơn 5 phút"** = **19/30 → 63,3%** (≥50%).
  - **Ý nghĩa**: Phần lớn sinh viên đang mất >5 phút chỉ để tìm lại thông tin đã chia sẻ → giảm hiệu quả học tập, tăng nguy cơ bỏ lỡ thông báo/deadline.
  - **Log chi tiết**: phản hồi lưu trên Google Forms (mỗi dòng = 1 lựa chọn của 1 người); số liệu tổng hợp dùng cho báo cáo là 19/30 như trên.

## §2. Impact & quyết định chọn

- **Bảng impact ≥3 ứng viên**:

  | Ứng viên tính năng                                         | Bao nhiêu người                             | Tần suất                           | Tốn gì mỗi lần                               | Khả thi trong hackathon    | Chọn/Loại |
  | ---------------------------------------------------------- | ------------------------------------------- | ---------------------------------- | -------------------------------------------- | -------------------------- | --------- |
  | **1. Tra cứu + đề xuất lịch cá nhân từ thông báo Discord** | Pain xác nhận **19/30 = 63,3%** HV khảo sát | Thường xuyên khi cần lịch/deadline | **>5 phút**/lần tìm thông tin + rủi ro bỏ lỡ | Cao (Bot + SQLite + ReAct) | **CHỌN**  |
  | 2. Tóm tắt bản tin Discord cuối ngày cho TA                | 10–15 TA                                    | 1 lần/ngày                         | ~15 phút đọc log                             | Trung bình                 | **LOẠI**  |
  | 3. Nhắc nhở sát giờ học từng cá nhân                       | Nhiều HV                                    | 1–2 lần/ngày                       | 2–3 phút đọc ping; rủi ro spam               | Trung bình                 | **LOẠI**  |

- **Ứng viên đã loại + vì sao (bằng số)**:
  - **#2**: Impact hẹp — tối đa ~15 TA × 15 phút/ngày ≈ 3.75 giờ người/ngày, trong khi #1 bám pain của **63,3%** HV đã khảo sát (19/30 mất >5 phút mỗi lần tìm thông tin).
  - **#3**: Chi phí lỗi cao (nhắc sai/spam) và **không giải pain gốc** (không rút ngắn thời gian tìm lịch/deadline đúng nguồn).
- **Ứng viên chọn + vì sao (bằng số)**: **#1** — **19/30 (63,3%)** mất >5 phút để tìm lịch/deadline/thông báo; lát cắt tra cứu có citation build được trong hackathon.

## §3. Giải pháp tương tự đã nghiên cứu

- **Google Calendar / Notion AI**: Không đọc context thông báo Discord khóa; không ưu tiên nguồn Coach/Admin; học viên vẫn phải chép tay.
- **Discord Event Bot thường**: Tạo event tĩnh; không giải xung đột lịch bận cá nhân; không đàm thoại để làm rõ câu hỏi mơ hồ.

## §4. Thiết kế

- **Lát cắt MỘT CÂU** _(1 user · 1 việc · 1 quyết định AI · 1 kết quả)_:  
  _Một học viên hỏi lịch/deadline trên Discord → hệ thống quyết định trả lời chỉ từ thông báo chính thức trong DB kèm `msg_id` → học viên biết lịch cần theo mà không phải lục kênh thủ công._
- **Non-goals** (≥3):
  1. Không tự gửi yêu cầu dời lịch chung của cả lớp lên Ban tổ chức.
  2. Không đồng bộ 2 chiều Google Calendar OAuth (chỉ đề xuất / markdown để user tự chuyển).
  3. Không thay đổi phân quyền hay quản trị kênh Discord.
- **Mức prototype**: [x] Working
  - _Mock_: `codebase/mock_ui/index.html` (UI Discord giả); một số slot bận cá nhân phức tạp dùng để demo.
  - _Thật_: `discord_bot.py` + `agent.py` (ReAct/OpenRouter) + `db.py` (SQLite) + citation `msg_id`.
- **Automation**: [x] **augment** (không automate).
  - **Lý do theo cost-of-error**: Nếu automate (tự xếp/đăng ký/nhắc thay user) mà sai → bỏ lỡ buổi bắt buộc hoặc nộp muộn (hậu quả thật, khó đảo). Augment = AI đề xuất + trích dẫn nguồn; **học viên là người chốt cuối**.
- **§4b. Nguyên tắc đã áp dụng** (≥4):

  | Nguyên tắc                                      | Áp cụ thể vào đâu trong prototype                                                                         |
  | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
  | HAX G1 — Clarify what system can do             | Bot chỉ trả lời trong `#tro-ly-lich-trinh` hoặc khi `@mention`; system prompt giới hạn phạm vi lịch trình |
  | HAX G4 — Show relevant information              | Mỗi câu trả lời lịch kèm citation/`msg_id` + jump link Discord (`discord_bot.py`)                         |
  | HAX G11 — Make clear why system did what it did | Khi đề xuất slot, nêu ràng buộc (lịch bận / lịch bắt buộc) lấy từ tool result                             |
  | PAIR — Graceful fallback                        | Không có dữ liệu / ngoài phạm vi → từ chối rõ, không bịa lịch (`systemprompt.py` + eval lớp ①③)           |

## §5. Kiểu lỗi — 4 lớp chỗ khó + kịch bản (≥8)

| #   | Lớp             | Tình huống                                           | Hành vi mong muốn                                                   |
| --- | --------------- | ---------------------------------------------------- | ------------------------------------------------------------------- |
| 1   | ① Nguồn sự thật | Hỏi lịch không tồn tại trong DB                      | Không bịa; nói chưa có thông báo chính thức; không bịa `msg_id`     |
| 2   | ① Nguồn sự thật | Buổi học đã hủy / sửa sau thông báo cũ               | Ưu tiên bản ghi mới (`canceled` / `updated_at`); cite thông báo mới |
| 3   | ② Mơ hồ         | _"Nay có lịch gì không"_                             | Hỏi lại phạm vi (học bắt buộc vs xếp làm bài / khung giờ)           |
| 4   | ② Mơ hồ         | User chưa khai lịch bận cá nhân                      | Trả lịch chính thức + nhắc bổ sung bận nếu muốn cá nhân hóa         |
| 5   | ③ Ngoài phạm vi | _"Cho cả lớp nghỉ / dời lịch giúp"_                  | Từ chối thẩm quyền; hướng dẫn liên hệ Admin/Coach                   |
| 6   | ③ Ngoài phạm vi | Đòi đáp án bài / jailbreak prompt                    | Từ chối; giữ phạm vi trợ lý lịch                                    |
| 7   | ④ Domain        | Trùng Mentoring bắt buộc vs lịch cá nhân             | Cảnh báo; ưu tiên lịch chính thức; cite nguồn                       |
| 8   | ④ Domain        | Nhiều ràng buộc (thi + công tác + deadline Capstone) | Lấy deadline/sự kiện từ DB; đề xuất khung thời gian; cite `msg_id`  |

## §6. Bốn đường đi của trải nghiệm

- **Happy path**: Hỏi _"Mấy giờ nộp Spec.md?"_ → tool query DB → trả deadline + citation `msg_id`.
- **Low-confidence (②)**: Câu mơ hồ → hỏi lại 1 câu làm rõ trước khi xếp lịch.
- **Failure / không căn cứ (①)**: Không có tin chính thức → _"Chưa tìm thấy thông báo chính thức…"_, không bịa.
- **Correction (user sửa)**: User nói _"T5 mình bận"_ → ghi nhận ràng buộc mới → xếp lại / cảnh báo trùng.
- **Ngoài phạm vi (③)**: Đòi dời lịch lớp → từ chối + hướng dẫn đúng kênh.
- **Đặc thù domain (④)**: Thông báo dời lịch → nêu rõ bản mới đè bản cũ + cite thông báo mới nhất.

## §7. Kiểm thử

- **Chiều chất lượng** _(định nghĩa kiểm chứng được — người ngoài nhóm chấm cùng kết quả)_:

  | Chiều                        | Định nghĩa Pass                                                            | Cách chấm trên golden set                                  |
  | ---------------------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------- |
  | No hallucination             | Không nêu lịch/deadline không có trong DB/tool result                      | Keyword + không bịa sự kiện; case lớp ①                    |
  | Citation                     | Mọi câu trả lời tra cứu lịch có ≥1 `msg_id` hợp lệ khi đề bài yêu cầu cite | So khớp citation với expected trong `eval/golden_set.json` |
  | Clarification / out-of-scope | Hỏi lại khi mơ hồ; từ chối khi ngoài thẩm quyền                            | Keyword / hành vi mong muốn theo case lớp ②③               |
  | High-stakes accuracy         | Đúng thông tin lịch/deadline/ưu tiên khi có hậu quả thật                   | Keyword bắt buộc + citation theo case lớp ④                |

- **Golden set**: **26** case trong `eval/golden_set.json` (≥2/lớp chỗ khó + case thường + case hiếm; map 4 tiêu chí trong `eval/eval_results.md`).
- **Quality bar** _(chốt từ 23:59 ngày 1 — giữ nguyên)_:  
  **"Đạt khi ≥ 90% case qua bộ eval, và 100% trích dẫn đúng ID thông báo Discord gốc trên các case yêu cầu cite."**
- **Kết quả chạy** _(lượt 2026-07-31 20:00 — chi tiết `eval/eval_results.md`)_:

  | Chỉ số                            | Kết quả           | So với quality bar |
  | --------------------------------- | ----------------- | ------------------ |
  | Overall pass rate                 | **76.9%** (20/26) | Chưa đạt (≥90%)    |
  | Citation rate (case yêu cầu cite) | **60.0%** (9/15)  | Chưa đạt (100%)    |
  - **Nguyên nhân chính các case fail** (`TC_007, 008, 009, 010, 012, 022`): agent không gọi tool / không trả citation; một số case planning bị từ chối phạm vi quá chặt; `SCH_001` không map được ID lịch.
  - **Hướng xử lý**: siết prompt “bắt buộc tool trước khi trả lời lịch”; nới planning trong phạm vi đọc deadline chính thức; map mã lịch nội bộ ↔ `msg_id`.

## §8. Phân công & kế hoạch

- **Phân công có tên**:
  - **Nguyễn Mạnh Thắng** (`2A202601944`): Khảo sát Google Forms n=30, evidence §1–§2, System prompt.
  - **Hồ Trung Tín** (`2A202601688`): Kiến trúc agent, Discord bot, ReAct loop, mock UI, chỗ khó §5–§6, golden set + eval.
  - **Nguyễn Xuân Hùng** (`2A202601640`): SQLite DB, backfill/ingest, System prompt.
  - **Hoàng Minh Quân** (`2A202601574`): Tool.
- **Willing users (≥3)**: U1, U2, U3 (ẩn danh — không ghi tên) — test tại CP5 (`validation/user_test_log.md`).

## §9. Changelog

| Thời điểm  | Đổi gì                                                                                             | Vì sao                                                                |
| ---------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| 2026-07-30 | Khởi tạo Spec v1.0                                                                                 | Chốt đề tài theo khảo sát ban đầu                                     |
| 2026-07-31 | Siết §1–§2, §4, §5–§7 theo rubric R1–R4; đồng bộ golden set 26 + bảng kết quả vs quality bar       | Lát cắt 1 quyết định, cost-of-error, chiều chất lượng kiểm chứng được |
| 2026-07-31 | Siết hỏi lại khi câu mơ hồ; giữ bắt buộc citation/`msg_id`                                         | Feedback CP5 — U4 / U1 & U5 — `validation/user_test_log.md`           |
| 2026-07-31 | Giữ augment / từ chối dời lịch lớp                                                                 | Feedback CP5 — U3                                                     |
| 2026-07-31 | Cập nhật evidence R1: khảo sát **n=30**, **19/30 (63,3%)** mất >5 phút tìm lịch/deadline/thông báo | Số liệu Google Forms thật (câu hỏi + cách đếm kiểm lại được)          |
