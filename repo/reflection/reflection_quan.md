# REFLECTION CÁ NHÂN — Hoàng Minh Quân (`2A202601574`)
Vai trò: Thiết kế và phát triển Tool Layer, xây dựng các hàm thao tác với SQLite Database, hỗ trợ Function Calling cho ReAct Scheduler Agent.

1. Phần mình làm trong repo
repo/codebase/src/tools.py — xây dựng các tool thao tác với SQLite Database để Agent có thể truy xuất và cập nhật dữ liệu lịch trình.
Xây dựng Function Calling Layer, ánh xạ tên tool với hàm thực thi thông qua AVAILABLE_TOOLS.
Thiết kế các hàm thao tác dữ liệu:
get_schedules_from_db() — truy vấn danh sách lịch trình chính thức từ cơ sở dữ liệu, hỗ trợ lọc theo category.
add_schedule_to_db() — thêm mới hoặc cập nhật lịch trình vào bảng official_schedules, phục vụ quá trình ingestion và đồng bộ dữ liệu.
Chuẩn hóa dữ liệu đầu ra của tool dưới dạng dict để Agent dễ dàng xử lý và sinh câu trả lời.
Hỗ trợ tích hợp Tool Layer với agent.py để Agent có thể gọi tool thay vì trả lời trực tiếp từ mô hình ngôn ngữ.
2. AI hỗ trợ thế nào
Sử dụng AI để tham khảo cách thiết kế Function Calling và chuẩn hóa giao diện giữa Agent và Database.
AI hỗ trợ gợi ý cách tối ưu truy vấn SQLite, chuẩn hóa dữ liệu trả về và cấu trúc AVAILABLE_TOOLS.
Phần mình tự chịu trách nhiệm gồm:
Thiết kế các hàm thao tác với SQLite.
Xây dựng logic thêm/cập nhật và truy vấn lịch trình.
Kiểm tra dữ liệu trả về để đảm bảo Agent luôn nhận được thông tin đúng định dạng trước khi suy luận.
3. Bài học từ quá trình phát triển
Tool Layer là thành phần quyết định chất lượng của Agent. Nếu Tool trả về dữ liệu không đầy đủ hoặc sai định dạng, Agent rất dễ sinh câu trả lời sai hoặc bị hallucination.
Việc tách riêng phần truy cập Database thành tools.py giúp mã nguồn dễ mở rộng và bảo trì hơn, đồng thời giảm sự phụ thuộc giữa Agent và tầng dữ liệu.
Trong quá trình tích hợp với ReAct Agent, mình nhận thấy việc chuẩn hóa dữ liệu đầu ra (JSON/dictionary) giúp Agent gọi nhiều tool liên tiếp dễ dàng hơn và giảm lỗi khi sinh phản hồi.
Việc quản lý các tool thông qua AVAILABLE_TOOLS giúp Agent chỉ được phép gọi những chức năng đã định nghĩa, tăng tính an toàn và khả năng mở rộng khi bổ sung thêm các tool mới như tìm khoảng thời gian rảnh, kiểm tra trùng lịch hoặc đề xuất kế hoạch học tập.