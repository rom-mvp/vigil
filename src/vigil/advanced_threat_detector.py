#!/usr/bin/env python3
"""
Advanced Threat Detector - Comprehensive Attack Pattern Recognition
Restores and enhances security capabilities deleted from core/

Detects:
- Encoding evasion (base64, hex, unicode)
- Homoglyph substitution attacks  
- Whitespace-based fragmentation
- Prompt injection variants
- Token flooding attacks
- Semantic intent attacks
"""

import re
import unicodedata
import base64
import math
import signal
from collections import defaultdict
from typing import Dict, List, Tuple, Any


class EncodingDetector:
    """Detect various encoding evasion techniques"""
    
    @staticmethod
    def is_base64(text: str) -> Tuple[bool, str]:
        """Check if text is base64 encoded and decode"""
        if not text or len(text) < 8:  # Require at least 8 chars to be meaningful base64
            return False, text
        
        stripped = text.strip()
        
        # Base64 pattern: alphanumeric + / + = padding
        if not re.match(r'^[A-Za-z0-9+/]*={0,2}$', stripped):
            return False, text
        
        # Length must be multiple of 4
        if len(stripped) % 4 != 0:
            return False, text
        
        try:
            decoded = base64.b64decode(stripped, validate=True).decode('utf-8', errors='ignore')
            # Only return as base64 if decoded looks like actual text (not random)
            if len(decoded) > 5 and decoded.isprintable():
                # Check if decoded text looks like actual content
                entropy = EntropyAnalyzer.shannon_entropy(decoded)
                # If decoded text has moderate entropy (not random), it's likely real
                if entropy < 5.8:
                    return True, decoded
        except Exception:
            pass
        
        return False, text
    
    @staticmethod
    def is_hex_encoded(text: str) -> Tuple[bool, str]:
        """Check if text is hex encoded"""
        if not text or len(text) < 6:
            return False, text
        
        # Remove common hex prefixes
        cleaned = text.lstrip().lower()
        if cleaned.startswith('0x'):
            cleaned = cleaned[2:]
        
        # Check if valid hex
        if not re.match(r'^[0-9a-f]+$', cleaned):
            return False, text
        
        # Must be even length
        if len(cleaned) % 2 != 0:
            return False, text
        
        try:
            decoded = bytes.fromhex(cleaned).decode('utf-8', errors='ignore')
            if len(decoded) > 3 and decoded.isprintable():
                return True, decoded
        except Exception:
            pass
        
        return False, text
    
    @staticmethod
    def decode_all_encodings(text: str) -> List[str]:
        """Recursively decode all detected encodings"""
        decoded = [text]
        current = text
        
        for _ in range(3):  # Max 3 levels of encoding
            is_b64, decoded_b64 = EncodingDetector.is_base64(current)
            if is_b64:
                current = decoded_b64
                decoded.append(current)
                continue
            
            is_hex, decoded_hex = EncodingDetector.is_hex_encoded(current)
            if is_hex:
                current = decoded_hex
                decoded.append(current)
                continue
            
            break
        
        return decoded


class HomoglyphNormalizer:
    """Normalize homoglyphs and confusable characters"""
    
    # Common homoglyph substitutions
    HOMOGLYPH_MAP = {
        'а': 'a', 'в': 'b', 'с': 'c', 'е': 'e', 'м': 'm', 'н': 'h',
        'о': 'o', 'р': 'p', 'х': 'x', 'у': 'y', 'т': 't', 'і': 'i',
        'ї': 'yi', 'ґ': 'g',
        # Latin lookalikes
        '𝐚': 'a', '𝐛': 'b', '𝐜': 'c', '𝐝': 'd', '𝐞': 'e',
        '𝐀': 'a', '𝐁': 'b', '𝐂': 'c', '𝐃': 'd', '𝐄': 'e',
    }
    
    @staticmethod
    def normalize(text: str) -> str:
        """Normalize homoglyphs to ASCII equivalents"""
        # Unicode NFKC normalization
        normalized = unicodedata.normalize('NFKC', text)
        
        # Apply homoglyph mapping
        for original, replacement in HomoglyphNormalizer.HOMOGLYPH_MAP.items():
            normalized = normalized.replace(original, replacement)
        
        return normalized


