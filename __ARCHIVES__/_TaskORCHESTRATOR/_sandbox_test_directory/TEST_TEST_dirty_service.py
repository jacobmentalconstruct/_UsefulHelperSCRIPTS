# Legacy Microservice - Hard to parse with regex
import sys, os
from datetime import datetime

def helper_tool(data):
    return f"PROCESSED: {data}"

class LegacyDataService:
    def __init__(self, config=None):
        self.cfg = config
        self.started = datetime.now()

    def get_user_data(self, user_id):
        # This logic needs to be moved to @service_endpoint
        print(f"Fetching {user_id}")
        return {"id": user_id, "status": "active"}

    def update_record(self, record):
        # Messy inline logic
        if not record: return False
        return helper_tool(record)
