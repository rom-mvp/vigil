from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class PIIEngine:
    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    def scan_and_redact(self, text):
        if not text or not isinstance(text, str):
            return text, False
        
        # Detect PII (Context Aware)
        results = self.analyzer.analyze(text=text, language='en', entities=["PHONE_NUMBER", "EMAIL_ADDRESS", "PERSON", "LOCATION", "CREDIT_CARD"])
        
        if not results:
            return text, False

        # Redact PII
        anonymized_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators={
                "DEFAULT": OperatorConfig("replace", {"new_value": "<REDACTED_PII>"}),
                "PERSON": OperatorConfig("replace", {"new_value": "<REDACTED_PERSON>"}),
                "LOCATION": OperatorConfig("replace", {"new_value": "<REDACTED_LOCATION>"}),
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "<REDACTED_PHONE>"}),
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "<REDACTED_EMAIL>"})
            }
        )
        return anonymized_result.text, True
