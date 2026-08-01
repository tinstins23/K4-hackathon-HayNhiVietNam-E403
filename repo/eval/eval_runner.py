"""
eval_runner.py — Automated Evaluation Runner for Schedule AI Assistant

Reads test cases from repo/eval/golden_set.json, executes each against the agent,
evaluates keyword matches, citation requirements, tool traces, and generates
a structured evaluation summary report grouped by 4 critical quality criteria (Markdown & Console).
"""
import os
import sys
import json
from datetime import datetime

# Set UTF-8 encoding for Windows Console print
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add codebase/src directory to sys.path
CODEBASE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "codebase", "src"))
if CODEBASE_SRC not in sys.path:
    sys.path.insert(0, CODEBASE_SRC)

try:
    from dotenv import load_dotenv
    _eval_dir = os.path.dirname(os.path.abspath(__file__))
    _repo_dir = os.path.abspath(os.path.join(_eval_dir, ".."))
    load_dotenv(os.path.join(_repo_dir, "codebase", ".env"))
    load_dotenv(os.path.join(_repo_dir, ".env"))
    load_dotenv()
except ImportError:
    pass

import db
import agent

GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "golden_set.json")
EVAL_RESULTS_PATH = os.path.join(os.path.dirname(__file__), "eval_results.md")

CRITERIA_MAP = {
    "1_NO_DATA_HALLUCINATION_CHECK": "1. Chống Bịa Đặt Khi Không Có Dữ Liệu (No Hallucination)",
    "2_AMBIGUOUS_CLARIFICATION_CHECK": "2. Xử Lý Câu Hỏi Mơ Hồ & Thiếu Ngữ Cảnh (Ask Clarification)",
    "3_UNAUTHORIZED_OUT_OF_SCOPE_CHECK": "3. Từ Chối Yêu Cầu Trái Thẩm Quyền / Security Trap (Out of Scope)",
    "4_HIGH_STAKES_DEADLINE_RISK_CHECK": "4. Chính Xác Cao Với Câu Hỏi Gây Hậu Quả Thật (High Stakes Risk)"
}