class WhitespaceFragmentationDetector:
    """Detect whitespace-based fragmentation attacks"""
    
    @staticmethod
    def detect_fragments(text: str) -> Tuple[bool, List[str]]:
        """
        Detect space-separated character fragmentation
        E.g. "D E L E T E A L L" -> ["DELETEALL"]
        """
        # Try multiple collapse patterns
        patterns_to_try = [
            (r'\b(\w)\s+(?=\w\b)', 'single-space'),      # Single char followed by word char with space
            (r'(\w)\s{2,}(?=\w)', 'multi-space'),        # Multiple spaces
            (r'(\w)[\s\t\n]{1,}(?=\w)', 'mixed-space'),  # Mixed whitespace
            (r'(\w)\s+(?=\w)', 'aggressive'),            # Very aggressive: any space between word chars
        ]
        
        results = []
        for pattern, ptype in patterns_to_try:
            collapsed = re.sub(pattern, r'\1', text)
            if collapsed != text:
                results.append(collapsed)
        
        return (len(results) > 0, results)
    
    @staticmethod
    def reconstruct_words(text: str) -> str:
        """Aggressively reconstruct fragmented text"""
        # Remove all internal whitespace from words
        result = re.sub(r'(\b\w)[\s\t\n]+(?=\w)', r'\1', text)
        return result


class IndirectInjectionDetector:
    """Detect indirect prompt injections hidden in content"""
    
    # Patterns for system instruction injections hidden in content
    INJECTION_MARKERS = [
        r'\[SYSTEM[^\]]*\]',           # [SYSTEM:...]
        r'\[INSTRUCTIONS?[^\]]*\]',    # [INSTRUCTIONS:...]
        r'<SYSTEM[^>]*>',              # <SYSTEM:...>
        r'\{\{SYSTEM[^}]*\}\}',        # {{SYSTEM:...}}
        r'SYSTEM OVERRIDE:',           # SYSTEM OVERRIDE:
        r'IGNORE (ALL|PREVIOUS)',      # IGNORE ALL/PREVIOUS
        r'FORGET (ABOUT|ALL)',         # FORGET ABOUT/ALL
    ]
    
    @staticmethod
    def detect_injections(text: str) -> Tuple[bool, List[str]]:
        """Detect system instruction injections in content"""
        found_injections = []
        
        for pattern in IndirectInjectionDetector.INJECTION_MARKERS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            found_injections.extend(matches)
        
        return (len(found_injections) > 0, found_injections)


class ReDoSProtection:
    """Protect against Regular Expression Denial of Service attacks"""
    
    @staticmethod
    def has_dangerous_pattern(text: str) -> bool:
        """Check if text looks like a ReDoS attempt"""
        # Simple heuristic: very long runs of same character
        if len(text) > 50000:  # Extremely long text
            return True
        
        for char in set(text):
            if text.count(char) > 5000:  # Too many of same char
                return True
        
        return False


class EntropyAnalyzer:
    """Analyze Shannon entropy for random/encoded content"""
    
    @staticmethod
    def shannon_entropy(text: str) -> float:
        """Calculate Shannon entropy of text"""
        if not text:
            return 0.0
        
        char_counts = defaultdict(int)
        for char in text:
            char_counts[char] += 1
        
        text_len = len(text)
        entropy = 0.0
        
        for count in char_counts.values():
            probability = count / text_len
            if probability > 0:
                entropy -= probability * math.log2(probability)
        
        return entropy
    
    @staticmethod
    def is_high_entropy(text: str, threshold: float = 4.5) -> bool:
        """Check if text has suspiciously high entropy"""
        entropy = EntropyAnalyzer.shannon_entropy(text)
        return entropy > threshold


