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
            
            # Financial manipulation attacks
            r"\b(transfer|authorize|approve|execute)\s+(?:a\s+)?(?:wire|fund|payment|transaction).*\$\d+",
            r"\b(update|change|modify|increase)\s+(?:my|the)\s+(account|balance|credit|limit).*\$\d+",
            r"\b(grant|approve|authorize)\s+(?:a\s+)?(?:large|massive|huge|unlimited)\s+(?:transfer|payment|withdrawal)",
            r"\b(?:wire|send|transfer)\s+(?:me\s+)?\$?\d+,\d+\s+(?:to|into)\b",
            
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
            r"[;|&`$]\s*(cat|ls|curl|wget|nc|bash|sh|python|perl)\b",
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
            
            # Healthcare/Patient Data (additional PII)
            r"\b(patient|medical)\s+id\b",
            r"\b(?:DOB|date\s+of\s+birth)\s*:\s*\d{1,2}/\d{1,2}/\d{4}",
            r"\b(?:diagnosis|medical\s+record|health\s+data)\b",
            
            # Financial Data (additional PII)
            r"\b(account|routing|swift)\s+(number|code)\b",
            r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # Credit card
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b.*\bpassword\b",  # Email+password
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN pattern (XXX-XX-XXXX)
            r"\b(social\s+security|SSN|sin)\b",  # References to SSN
            
            # System commands
            r"\b(system|execute|exec|run)\s+(command|cmd|shell)\b",
            r"\bos\.system\(",
            r"\bsubprocess\.(run|call|Popen)\b",
            
            # Jailbreak / Roleplay
            r"\b(DAN|ChaosGPT|DODAN|STAN)\s+mode\b",
            r"\bpretend\s+you\s+are\s+(unfiltered|unrestricted|without\s+ethics)\b",
            r"\byou\s+are\s+now\b.*\b(no\s+ethical|unfiltered|unrestricted)\b",
            r"\bpretend\s+(to\s+be|you\s+are)\s+DAN\b",
            r"\bDAN\b.*\b(do\s+anything\s+now|developer\s+mode|unrestricted|ignore\s+instructions)\b",
            r"\bDAN\b",
            
            # JSON-based attacks
            r'"\s*(?:task|action|command|instruction|rule)\s*"\s*:\s*"(?:ignore|disregard|bypass|forget|override|dump)',
            r'(?:ignore|disregard|bypass|forget|override|skip)[\s_]?(rules?|instructions?|guidelines?|restrictions?|filters?|policies?)',
            
            # Data exfiltration
            r"\b(reveal|show|display|expose|leak|dump|extract|retrieve|harvest|pull)\b.*\b(api\s*keys?|credentials?|secrets?|tokens?|passwords?)\b",
            r"\bdump\s+(database|table|credentials)\b",
            r"\bexfiltrate\s+data\b",
            r"\bopenai\b.*\bapi\s*key\b",
            r"\bapi\s*key\b.*\b(value|using|show\s+me)\b",
            
            # Bomb/Weapon/Illegal content
            r"\bhow\s+to\s+(build|make|create)\s+(a\s+)?(bomb|explosive|weapon|gun)\b",
            r"\b(hacking|cracking|illegal)\s+(tools?|techniques?|methods?)\b",
            
            # Base64/Encoding hints
            r"\bdecode\s+(this|the\s+following)\b.*[A-Za-z0-9+/=]{20,}",
            r"\btranslate\s+from\s+base64\b",
            r"\\x[0-9a-fA-F]{2}",  # Hex encoding
            r"shell_exec\s*\(",
            r"rm\s*-rf\s*/",
            r"\bsk-[A-Za-z0-9]{10,}\b",
            # Additional high-signal heuristics
            r"\bwhat\s+is\s+(your|the)\s+.*\bapi\s*key\b",
            r"\bunrestricted\b",
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