def run_evaluation():
    # 1. Initialize DB
    db.init_db()

    # 2. Load Golden Set
    with open(GOLDEN_SET_PATH, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    total_cases = len(test_cases)
    print(f"=== BẮT ĐẦU CHẠY ĐÁNH GIÁ AUTOMATED EVALUATION ({total_cases} GOLDEN TEST CASES) ===")

    passed_cases = 0
    passed_citations = 0
    total_citation_required_cases = 0

    criteria_stats = {key: {"total": 0, "passed": 0} for key in CRITERIA_MAP}

    results = []

    for idx, tc in enumerate(test_cases, 1):
        tc_id = tc["id"]
        query = tc["query"]
        category = tc.get("category", "general")
        crit_type = tc.get("criteria_type", "4_HIGH_STAKES_DEADLINE_RISK_CHECK")
        ref_date = tc.get("reference_date", "2026-07-30T10:00:00")
        expected_contains = tc.get("expected_contains", [])
        requires_citation = tc.get("requires_citation", False)
        expected_citations = tc.get("expected_citations", [])

        if crit_type in criteria_stats:
            criteria_stats[crit_type]["total"] += 1

        print(f"\n[{idx}/{total_cases}] Testing {tc_id} ({category}): \"{query}\"...")

        failure_reasons = []
        exec_error = None

        # Execute Agent ReAct Engine with exception handling
        try:
            res = agent.ask(user_query=query, reference_date=ref_date, user_label="TestUser")
            reply = res.get("reply", "")
            citations = res.get("citations", [])
            tool_trace = res.get("tool_trace", [])
        except Exception as e:
            exec_error = str(e)
            res = {}
            reply = ""
            citations = []
            tool_trace = []
            failure_reasons.append(f"Lỗi ngoại lệ thực thi (Exception): {exec_error}")

        # 1. Keyword check
        contains_pass = True
        missing_keywords = []
        if not exec_error:
            for kw in expected_contains:
                if kw.lower() not in reply.lower():
                    contains_pass = False
                    missing_keywords.append(kw)

            if not contains_pass:
                failure_reasons.append(f"Thiếu từ khóa bắt buộc trong câu trả lời: {missing_keywords}")

        # 2. Citation check
        citation_pass = True
        actual_msg_ids = [c.get("msg_id") for c in citations]
        if requires_citation and not exec_error:
            total_citation_required_cases += 1
            if not citations:
                citation_pass = False
                failure_reasons.append("Yêu cầu trích dẫn nhưng AI không trả về citation nào")
            elif expected_citations:
                if not any(cid in actual_msg_ids for cid in expected_citations):
                    citation_pass = False
                    failure_reasons.append(f"Trích dẫn không đúng nguồn kỳ vọng (Kỳ vọng chứa 1 trong {expected_citations}, Thực tế: {actual_msg_ids})")

        if citation_pass and requires_citation and not exec_error:
            passed_citations += 1

        overall_pass = (not exec_error) and contains_pass and (citation_pass if requires_citation else True)
        if overall_pass:
            passed_cases += 1
            if crit_type in criteria_stats:
                criteria_stats[crit_type]["passed"] += 1
            print(f"  ✅ [PASS] Tools used: {len(tool_trace)} | Citations: {len(citations)}")
        else:
            print(f"  ❌ [FAIL] {tc_id}")
            for reason in failure_reasons:
                print(f"     └─ ⚠️  {reason}")
            if reply:
                reply_preview = reply.replace("\n", " ")[:150]
                print(f"     └─ 💬 AI Reply (preview): \"{reply_preview}...\"")

        results.append({
            "id": tc_id,
            "category": category,
            "criteria_type": crit_type,
            "query": query,
            "contains_pass": contains_pass,
            "citation_pass": citation_pass,
            "overall_pass": overall_pass,
            "tools_called": [t.get("tool") for t in tool_trace],
            "actual_citations": actual_msg_ids,
            "expected_citations": expected_citations,
            "missing_keywords": missing_keywords,
            "failure_reasons": failure_reasons,
            "reply": reply,
            "exec_error": exec_error
        })

    # Summary Calculations
    pass_rate = (passed_cases / total_cases) * 100 if total_cases > 0 else 0
    citation_rate = (passed_citations / total_citation_required_cases) * 100 if total_citation_required_cases > 0 else 100

    print("\n" + "=" * 60)
    print("BẢNG KẾT QUẢ ĐÁNH GIÁ (EVALUATION SUMMARY REPORT)")
    print(f"* Tổng số Testcases: {total_cases}")
    print(f"* Số case ĐẠT (Pass): {passed_cases}/{total_cases} ({pass_rate:.1f}%)")
    print(f"* Tỷ lệ Trích dẫn đúng (Citation Rate): {passed_citations}/{total_citation_required_cases} ({citation_rate:.1f}%)")
    print("-" * 60)
    print("KẾT QUẢ THEO 4 TIÊU CHÍ CHÍNH:")
    for key, name in CRITERIA_MAP.items():
        st = criteria_stats[key]
        rate = (st["passed"] / st["total"]) * 100 if st["total"] > 0 else 0
        print(f"  - {name}: {st['passed']}/{st['total']} ({rate:.1f}%)")
    print("=" * 60)

    # Write Markdown Report
    report_md = f"""# 📊 BẢNG KẾT QUẢ ĐÁNH GIÁ EVALUATION (GOLDEN SET REPORT)

- **Thời gian chạy**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
- **Tổng số Test cases**: `{total_cases}`
- **Tỷ lệ Đạt tổng thể (Overall Pass Rate)**: `{pass_rate:.1f}%` ({passed_cases}/{total_cases})
- **Tỷ lệ Trích dẫn Nguồn Sự Thật (Citation Accuracy Rate)**: `{citation_rate:.1f}%` ({passed_citations}/{total_citation_required_cases})

---

## 🎯 Bảng Đánh Giá Theo 4 Tiêu Chí Chất Lượng

| STT | Tiêu Chí Kiểm Thử | Số Case | Đạt (Pass) | Tỷ Lệ Đạt (%) | Đánh Giá Đáp Ứng |
|---|---|---|---|---|---|
"""
    for key, name in CRITERIA_MAP.items():
        st = criteria_stats[key]
        rate = (st["passed"] / st["total"]) * 100 if st["total"] > 0 else 0
        status_criteria = "✅ ĐẠT" if rate >= 80 else "⚠️ CẦN TỐI ƯU"
        report_md += f"| `{key[:1]}` | **{name}** | `{st['total']}` | `{st['passed']}` | **{rate:.1f}%** | {status_criteria} |\n"

    report_md += f"""
---

## 📌 Bảng Tổng Quan Kết Quả {total_cases} Testcases

| ID | Nhóm / Category | Tiêu Chí Kiểm Thử | Câu hỏi Testcase | Trích dẫn | Kết quả |
|---|---|---|---|---|---|
"""
    for r in results:
        status_icon = "✅ PASS" if r["overall_pass"] else "❌ FAIL"
        cit_status = "🔗 Có" if r["actual_citations"] else "Không"
        crit_short = CRITERIA_MAP.get(r["criteria_type"], r["criteria_type"])
        report_md += f"| `{r['id']}` | `{r['category']}` | {crit_short} | {r['query']} | {cit_status} | **{status_icon}** |\n"

    report_md += """
---

## 🔍 Log Lỗi Chi Tiết & Nguyên Nhân Thất Bại (Detailed Error Logs)

"""
    failed_results = [r for r in results if not r["overall_pass"]]
    if not failed_results:
        report_md += "🎉 **Tất cả test cases đều PASSED thành công! Không có log lỗi nào.**\n"
    else:
        for r in failed_results:
            reasons_str = "\n".join([f"  - ⚠️ {reason}" for reason in r["failure_reasons"]])
            reply_clean = r["reply"].replace("\n", " ") if r["reply"] else "(Không có phản hồi / Lỗi)"
            crit_name = CRITERIA_MAP.get(r["criteria_type"], r["criteria_type"])
            report_md += f"""### ❌ `{r['id']}` — {r['category']}
- **Tiêu chí kiểm thử**: `{crit_name}`
- **Câu hỏi**: `{r['query']}`
- **Nguyên nhân lỗi**:
{reasons_str}
- **Trích dẫn thực tế**: `{r['actual_citations']}` *(Kỳ vọng: `{r['expected_citations']}`)*
- **Tools đã gọi**: `{r['tools_called']}`
- **Phản hồi từ AI**:
  > {reply_clean}

---
"""

    report_md += f"""
## 🎯 Đánh Giá Theo Quality Bar (Rubric §7)
- **Quality Bar Chốt**: `≥85% Pass Rate` và `100% Citation Rate` cho các câu hỏi tra cứu lịch.
- **Trạng thái**: {"✅ **ĐẠT CHUẨN ĐÁNH GIÁ HACKATHON R4**" if pass_rate >= 85 and citation_rate >= 100 else "⚠️ **CẦN TỐI ƯU THÊM PROMPT / REACT AGENT**"}
"""

    with open(EVAL_RESULTS_PATH, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"\nĐã ghi kết quả đánh giá và log lỗi chi tiết vào file: {EVAL_RESULTS_PATH}")

if __name__ == "__main__":
    run_evaluation()