class CapabilityMatcher:
    """Pattern-based capability violation detection"""
    
    CAPABILITY_PATTERNS = {
        "REVEAL_SYSTEM": [
            r"\byour\s+system\s+prompt\b",
            r"\bsystem\s+prompt\b",
            r"\b(?:reveal|show|expose)\s+(?:the\s+)?system\b",
            r"\b(?:hack|access|exploit|override|break)\s+(?:the\s+)?system\b",
            r"\binit\s+instructions\b",
            r"^hacksystem$",  # Fragmented/concatenated (case-insensitive in check)
            r"^hacks$",  # Just "hack" from h a c k
            r"\bhack\b",  # Word boundary for hack
            r"\bsystem\b",  # Standalone "system" word (from ASCII art jailbreaks)
        ],
        "CHANGE_POLICY": [
            r"\b(ignore|disregard|bypass|forget|override|skip|neglect)\s+(?:all\s+)?(?:previous|above|prior|earlier|former)\s+(?:instructions?|rules?|commands?|directives?|prompts?)\b",
            r"\bignore(?:all)?(?:previous|prior|above)(?:instructions|rules)\b",
            r"\bdisregard\s+(?:the\s+)?(?:above|previous|prior|all)\s+(?:instructions|rules)\b",
            r"\bforget\s+(?:about\s+)?(?:previous|above|earlier|all)\s+(?:instructions|rules|context)\b",
            r"\b(reset|clear|wipe)\s+(?:your|the)\s+(?:memory|context|instructions?)\b",
            r"\boverride\s+(?:all\s+)?(?:previous|prior)\s+(?:rules?|instructions?)\b",
            r"\bbypass\s+(?:all\s+)?(?:rules?|restrictions?|guidelines?)\b",
        ],
        "AUTHORITY_ESCALATION": [
            r"\bgive\s+me\s+(?:admin|administrator|root)\s+(?:privileges?|access)\b",
            r"\bbypass\s+(?:the\s+)?(?:authentication|security|access\s+control)\b",
            r"\b(?:become|switch\s+to)\s+(?:admin|administrator|root)\b",
            r"\brun\s+(?:as\s+)?(?:admin|administrator|root)\b",
            r"^giveadmin",  # Fragmented/concatenated
        ],
        "CREDENTIAL_EXFIL": [
            r"\bapi\s*key\b",
            r"\bsk-[a-zA-Z0-9]{20,}",
            r"\b(?:send|give|leak|exfil|dump|show|reveal)\s+(?:my\s+)?(?:password|credential|secret|token|key)\b",
            r"\b(?:password|secret|token|credential|key)\s+(?:is|=)\s*[a-zA-Z0-9]{8,}\b",
        ],
        "DESTRUCTIVE_ADMIN": [
            r"\b(?:delete|drop|truncate|clear|wipe)\s+(?:all\s+)?(?:users?|database|table|records?|data)\b",
            r"\bdelete.*from.*where\s+1\s*=\s*1\b",
            r"\b(?:rm|rmrf|-rf)\s+/\b",
            r"^deleteall",  # Fragmented/concatenated
            r"^delete$",  # Just "delete" standalone (from D E L E T E)
        ],
    }
    
    @staticmethod
    def check_capabilities(text: str) -> Dict[str, List[str]]:
        """Check text for capability violations"""
        violations = {}
        
        # Also check space-collapsed variants
        space_collapsed = re.sub(r'\s+', '', text.lower())
        
        for capability, patterns in CapabilityMatcher.CAPABILITY_PATTERNS.items():
            matched_patterns = []
            for pattern in patterns:
                # Check original text with pattern
                if re.search(pattern, text, re.IGNORECASE):
                    matched_patterns.append(pattern)
                    continue
                
                # Check space-collapsed version (for fragmented attacks)
                # Create a space-collapsed version of the pattern
                pattern_no_space = re.sub(r'\\s\+', '', pattern)
                pattern_no_space = re.sub(r'\\s', '', pattern_no_space)
                if re.search(pattern_no_space, space_collapsed, re.IGNORECASE):
                    matched_patterns.append(pattern)
            
            if matched_patterns:
                violations[capability] = matched_patterns
        
        return violations


