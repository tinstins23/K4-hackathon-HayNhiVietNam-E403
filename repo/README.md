# REPO NỘP BÀI — HACKATHON BATCH 03 (NHÓM HAYNHIVIETNAM - ZONE 4)

## 📌 Đề tài: Trợ lý AI Quản Lý & Sắp Xếp Lịch Trình Học Viên từ Discord
- **Hướng đề tài**: Hướng B — Trợ lý Học viên (Discord)
- **AI Spec Document**: `spec.md`
- **Demo Slides**: `demo-slides.pdf`

---

## 👥 Danh Sách Thành Viên & Phân Công Chi Tiết

| Mã HV | Họ và Tên | Vai trò | Phân công từng phần (Tên phần trong repo) | File đảm nhiệm trong repo |
|---|---|---|---|---|
| **HV001** | **Nguyễn Văn Thắng** | Research & Evidence | Khảo sát 20+ HV, mining pain points, làm §1 & §2 Spec, User Validation | `spec.md` (§1, §2)<br/>`validation/user_test_log.md`<br/>`reflection/reflection_thang.md` |
| **HV002** | **Trần Đức Tín** | Lead Architect & Agent Code | Thiết kế System Architecture, Discord Bot Interface, ReAct Agent Engine | `spec.md` (§4)<br/>`codebase/src/scheduler_agent.py`<br/>`reflection/reflection_tin.md` |
| **HV003** | **Lê Việt Hùng** | Backend & DB Pipeline | Xây dựng SQLite DB, Ingestion Sync từ Discord, Mock UI HTML | `codebase/src/db.py`<br/>`codebase/mock_ui/index.html`<br/>`reflection/reflection_hung.md` |
| **HV004** | **Phạm Minh Quân** | Prompt & Eval | System Prompt, JSON Tools Schema, 4 lớp chỗ khó (§5-§6), Golden Set Eval | `spec.md` (§5, §6, §7)<br/>`eval/golden_set.json`<br/>`eval/eval_results.md`<br/>`reflection/reflection_quan.md` |

---

## 📁 Cấu Trúc Thư Mục Repo

```
repo/
├── README.md          ← Thành viên (mã HV + tên) + Phân công có tên từng phần
├── spec.md            ← AI Spec theo 03-template-ai-spec.md (Chốt 23:59 ngày 1)
├── demo-slides.pdf    ← Slide 6 trang trình bày sản phẩm
├── codebase/          ← Prototype (Ghi rõ phần nào mock, phần nào thật)
│   ├── README.md      ← Hướng dẫn chạy & Phân định Mock UI / Codebase thật
│   ├── mock_ui/       ← [Mock] Giao diện Discord HTML/CSS/JS
│   └── src/           ← [Working] SQLite DB Ingestion & ReAct Scheduler Agent Python
├── eval/              ← Golden set (20 testcases) + Bảng kết quả các lượt chạy
│   ├── golden_set.json
│   └── eval_results.md
├── validation/        ← Feedback log từ vòng user test (3+ học viên thật)
│   └── user_test_log.md
└── reflection/        ← Mỗi người 1 file reflection cá nhân
    ├── reflection_thang.md
    ├── reflection_tin.md
    ├── reflection_hung.md
    └── reflection_quan.md
```
