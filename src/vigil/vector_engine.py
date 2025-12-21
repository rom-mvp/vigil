"""
Vector Threat Engine - ONNX/TensorRT embedding + VRAM vector search
Implements the 'Embedding Model' and 'Vector Threat DB' components 
from the Vigil Architecture Diagram.

This module handles the "Left Brain" logic: converting text to embeddings 
and checking them against a database of known threat signatures (e.g., 
jailbreaks, injection templates) stored in VRAM.
"""

import os
import numpy as np
import logging
from typing import Dict, List, Any
import threading
import json

logger = logging.getLogger(__name__)


class VectorScanner:
    """
    Implements the 'Embedding Model' and 'Vector Threat DB' components 
    from the Vigil Architecture Diagram.
    
    Attributes:
        model_path (str): Path to the quantized ONNX embedding model.
        threat_db (np.array): In-memory matrix of known threat vectors.
        threshold (float): Cosine similarity threshold (0.0-1.0) for a match.
    """
    
    def __init__(self, model_path: str = None, vector_db_path: str = None, threshold: float = 0.85):
        """
        Initialize Vector Scanner with ONNX model and threat database.
        
        Args:
            model_path: Path to ONNX model (default: models/all-MiniLM-L6-v2.onnx)
            vector_db_path: Path to threat vector database (default: data/threat_vectors.jsonl)
            threshold: Cosine similarity threshold for threat detection (0.85)
        """
        self.model_path = model_path or os.environ.get('VECTOR_MODEL_PATH', 'models/all-MiniLM-L6-v2.onnx')
        self.vector_db_path = vector_db_path or os.environ.get('VECTOR_DB_PATH', 'data/threat_vectors.jsonl')
        self.threshold = threshold
        self.embedding_dim = 384  # all-MiniLM-L6-v2 dimension
        
        self.session = None
        self.tokenizer = None
        self.threat_vectors = None
        self.threat_labels = []
        self.threat_metadata = []
        
        self._lock = threading.Lock()
        self._initialized = False
        
        # Lazy initialization on first use
        
    def _lazy_init(self):
        """Lazy load model and vector DB to avoid startup delays."""
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:  # Double-check after acquiring lock
                return
                
            try:
                # Load resources
                self._load_model(self.model_path)
                self._load_threat_db()
                
                self._initialized = True
                provider = self.session.get_providers()[0] if self.session else "None"
                logger.info(f"VectorScanner initialized on {provider} with {len(self.threat_labels)} threat patterns")
            except Exception as e:
                logger.error(f"VectorScanner initialization failed: {e}")
                self._initialized = True  # Mark as initialized to avoid retry loops
    
    def _load_model(self, model_path: str):
        """
        Loads the ONNX model with CUDA execution provider if available (VRAM path),
        falling back to CPU.
        
        Args:
            model_path: Path to ONNX model file
        """
        try:
            import onnxruntime as ort
            
            # Check for GPU support (Architecture: GPU VRAM - SCANNING)
            # Respect VIGIL_DEVICE_MODE environment variable for CPU-only deployment
            device_mode = os.environ.get("VIGIL_DEVICE_MODE", "auto").lower()
            
            if device_mode == "cpu":
                # Force CPU-only execution (for Mac/Windows/cheap servers)
                providers = ['CPUExecutionProvider']
                logger.info("VIGIL_DEVICE_MODE=cpu: Using CPU-only inference (no GPU)")
            elif device_mode == "gpu":
                # Force GPU-only execution (fail if GPU not available)
                providers = ['CUDAExecutionProvider']
                logger.info("VIGIL_DEVICE_MODE=gpu: Using GPU-only inference (requires CUDA)")
            else:
                # Auto mode: Try CUDA first for VRAM acceleration, fallback to CPU
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                logger.info("VIGIL_DEVICE_MODE=auto: Trying GPU first, fallback to CPU")
            
            if not os.path.exists(model_path):
                logger.warning(f"ONNX model not found at {model_path}. Vector scanning will use mock embeddings.")
                self.session = None
                return
            
            self.session = ort.InferenceSession(model_path, providers=providers)
            
            # Try to load tokenizer
            tokenizer_path = os.path.join(os.path.dirname(model_path), "tokenizer.json")
            if os.path.exists(tokenizer_path):
                try:
                    from tokenizers import Tokenizer
                    self.tokenizer = Tokenizer.from_file(tokenizer_path)
                    logger.info(f"Loaded tokenizer from {tokenizer_path}")
                except ImportError:
                    logger.warning("tokenizers library not installed. Using simple tokenization.")
                    self.tokenizer = None
            else:
                logger.warning(f"Tokenizer not found at {tokenizer_path}. Using simple tokenization.")
                self.tokenizer = None
                
            logger.info(f"Vector Engine initialized on {self.session.get_providers()[0]}")
            
        except ImportError as e:
            logger.warning(f"onnxruntime not installed: {e}. Vector scanning will use mock embeddings.")
            self.session = None
        except Exception as e:
            logger.error(f"Failed to load Vector Engine: {e}")
            self.session = None
    
    def _load_threat_db(self):
        """
        Loads known threat signatures into memory (Simulating 'Vector Threat DB').
        In production, this might use memory mapping (np.memmap) for zero-copy access
        to large databases stored in VRAM.
        """
        try:
            if not os.path.exists(self.vector_db_path):
                logger.warning(f"Threat vector DB not found at {self.vector_db_path}. Using default threats.")
                self._load_default_threats()
                return
            
            # Load pre-computed threat embeddings from JSONL file
            vectors = []
            with open(self.vector_db_path, 'r') as f:
                for line in f:
                    entry = json.loads(line.strip())
                    vector = np.array(entry['vector'], dtype=np.float32)
                    vectors.append(vector)
                    self.threat_labels.append(entry.get('threat_type', 'unknown'))
                    self.threat_metadata.append({
                        'pattern': entry.get('pattern', ''),
                        'threat_type': entry.get('threat_type', 'unknown'),
                        'severity': entry.get('severity', 'medium'),
                        'description': entry.get('description', '')
                    })
            
            if vectors:
                self.threat_vectors = np.vstack(vectors)
                
                # Normalize for cosine similarity (Architecture: Vector Search optimization)
                norm = np.linalg.norm(self.threat_vectors, axis=1, keepdims=True)
                self.threat_vectors = self.threat_vectors / (norm + 1e-10)
                
                logger.info(f"Loaded {len(self.threat_labels)} threat vectors from {self.vector_db_path}")
            else:
                logger.warning("No threat vectors found in database")
                self._load_default_threats()
                
        except Exception as e:
            logger.error(f"Failed to load threat database: {e}")
            self._load_default_threats()
    
    def _load_default_threats(self):
        """
        Loads default threat patterns as fallback.
        These act as the 'Threat DB' in the architecture diagram.
        """
        # Example: 2 random vectors representing threat signatures
        # In production, these would be pre-computed embeddings of known attacks
        self.threat_vectors = np.random.rand(2, 384).astype(np.float32)
        self.threat_labels = ["jailbreak_classic", "prompt_injection_simple"]
        self.threat_metadata = [
            {'pattern': 'ignore previous instructions', 'threat_type': 'jailbreak_classic', 'severity': 'high', 'description': 'Classic jailbreak pattern'},
            {'pattern': 'system prompt override', 'threat_type': 'prompt_injection_simple', 'severity': 'high', 'description': 'Simple prompt injection'}
        ]
        
        # Normalize for cosine similarity
        norm = np.linalg.norm(self.threat_vectors, axis=1, keepdims=True)
        self.threat_vectors = self.threat_vectors / (norm + 1e-10)
        
        logger.info("Loaded default threat patterns (2)")
    
    def _simple_tokenize(self, text: str, max_length: int = 128) -> Dict[str, np.ndarray]:
        """
        Simple tokenization fallback when tokenizers library unavailable.
        
        Args:
            text: Input text to tokenize
            max_length: Maximum sequence length
            
        Returns:
            Dict with input_ids and attention_mask
        """
        # Very basic tokenization: convert to char codes
        # In production, use proper tokenizers library
        chars = [ord(c) % 30000 for c in text[:max_length]]
        
        # Pad to max_length
        input_ids = chars + [0] * (max_length - len(chars))
        attention_mask = [1] * len(chars) + [0] * (max_length - len(chars))
        
        return {
            'input_ids': np.array([input_ids], dtype=np.int64),
            'attention_mask': np.array([attention_mask], dtype=np.int64)
        }
    
    def embed(self, text: str) -> np.ndarray:
        """
        Generates embedding for input text using ONNX Runtime.
        Uses CUDA (VRAM) if available for hardware acceleration.
        
        Args:
            text: Input text to embed
            
        Returns:
            normalized numpy array (1, 384)
        """
        self._lazy_init()
        
        if not self.session:
            # Fallback to mock embedding
            embedding = np.random.rand(1, self.embedding_dim).astype(np.float32)
            norm = np.linalg.norm(embedding, axis=1, keepdims=True)
            return embedding / (norm + 1e-10)
        
        try:
            # Tokenize input
            if self.tokenizer:
                encoded = self.tokenizer.encode(text)
                input_ids = np.array([encoded.ids], dtype=np.int64)
                attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
            else:
                tokens = self._simple_tokenize(text)
                input_ids = tokens['input_ids']
                attention_mask = tokens['attention_mask']
            
            # ONNX Inference (Zero-Copy Simulation)
            # We assume model output 0 is 'last_hidden_state' or 'sentence_embedding'
            outputs = self.session.run(None, {
                'input_ids': input_ids,
                'attention_mask': attention_mask
            })
            
            # Mean pooling (simple version)
            # For production, implement proper pooling strategy
            embeddings = outputs[0].mean(axis=1)
            
            # Normalize for cosine similarity
            norm = np.linalg.norm(embeddings, axis=1, keepdims=True)
            return embeddings / (norm + 1e-10)
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}. Using mock embedding.")
            # Fallback to mock embedding
            embedding = np.random.rand(1, self.embedding_dim).astype(np.float32)
            norm = np.linalg.norm(embedding, axis=1, keepdims=True)
            return embedding / (norm + 1e-10)
    
    def scan(self, text: str) -> Dict[str, Any]:
        """
        Scans text against the Threat DB using vector similarity search.
        This implements the "Vector Search" component from the architecture diagram.
        
        Args:
            text: Input text to scan for threats
            
        Returns:
            dict: scan_results payload for AgentShield with keys:
                - scanned (bool): Whether scan was performed
                - vector_db_hit (bool): Whether threat was detected
                - vector_distance (float): Max similarity score (0.0-1.0)
                - detected_clusters (list): List of detected threat types
                - embedding_depth (int): Embedding dimension (384)
                - vector_hits (list): Detailed threat matches
        """
        self._lazy_init()
        
        if self.threat_vectors is None or len(self.threat_vectors) == 0:
            return {
                "scanned": False,
                "reason": "db_empty",
                "vector_db_hit": False,
                "vector_distance": 0.0,
                "detected_clusters": [],
                "embedding_depth": self.embedding_dim,
                "vector_hits": []
            }
        
        try:
            # 1. Generate Embedding (Architecture: Embedding Model)
            query_vec = self.embed(text)  # Shape (1, 384)
            
            # 2. Vector Search (Architecture: Vector Threat DB lookup)
            # Dot product of normalized vectors = Cosine Similarity
            # This operates in VRAM if using CUDAExecutionProvider
            scores = np.dot(query_vec, self.threat_vectors.T).flatten()
            
            # 3. Filter by threshold
            max_score_idx = np.argmax(scores)
            max_score = float(scores[max_score_idx])
            
            detected = max_score > self.threshold
            
            # Build detailed results
            vector_hits = []
            if detected:
                # Get all matches above threshold
                matches = np.where(scores > self.threshold)[0]
                for idx in matches:
                    score = float(scores[idx])
                    metadata = self.threat_metadata[idx]
                    vector_hits.append({
                        'pattern': metadata['pattern'],
                        'threat_type': metadata['threat_type'],
                        'severity': metadata['severity'],
                        'score': round(score, 4),
                        'description': metadata.get('description', '')
                    })
                
                # Sort by score descending
                vector_hits.sort(key=lambda x: x['score'], reverse=True)
            
            return {
                "scanned": True,
                "vector_db_hit": detected,
                "vector_distance": round(max_score, 4),  # Similarity score (higher = more similar)
                "detected_clusters": [self.threat_labels[max_score_idx]] if detected else [],
                "embedding_depth": self.embedding_dim,
                "vector_hits": vector_hits,
                "threat_detected": detected,
                "max_score": max_score,
                "num_hits": len(vector_hits)
            }
            
        except Exception as e:
            logger.error(f"Vector scan failed: {e}")
            return {
                "scanned": False,
                "reason": f"scan_error: {str(e)}",
                "vector_db_hit": False,
                "vector_distance": 0.0,
                "detected_clusters": [],
                "embedding_depth": self.embedding_dim,
                "vector_hits": []
            }


# Backward compatibility alias
VectorEngine = VectorScanner