class AdvancedThreatDetector:
    """Main detector combining all threat detection methods"""
    
    def __init__(self):
        self.encoding_detector = EncodingDetector()
        self.homoglyph_normalizer = HomoglyphNormalizer()
        self.fragmentation_detector = WhitespaceFragmentationDetector()
        self.entropy_analyzer = EntropyAnalyzer()
        self.capability_matcher = CapabilityMatcher()
        self.injection_detector = IndirectInjectionDetector()
        self.redos_protection = ReDoSProtection()
        self.visual_detector = VisualThreatDetector()
        self.semantic_detector = SemanticThreatDetector()
    
    def detect_threat(self, text: str) -> Dict[str, Any]:
        """
        Comprehensive threat detection
        
        Returns:
            {
                'is_threat': bool,
                'threat_type': str,
                'confidence': float,
                'details': dict,
                'recommendations': list
            }
        """
        details = {
            'original_text': text,
            'decoded_variants': [],
            'normalized_text': '',
            'detected_capabilities': {},
            'entropy_score': 0.0,
            'fragmentation_detected': False,
            'indirect_injections': [],
            'redos_risk': False,
        }
        
        # TIER 5.1: Check for ReDoS attacks (BEFORE any regex)
        if self.redos_protection.has_dangerous_pattern(text):
            return {
                'is_threat': True,
                'threat_type': 'REDOS_ATTACK',
                'confidence': 0.95,
                'details': details,
                'recommendations': ['Block: ReDoS attack detected - text too large or repetitive'],
            }
        
        # TIER 5.2: Check for indirect injections (BEFORE capability check)
        has_injections, injections = self.injection_detector.detect_injections(text)
        if has_injections:
            details['indirect_injections'] = injections
            return {
                'is_threat': True,
                'threat_type': 'INDIRECT_INJECTION',
                'confidence': 0.90,
                'details': details,
                'recommendations': ['Block: Indirect system instruction injection detected'],
            }
        
        # TIER 5.3: Check for visual ASCII art threats
        visual_threat, visual_types, visual_confidence = self.visual_detector.detect_threats(text)
        if visual_threat:
            return {
                'is_threat': True,
                'threat_type': 'VISUAL_JAILBREAK',
                'confidence': visual_confidence,
                'details': {**details, 'visual_threats': visual_types},
                'recommendations': ['Block: ASCII art threat encoding detected'],
            }
        
        # TIER 5.4: Check for semantic intent threats (dangerous concepts without keywords)
        semantic_threat, semantic_types, semantic_confidence = self.semantic_detector.detect_threats(text)
        if semantic_threat:
            return {
                'is_threat': True,
                'threat_type': 'SEMANTIC_EVASION',
                'confidence': semantic_confidence,
                'details': {**details, 'semantic_threats': semantic_types},
                'recommendations': ['Block: Dangerous semantic intent detected without keyword triggers'],
            }
        
        # TIER 1: Check for direct capability violations first (highest priority)
        direct_violations = self.capability_matcher.check_capabilities(text)
        details['detected_capabilities'] = direct_violations
        
        # If direct violations found, return immediately
        if direct_violations:
            return {
                'is_threat': True,
                'threat_type': list(direct_violations.keys())[0],
                'confidence': 0.95,
                'details': details,
                'recommendations': [f"Block: {list(direct_violations.keys())[0]} detected"],
            }
        
        # 2: Encoding detection
        decoded_variants = self.encoding_detector.decode_all_encodings(text)
        details['decoded_variants'] = decoded_variants
        
        # 3: Homoglyph normalization
        normalized = self.homoglyph_normalizer.normalize(text)
        details['normalized_text'] = normalized
        
        # 4: Whitespace fragmentation
        has_fragments, reconstructed = self.fragmentation_detector.detect_fragments(text)
        if has_fragments and reconstructed:
            details['fragmentation_detected'] = True
            decoded_variants.extend(reconstructed)
        
        # 4. Entropy analysis
        entropy = self.entropy_analyzer.shannon_entropy(text)
        details['entropy_score'] = entropy
        
        # Check decoded/normalized variants for capability violations
        all_texts_to_check = [normalized] + decoded_variants
        all_violations = {}
        
        for check_text in all_texts_to_check:
            violations = self.capability_matcher.check_capabilities(check_text)
            for cap, patterns in violations.items():
                if cap not in all_violations:
                    all_violations[cap] = patterns
        
        details['detected_capabilities'] = all_violations
        
        # Determine threat level
        is_threat = False
        confidence = 0.0
        threat_type = "NONE"
        recommendations = []
        
        # Threat: Capability violation in variant
        if all_violations:
            is_threat = True
            threat_type = list(all_violations.keys())[0]
            confidence = min(0.99, 0.75 + len(all_violations) * 0.1)
            recommendations.append(f"Block: {threat_type} detected in variant")
        
        # Threat: High entropy + suspicious encoding chain
        elif decoded_variants and len(decoded_variants) > 2 and entropy > 5.2:
            is_threat = True
            threat_type = "ENCODING_EVASION"
            confidence = 0.80
            recommendations.append("Block: Suspicious encoding chain")
        
        # Threat: Fragmentation + capability-like words reconstructed
        elif has_fragments and len(decoded_variants) > 1:
            # Check if fragmented version matches any capability
            for variant in decoded_variants:
                if self.capability_matcher.check_capabilities(variant):
                    is_threat = True
                    threat_type = "FRAGMENTATION"
                    confidence = 0.85
                    recommendations.append("Block: Fragmented attack pattern detected")
                    break
        
        return {
            'is_threat': is_threat,
            'threat_type': threat_type,
            'confidence': confidence,
            'details': details,
            'recommendations': recommendations,
        }


