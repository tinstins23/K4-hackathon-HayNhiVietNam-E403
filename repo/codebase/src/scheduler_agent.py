import json
from db import query_schedules

class ScheduleAgent:
    def __init__(self):
        self.system_prompt = "Bạn là Trợ lý AI Quản Lý & Sắp Xếp Lịch Trình cho Học viên từ thông báo Discord."
        
    def process_request(self, user_query, user_busy_slots=None):
        raw_events = query_schedules()
        return {
            "status": "SUCCESS",
            "message": f"Đã truy xuất {len(raw_events)} sự kiện từ DB.",
            "schedule": raw_events
        }

if __name__ == "__main__":
    agent = ScheduleAgent()
    print(agent.process_request("Xếp lịch tuần này"))
