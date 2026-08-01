# REFLECTION CÁ NHÂN — Nguyễn Mạnh Thắng (`2A202601944`)

**Vai trò**: Khảo sát Google Forms n=30, evidence §1–§2, System prompt.

## 1. Phần mình làm trong repo
- `spec.md` §1–§2 — Khảo sát pain point thực tế của học viên trên Google Forms (thu thập `n = 30` phản hồi hợp lệ), phân tích dữ liệu đếm số người mất >5 phút để làm minh chứng bằng chứng (evidence) và xây dựng bảng đánh giá Impact.
- `codebase/src/systemprompt.py` — Xây dựng và tinh chỉnh hệ thống System Prompt cho Agent: thiết lập persona Trợ lý lịch trình Discord, định nghĩa phạm vi thẩm quyền, quy tắc bắt buộc sử dụng tool tra cứu DB và luật chống hallucination (không bịa `msg_id` hay thông tin lịch).
- `validation/user_test_log.md` — Tham gia hỗ trợ thu thập feedback và ghi nhận log trải nghiệm của người dùng ở vòng validation.

## 2. AI hỗ trợ thế nào
- Dùng AI để hỗ trợ thiết kế bộ câu hỏi khảo sát tối ưu, gợi ý cấu trúc phân hóa câu hỏi theo thang đo thời gian để thu thập bằng chứng mang tính kiểm chứng cao.
- Dùng AI để phác thảo các khung System Prompt chống hallucination và ép output theo đúng format citation.
- Phần mình **tự chịu trách nhiệm giải thích**: Phương pháp luận khảo sát ($n=30$, tỷ lệ $19/30 = 63.3\%$ chọn >5 phút), logic phân cấp ưu tiên trong System Prompt, và lý do vì sao phải siết chặt quy tắc từ chối khi thông tin nằm ngoài phạm vi DB.

## 3. Bài học từ case fail của nhóm
- Trong lượt eval chính thức, nhóm đạt tỷ lệ pass **76.9%** (so với bar **≥90%**) và citation **60%** (so with bar **100%**).
- **Nguyên nhân liên quan đến System Prompt**: Một số test case (`TC_007–010, 012, 022`) bị fail do System Prompt lúc đầu siết điều kiện quá cứng hoặc chưa đủ lực để bắt agent bắt buộc kích hoạt tool trước khi trả lời. Ngoài ra, việc phân định phạm vi out-of-scope quá chặt khiến agent từ chối cả những câu hỏi hỏi về deadline chính thức.
- **Bài học rút ra**: Rút kinh nghiệm sâu sắc về Prompt Engineering trong ReAct Agent — prompt không chỉ cần định nghĩa persona mà quan trọng nhất là phải thiết lập **luồng kiểm soát hành vi tool-calling** chặt chẽ; điều chỉnh prompt giữa việc từ chối ngoài thẩm quyền và linh hoạt tra cứu đúng context là chìa khóa để nâng cao độ chính xác.

