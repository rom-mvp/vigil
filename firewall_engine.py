import re
class FirewallEngine:
    def __init__(self, config=None):
        self.patterns = [
            re.compile(r"ignore previous instructions", re.IGNORECASE),
            re.compile(r"drop table", re.IGNORECASE),
            re.compile(r"delete database", re.IGNORECASE),
            re.compile(r"system prompt", re.IGNORECASE)
        ]
    def scan_input(self, text):
        if not text: return {"safe": True}
        for p in self.patterns:
            if p.search(text):
                return {"safe": False, "reason": "HEURISTIC_BLOCK"}
        return {"safe": True}