class VisualThreatDetector:
    """Detect ASCII art and visual-based threat encodings"""
    
    def __init__(self):
        """Initialize visual threat detector"""
        # ASCII art character patterns
        self.ascii_art_patterns = [
            r'[╔╗╚╝║═╠╣╦╩╬]',  # Box drawing
            r'[█▓▒░]',  # Block elements
            r'[_\-*/+=\[\]\(\)\<\>|\\]',  # ASCII art
        ]
        self.capability_matcher = CapabilityMatcher()
    
    def extract_text_from_visual(self, text: str) -> List[str]:
        """Extract readable text from ASCII art"""
        extracted = []
        
        lines = text.split('\n')
        for line in lines:
            # Remove common ASCII art drawing characters
            cleaned = re.sub(r'[╔╗╚╝║═╠╣╦╩╬█▓▒░_\-*/+=\[\]\(\)\<\>|\\`~@#$%^&]', ' ', line)
            # Get continuous word sequences (2+ letters)
            words = re.findall(r'\b[A-Za-z]{2,}\b', cleaned)
            if words:
                extracted.extend(words)
        
        # Also try to extract as continuous text
        continuous = ' '.join(extracted)
        if continuous.strip():
            extracted.append(continuous)
        
        return extracted
    
    def detect_threats(self, text: str) -> Tuple[bool, List[str], float]:
        """Detect visual threat patterns"""
        
        # Check if text has ASCII art characteristics (multiple lines with few words, lots of special chars)
        lines = text.split('\n')
        if len(lines) < 2:
            return False, [], 0.0
        
        # Count special characters vs regular chars
        special_char_count = len(re.findall(r'[╔╗╚╝║═╠╣╦╩╬█▓▒░_\-*/+=\[\]\(\)\<\>|\\`~@#$%^&]', text))
        total_chars = len(text)
        
        # If more than 20% special chars, likely ASCII art
        has_visual_encoding = special_char_count / max(total_chars, 1) > 0.15
        
        if not has_visual_encoding:
            return False, [], 0.0
        
        # Extract text from ASCII art
        extracted_texts = self.extract_text_from_visual(text)
        
        threats_found = []
        max_confidence = 0.0
        
        # Check each extracted text for capabilities
        for extracted in extracted_texts:
            if len(extracted) > 3:  # Only check meaningful text
                violations = self.capability_matcher.check_capabilities(extracted)
                if violations:
                    threats_found.extend(list(violations.keys()))
                    max_confidence = max(max_confidence, 0.80)
        
        return len(threats_found) > 0, threats_found, max_confidence


