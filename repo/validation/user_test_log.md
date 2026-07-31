# Feedback Log — User Test CP5 (Validation)

> **Mốc**: CP5 · Xác minh + validation + dry run  
> **Người thực hiện / ghi log**: Nguyễn Mạnh Thắng (`2A202601944`)  
> **Sản phẩm thử**: Trợ lý AI lịch trình Discord (Bot thật + Mock UI)  
> **Thời điểm**: 2026-07-31  
> **Đối tượng**: **5 học viên ngoài nhóm** (gồm **3 willing users** đã khai từ CP1)  
> **Ghi chú**: Người thử được **ẩn danh** (mã U1–U5), không ghi tên thật.

---

## 1. Cách chạy phiên test (10 phút / người)

1. Giao task thật — **không thuyết minh, không gợi ý** trong lúc họ dùng.  
2. Quan sát: họ gõ gì, kẹt đâu, có mở citation/link gốc không.  
3. Hỏi đúng 3 câu:
   - *"Điều gì khó hiểu hoặc khó chịu nhất?"*
   - *"Kết quả này bạn có tin không — vì sao?"*
   - *"Bạn có dùng thật không — vì sao / vì sao chưa?"*
4. Ghi **quote nguyên văn** + mức nghiêm trọng.

**Task giao cho từng người** (xen kẽ happy path / chỗ khó):

| Mã task | Nội dung |
|---|---|
| T1 | Hỏi deadline Spec.md / lịch tuần này trên Bot hoặc Mock UI |
| T2 | Hỏi câu mơ hồ: *"Nay có lịch gì không"* — xem AI có hỏi lại không |
| T3 | Thử yêu cầu ngoài phạm vi: dời lịch cả lớp / đòi đáp án |
| T4 | Hỏi lịch đã hủy / đã sửa — kiểm tra có cite thông báo gốc không |

---

## 2. Bảng feedback ≥5 người (R6)

| # | Người thử (mã / vai) | Willing CP1? | Task | Quan sát | Quote nguyên văn | Mức |
|---|---|---|---|---|---|---|
| 1 | **U1** — HV khóa AI Thực Chiến | Có | T1 | Hỏi deadline, mở được citation | *"AI trả lời nhanh, có đính kèm link Discord bài gốc nên mình kiểm tra lại rất dễ."* | Thấp (khen + dùng được) |
| 2 | **U2** — HV khóa AI Thực Chiến | Có | T1 + xếp slot làm bài | Muốn né lịch bận cá nhân; Bot đề xuất được nhưng phải tự nhắc bận | *"Thích nhất là AI tự biết né buổi tối T4 mình đi làm thêm để xếp slot chép spec T5 — nhưng lúc đầu mình không biết phải nói lịch bận thế nào."* | Trung bình |
| 3 | **U3** — HV khóa AI Thực Chiến | Có | T3 | Thử đòi dời lịch lớp | *"AI từ chối và hướng dẫn báo Admin khá lịch sự. Mình tin hơn vì nó không tự ý hứa dời lịch."* | Thấp (đúng hành vi) |
| 4 | **U4** — HV zone khác (đổi chéo) | Không | T2 | Câu *"Nay có lịch gì"* — lúc đầu trả dài, hơi loạn | *"Khó chịu nhất là câu hỏi chung chung mà bot trả một đống lịch, mình phải đọc lại. Nên hỏi lại mình đang cần deadline hay lịch học."* | Cao |
| 5 | **U5** — HV zone khác (đổi chéo) | Không | T4 | Kiểm tra buổi hủy / sửa + citation | *"Mình có tin khi có msg_id / link tin gốc. Không có link thì mình vẫn vào #thong-bao tự lục — lúc đó gần như không hơn cách cũ."* | Cao |

**Đủ rubric R6**: 5 mẩu · 5 người ngoài nhóm · ≥2 willing (thực tế 3) · có mã ẩn danh + vai.

---

## 3. Tổng hợp 4 dòng (theo guide §4.2)

| Mục | Nội dung |
|---|---|
| **Chủ đề lặp nhiều nhất** | (1) Cần **citation / link tin gốc** mới tin; (2) Câu hỏi **mơ hồ** dễ bị trả lời “một đống”; (3) Chưa rõ cách **khai báo lịch bận** cá nhân. |
| **1–2 thay đổi làm trước demo** | Siết prompt: câu mơ hồ → **hỏi lại 1 câu** trước khi liệt kê; luôn kèm **citation `msg_id`** khi trả lời lịch. Ghi vào Changelog `spec.md` §9. |
| **Giữ nguyên có lý do** | Giữ **augment** (không automate dời lịch / nhắc spam): U3 tin hơn khi bot từ chối đúng thẩm quyền — khớp cost-of-error trong spec §4. |
| **Backlog (slide 6 — nếu thêm 1 tuần)** | UX khai báo lịch bận 1 lệnh rõ; map mã lịch nội bộ (`SCH_xxx`); cải thiện case planning trùng lịch (eval đang fail một phần high-stakes). |

---

## 4. Ba câu hỏi — ghi chú theo người (rút gọn)

### U1 (willing)
- Khó chịu nhất: gần như không — muốn thêm lọc theo ngày.  
- Có tin không: **Có** — vì có link Discord gốc.  
- Dùng thật không: **Có** — thay lục `#thong-bao`.

### U2 (willing)
- Khó chịu nhất: *"không biết phải nói lịch bận thế nào."*  
- Có tin không: **Có** khi đề xuất có giải thích ràng buộc.  
- Dùng thật không: **Có**, nếu nhớ được cách nhập lịch bận.

### U3 (willing)
- Khó chịu nhất: không — kỳ vọng bot “xin nghỉ giúp” nhưng chấp nhận từ chối.  
- Có tin không: **Có** vì không hứa quá quyền.  
- Dùng thật không: **Có** cho tra cứu lịch; không dùng để xin dời lịch lớp.

### U4
- Khó chịu nhất: trả lời quá dài với câu mơ hồ.  
- Có tin không: **Một phần** — thiếu hỏi lại thì dễ bỏ sót ý.  
- Dùng thật không: **Chưa chắc** nếu còn trả lời “một đống”.

### U5
- Khó chịu nhất: thiếu link / citation thì mất giá trị.  
- Có tin không: **Chỉ khi có nguồn**.  
- Dùng thật không: **Có**, với điều kiện luôn cite thông báo chính thức.

---

## 5. Changelog từ feedback → sản phẩm (R6 — 4 điểm)

| Thời điểm | Đổi gì | Vì feedback / căn cứ nào |
|---|---|---|
| 2026-07-31 | Siết hỏi lại khi câu mơ hồ (lớp ②) trong system prompt / agent | Quote U4: trả lời “một đống” với *"Nay có lịch gì"* |
| 2026-07-31 | Giữ bắt buộc citation `msg_id` + jump link trên Bot | Quote U1 + U5: chỉ tin khi có link tin gốc |
| 2026-07-31 | **Giữ** augment / từ chối dời lịch lớp | Quote U3: tin hơn vì bot không tự ý hứa dời lịch |

Chi tiết cũng ghi ở `spec.md` §9.
