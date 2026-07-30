# AI SPEC — Trợ lý AI Sắp Xếp Lịch Trình Discord · Nhóm HayNhiVietNam · Zone 4
Hướng: [ ] A — VLearn  [x] B — Trợ lý Học viên  [ ] C — Làn mở
Loại: [ ] Tối ưu tính năng có sẵn  [x] Tính năng mới

## §1. User & Job
- **Job executor + workflow**: Học viên khóa AI Thực Chiến cần theo dõi, tìm kiếm và tự lên lịch trình tuần/tháng từ hàng loạt thông báo trên Discord (`#thong-bao`, `#lich-hoc`, `#mentoring`...).
- **Core JTBD**: Khi có thông báo lịch học và bài tập dày đặc trên Discord, tôi muốn tra cứu và tự động lập thời khóa biểu cá nhân hóa không trùng lịch bận, để tôi quản lý thời gian hiệu quả mà không bỏ lỡ hạn nộp hay buổi học quan trọng.
- **Problem statement**: Học viên gặp khó khăn trong việc tổng hợp và sắp xếp lịch trình cá nhân do số lượng thông báo quá lớn, liên tục thay đổi trên Discord, gây mất thời gian tra cứu thủ công và phải liên tục hỏi lại Giảng viên / Coach.
- **Evidence**:
  - **Số liệu khảo sát (Thắng thực hiện)**: Khảo sát `n = 20` học viên trong khóa, **>60%** (13/20 học viên) xác nhận gặp khó khăn lớn khi tìm kiếm và sắp xếp lịch do thông báo dày và đổi liên tục.
  - **Ví dụ quote nguyên văn**:
    1. *"Lịch thông báo trên Discord trôi nhanh quá, sáng báo một đằng chiều dời lịch là mình bỏ lỡ ngay."*
    2. *"Mỗi tuần phải ngồi nhặt từng tin nhắn ở #thong-bao rồi tự chép ra Google Calendar mất 30-45 phút."*
    3. *"Nhiều lúc không biết chiều nay có lịch coaching không, toàn phải tag Coach hỏi lại làm phiền Coach."*
    4. *"Lịch cá nhân bận đột xuất muốn xếp lại lịch làm bài tập mà không biết kẹp vào slot nào."*
    5. *"Thông báo dời deadline nằm rải rác trong thread làm mình nộp bài muộn."*

## §2. Impact & quyết định chọn
- **Bảng impact 3 ứng viên**:
  | Ứng viên tính năng | Đối tượng & Tần suất | Tốn gì mỗi lần | Khả thi | Chọn/Loại |
  |---|---|---|---|---|
  | **1. AI Tự động Ingest & Sắp xếp Lịch trình cá nhân hóa** | 1000 học viên · 3-5 lần/tuần | 30-45 phút tra cứu, đối soát lịch bận, rủi ro bỏ lỡ | Cao (Agent + Function Calling Tool Query DB) | **CHỌN** |
  | 2. AI Tóm tắt bản tin Discord cuối ngày cho TA | 10-15 TA · 1 lần/ngày | 15 phút đọc lại log | Trung bình | LOẠI (Impact nhỏ hơn, ít người dùng hơn) |
  | 3. AI Tự động nhắc nhở từng cá nhân sát giờ học | 1000 học viên · 1-2 lần/ngày | 2-3 phút đọc ping | Trung bình | LOẠI (Có thể gây phiền/spam nếu nhắc quá nhiều) |

- **Lý do chọn tính năng 1**: Giải quyết trực tiếp pain point của >60% học viên (đã kiểm chứng qua khảo sát của Thắng), mang lại ROI thời gian tiết kiệm rõ rệt.

## §3. Giải pháp tương tự đã nghiên cứu
- **Google Calendar / Notion AI**: Đắt đỏ, không tích hợp trực tiếp vào Discord khoá, không tự đọc được context tin nhắn thông báo Discord để trích xuất metadata (Deadlines, Voice room, Coach).
- **Discord Event Bot thông thường**: Chỉ tạo event tĩnh, không biết giải quyết xung đột lịch bận cá nhân của từng học viên, không có khả năng đàm thoại / ReAct loop để tối ưu lịch.

## §4. Thiết kế
- **Lát cắt MỘT CÂU**: *Một học viên nhắn tin/yêu cầu trên Discord, AI tự động truy xuất DB lịch trình (đã sync từ thông báo) và lặp ReAct logic để sắp xếp/phản hồi thời khóa biểu tối ưu hoặc thông báo nếu không có lịch.*
- **Non-goals**:
  - Không tự động gửi request xin dời lịch chung của cả lớp lên Ban tổ chức.
  - Không đồng bộ 2 chiều với Google Calendar external OAuth (chỉ xuất ra markdown / format bàn giao cho user).
  - Không can thiệp vào phân quyền quản trị kênh Discord.
- **Mức prototype nhắm tới**: [x] Working
  - *Phần mock*: Giả lập dữ liệu một số tin nhắn bận cá nhân phức tạp.
  - *Phần thật*: Discord Bot nhận query thật -> Ingestion Parser thật -> SQLite DB Query -> ReAct Agent lặp thật qua LLM Function Calling.