class SemanticThreatDetector:
    """Detect semantic intent threats using embeddings or keyword fallback"""
    
    def __init__(self):
        """Initialize semantic threat detector"""
        self.dangerous_concepts = [
            "bomb making",
            "bomb creation",
            "explosive manufacturing",
            "weapon creation",
            "destructive chemistry",
            "chemical weapons",
            "biological weapons",
            "poison creation",
            "toxin synthesis",
            "hacking tutorials",
            "data theft",
            "ransomware deployment",
            "credential harvesting",
            "identity theft",
            "fraud scheme",
            "money laundering",
        ]
        
        # Enhanced keyword detection for concepts
        self.concept_keywords = {
            "bomb making": ["nitrate", "potassium", "explosive", "detonation", "fuse", "blast", "propellant", "oxidizer"],
            "weapon creation": ["firearm", "ammunition", "missile", "warhead", "trigger", "caliber"],
            "destructive chemistry": ["chemical formula", "synthesis", "compound", "reaction", "combustion", "oxidation"],
            "poison creation": ["toxic", "lethal", "dose", "arsenic", "cyanide", "strychnine"],
        }
        
        self.capability_matcher = CapabilityMatcher()
        self.embedding_enabled = False
        
        # Try to load embeddings if available
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            self.embedding_enabled = True
        except (ImportError, Exception):
            # Fallback to keyword-based detection
            self.embedding_enabled = False
    
    def semantic_similarity(self, text: str, concept: str) -> float:
        """Calculate semantic similarity between text and concept (0.0-1.0)"""
        if not self.embedding_enabled:
            return self._keyword_similarity(text, concept)
        
        try:
            text_lower = text.lower()
            concept_lower = concept.lower()
            
            text_embedding = self.embedding_model.encode(text_lower, convert_to_tensor=False)
            concept_embedding = self.embedding_model.encode(concept_lower, convert_to_tensor=False)
            
            # Calculate cosine similarity
            import numpy as np
            
            text_vec = np.array(text_embedding)
            concept_vec = np.array(concept_embedding)
            
            # Cosine similarity
            dot_product = np.dot(text_vec, concept_vec)
            norm_text = np.linalg.norm(text_vec)
            norm_concept = np.linalg.norm(concept_vec)
            
            if norm_text > 0 and norm_concept > 0:
                similarity = dot_product / (norm_text * norm_concept)
                return float(max(0.0, min(1.0, similarity)))
            
            return 0.0
        except Exception:
            return self._keyword_similarity(text, concept)
    
    def _keyword_similarity(self, text: str, concept: str) -> float:
        """Fallback keyword-based similarity detection"""
        text_lower = text.lower()
        concept_lower = concept.lower()
        
        # Direct match to concept
        if concept_lower in text_lower:
            return 0.95
        
        # Check related keywords
        max_score = 0.0
        for cpt, keywords in self.concept_keywords.items():
            if cpt.lower() in concept_lower:
                keyword_matches = sum(1 for kw in keywords if kw.lower() in text_lower)
                total_keywords = len(keywords)
                if total_keywords > 0:
                    # Score based on percentage of keywords found
                    score = (keyword_matches / total_keywords) * 0.90
                    if keyword_matches >= 2:  # At least 2 related keywords
                        score = max(score, 0.75)
                    max_score = max(max_score, score)
        
        # Check for suspicious chemistry/weapons language patterns
        suspicious_patterns = [
            r'chemical\s+(?:formula|compound|reaction)',
            r'(?:explosive|detonation|propellant)',
            r'(?:potassium|sulfur|charcoal|nitrate)',
            r'(?:fireworks|pyrotechnic)',
            r'(?:create|make|synthesis|manufacture).*(?:explosive|weapon|poison)',
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                max_score = max(max_score, 0.70)
        
        return max_score
    
    def detect_threats(self, text: str) -> Tuple[bool, List[str], float]:
        """Detect semantic intent threats"""
        
        threats_found = []
        max_confidence = 0.0
        similarity_threshold = 0.70 if self.embedding_enabled else 0.65
        
        # Check similarity to dangerous concepts
        for concept in self.dangerous_concepts:
            similarity = self.semantic_similarity(text, concept)
            
            if similarity > similarity_threshold:
                threats_found.append(concept)
                max_confidence = max(max_confidence, similarity)
        
        return len(threats_found) > 0, threats_found, max_confidence


def create_detector() -> AdvancedThreatDetector:
    """Factory function to create detector instance"""
    return AdvancedThreatDetector()
