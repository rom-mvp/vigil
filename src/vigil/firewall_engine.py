import re

class FirewallEngine:
    def __init__(self, config=None):
        """Initialize firewall with comprehensive attack patterns"""
        self.patterns = self._build_comprehensive_patterns()
    
    def _build_comprehensive_patterns(self):
        """Build comprehensive pattern list for all attack types"""
        pattern_strings = [
            # Indirect injection variants
            r"\b(ignore|disregard|bypass|forget|override|skip)\b.*\b(previous|prior|above|all|earlier)\b.*\b(instruction|rule|prompt|context|directive)",
            r"\bforget\s+everything\b",
            r"\breset\s+(your|the)\s+(memory|context|instructions)",
            
            # SQL Injection
            r"[';\"]+\s*(?:OR|AND)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+",
            r"\b(DROP|DELETE|TRUNCATE|ALTER|INSERT|UPDATE)\s+(TABLE|DATABASE|FROM|INTO)\b",
            r"';\s*DROP\s+TABLE",
            r"\bUNION\s+SELECT\b",
            r"--\s*$",  # SQL comment
            
            # XSS / Script injection
            r"<script[^>]*>.*?</script>",
            r"javascript:\s*",
            r"on(error|load|click|mouseover)\s*=",
            r"<iframe[^>]*>",
            r"eval\s*\(",
            r"document\.cookie",
            
            # Command Injection
            r"[;|&`$]\s*(cat|ls|rm|curl|wget|nc|bash|sh|python|perl)\b",
            r"\$\([^)]+\)",  # Command substitution
            r"`[^`]+`",  # Backtick execution
            r"&&|\|\|",  # Command chaining
            
            # Path Traversal
            r"\.\./",
            r"\.\.[/\\]",
            r"/etc/(passwd|shadow|hosts)",
            r"\bC:\\Windows\\System32",
            
            # Privilege Escalation
            r"\b(give|grant)\s+me\s+(admin|administrator|root|sudo|superuser)\b",
            r"\belevate\s+(my|user)\s+privilege",
            r"\bsudo\s+",
            r"\bsu\s+-",
            
            # PII patterns (additional to PIIEngine)
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
            r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # Credit card
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b.*\bpassword\b",  # Email+password
            
            # System commands
            r"\b(system|execute|exec|run)\s+(command|cmd|shell)\b",
            r"\bos\.system\(",
            r"\bsubprocess\.(run|call|Popen)\b",
            
            # Jailbreak / Roleplay
            r"\b(DAN|ChaosGPT|DODAN|STAN)\s+mode\b",
            r"\bpretend\s+you\s+are\s+(unfiltered|unrestricted|without\s+ethics)\b",
            r"\byou\s+are\s+now\b.*\b(no\s+ethical|unfiltered|unrestricted)\b",
            
            # Data exfiltration
            r"\b(reveal|show|display|expose|leak)\b.*\b(api[_\s]?key|secret|token|password|credential)\b",
            r"\bdump\s+(database|table|credentials)\b",
            r"\bexfiltrate\s+data\b",
            
            # Base64/Encoding hints (patterns that suggest encoding evasion)
            r"\bdecode\s+(this|the\s+following)\b.*[A-Za-z0-9+/=]{20,}",
            r"\btranslate\s+from\s+base64\b",
            r"\\x[0-9a-fA-F]{2}",  # Hex encoding
        ]
        
        compiled_patterns = []
        for pattern in pattern_strings:
            try:
                compiled_patterns.append(re.compile(pattern, re.IGNORECASE | re.DOTALL))
            except re.error as e:
                print(f"⚠️  Invalid regex pattern: {pattern} - {e}")
        
        return compiled_patterns
    def update_rules(self, patterns: list[str]):
        """Update firewall rules dynamically."""
        new_patterns = []
        for p in patterns:
            try:
                new_patterns.append(re.compile(p, re.IGNORECASE))
            except re.error:
                continue
        self.patterns = new_patterns

    def scan_input(self, text):
        if not text: return {"safe": True}
        for p in self.patterns:
            if p.search(text):
                return {"safe": False, "reason": "HEURISTIC_BLOCK"}
        return {"safe": True}