- **Automation**: [x] augment - Hỗ trợ học viên lập lịch và đề xuất, học viên là người chốt cuối cùng.
- **§4b. Nguyên tắc đã áp dụng**:
  | Nguyên tắc | Áp cụ thể vào đâu trong prototype |
  |---|---|
  | HAX G1 (Clarify what system can do) | Gợi ý rõ các lệnh học viên có thể hỏi (`/schedule`, `@AI xếp lịch tuần này...`) |
  | HAX G4 (Show relevant information) | Luôn đính kèm link / Discord Message ID gốc khi trả lời về lịch học |
  | HAX G11 (Make clear why system did what it did) | Giải thích lý do chọn slot làm bài tập (VD: *"Xếp vào T4 19h vì sáng T4 bạn đã bận"*)|
  | PAIR (Graceful Fallback) | Trả về lý do rõ ràng khi khoảng thời gian không có lịch hoặc trùng 100% |

## §5. Kiểu lỗi — 4 lớp chỗ khó + kịch bản (≥8)
1. **① Nguồn sự thật**: AI bịa ra lịch học không có thật -> Chốt nguồn dữ liệu cứng trong SQL DB, trả về kèm Message ID.
2. **① Nguồn sự thật**: Thông báo hủy buổi học bị bỏ sót -> Update trạng thái `canceled` trong DB ngay khi sync.
3. **② Mơ hồ**: User hỏi *"Chiều nay rảnh không?"* -> Hỏi lại: *"Bạn đang muốn kiểm tra lịch học bắt buộc hay xếp thời gian làm bài tập?"*
4. **② Mơ hồ**: User không nhập lịch bận cá nhân -> Đề xuất lịch học chính và nhắc user bổ sung lịch bận nếu muốn cá nhân hóa.
5. **③ Ngoài phạm vi**: User yêu cầu *"Dời buổi học sang tuần sau giúp cả lớp"* -> Từ chối và trỏ link liên hệ Admin.
6. **③ Ngoài phạm vi**: User hỏi đề thi / đáp án bài tập -> Phản hồi ngoài phạm vi quản lý lịch trình.
7. **④ Đặc thù Domain**: Lịch đổi đột xuất đè lên lịch cũ -> Ưu tiên record mới nhất theo timestamp `updated_at`.
8. **④ Đặc thù Domain**: Trùng giữa lịch học bắt buộc và lịch cá nhân -> Cảnh báo đỏ (Critical Warning) và ưu tiên lịch học bắt buộc.

## §6. Bốn đường đi của trải nghiệm
- **Happy path**: User nhắn *"Xếp lịch tuần này"* -> AI query DB -> Tìm thấy slot phù hợp -> Xuất Bảng Thời khóa biểu đẹp + Link Discord gốc.
- **Low-confidence (②)**: User nhập thiếu thông tin -> AI hỏi lại để làm rõ scope.
- **Failure/không căn cứ (①)**: Không có lịch nào trong khoảng thời gian user hỏi -> Phản hồi *"Không tìm thấy thông báo lịch học trong khoảng thời gian này"*.
- **Correction (user sửa)**: User phàn nàn *"T5 mình bận rồi"* -> AI nhận phản hồi, loại trừ T5 và Re-run agentic loop để xếp lại.
- **Khi bị đòi ngoài phạm vi (③)**: User đòi dời lịch lớp -> AI giải thích giới hạn thẩm quyền và hướng dẫn quy trình xin nghỉ chính thức.
- **Case đặc thù domain (④)**: Lịch thông báo bị thay đổi đột xuất -> AI thông báo rõ: *"Lịch T3 đã được Coach dời sang T5 theo thông báo mới nhất lúc 10h sáng nay"*.

## §7. Kiểm thử
- **Chiều chất lượng**:
  - Precision của thông tin lịch: 100% (không hallucinate).
  - Tỷ lệ đính kèm trích dẫn (Source Citation): 100%.
  - Tỷ lệ giải quyết trùng lịch (Conflict Resolution Rate): ≥90%.
- **Golden set**: 20 testcases nằm trong `eval/golden_set.json`.
- **Quality bar**: "Đạt khi ≥ 90% case qua bộ eval, 100% trích dẫn đúng ID thông báo Discord gốc."

## §8. Phân công & kế hoạch
- **Phân công có tên**:
  - **Thắng**: Khảo sát (Survey 20+ HV, mining pain points, thu thập evidence, làm §1-§2 Spec).
  - **Tín + Hùng**: Tìm đề tài + Build Engine (Xây dựng Discord Bot, Ingestion Pipeline, SQLite DB, ReAct Agent Loop, architecture.md).
  - **Quân**: Prompt Engineering (Soạn System Prompt, Tool Schema Function Calling, 4 lớp chỗ khó §5, Golden Set Eval).
- **Willing users (≥3 tên)**: Nguyễn Văn A, Trần Thị B, Lê Văn C (sẵn sàng test prototype tại CP5).

## §9. Changelog
| Thời điểm | Đổi gì | Vì sao |
|---|---|---|
| 2026-07-30 | Khởi tạo Spec v1.0 | Chốt đề tài theo kết quả khảo sát n=20 |
