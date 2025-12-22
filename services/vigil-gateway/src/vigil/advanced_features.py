"""
Advanced Vigil Features Module
===============================

Rate limiting, caching, and monitoring features for production deployment.
"""

import time
import hashlib
import json
from typing import Dict, Optional, Any, Callable
from functools import wraps
from collections import defaultdict
from threading import Lock
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter with per-API-key limits
    
    Supports:
    - Per-API-key rate limiting
    - Sliding window algorithm
    - Burst allowance
    - Global rate limits
    """
    
    def __init__(self):
        self.buckets = {}  # api_key -> bucket state
        self.lock = Lock()
        
        # Default limits (can be customized per API key)
        self.default_rate = 100  # requests per minute
        self.default_burst = 20  # burst capacity
        
        # Global limits
        self.global_rate = 10000  # requests per minute
        self.global_bucket = {'tokens': self.global_rate, 'last_update': time.time()}
    
    def check_rate_limit(self, api_key: str, cost: int = 1) -> Dict[str, Any]:
        """
        Check if request is within rate limit
        
        Args:
            api_key: API key identifier
            cost: Token cost (default 1, can be higher for expensive operations)
            
        Returns:
            dict: {
                'allowed': bool,
                'remaining': int,
                'reset_at': float,
                'retry_after': Optional[float]
            }
        """
        with self.lock:
            # Check global rate limit first
            if not self._check_global_limit(cost):
                return {
                    'allowed': False,
                    'remaining': 0,
                    'reset_at': time.time() + 60,
                    'retry_after': 60,
                    'reason': 'global_rate_limit_exceeded'
                }
            
            # Get or create bucket for API key
            if api_key not in self.buckets:
                self.buckets[api_key] = {
                    'tokens': self.default_rate,
                    'last_update': time.time(),
                    'rate': self.default_rate,
                    'burst': self.default_burst
                }
            
            bucket = self.buckets[api_key]
            now = time.time()
            
            # Refill tokens based on time elapsed
            elapsed = now - bucket['last_update']
            tokens_to_add = (elapsed / 60.0) * bucket['rate']
            bucket['tokens'] = min(
                bucket['rate'] + bucket['burst'],
                bucket['tokens'] + tokens_to_add
            )
            bucket['last_update'] = now
            
            # Check if enough tokens available
            if bucket['tokens'] >= cost:
                bucket['tokens'] -= cost
                return {
                    'allowed': True,
                    'remaining': int(bucket['tokens']),
                    'reset_at': now + 60,
                    'retry_after': None
                }
            else:
                # Calculate when enough tokens will be available
                tokens_needed = cost - bucket['tokens']
                seconds_to_wait = (tokens_needed / bucket['rate']) * 60
                
                return {
                    'allowed': False,
                    'remaining': 0,
                    'reset_at': now + seconds_to_wait,
                    'retry_after': seconds_to_wait,
                    'reason': 'rate_limit_exceeded'
                }
    
    def _check_global_limit(self, cost: int) -> bool:
        """Check global rate limit"""
        now = time.time()
        elapsed = now - self.global_bucket['last_update']
        
        # Refill global bucket
        tokens_to_add = (elapsed / 60.0) * self.global_rate
        self.global_bucket['tokens'] = min(
            self.global_rate * 2,  # Allow 2x burst
            self.global_bucket['tokens'] + tokens_to_add
        )
        self.global_bucket['last_update'] = now
        
        # Check and consume tokens
        if self.global_bucket['tokens'] >= cost:
            self.global_bucket['tokens'] -= cost
            return True
        return False
    
    def set_api_key_limit(self, api_key: str, rate: int, burst: int):
        """Set custom rate limit for specific API key"""
        with self.lock:
            if api_key in self.buckets:
                self.buckets[api_key]['rate'] = rate
                self.buckets[api_key]['burst'] = burst
            else:
                self.buckets[api_key] = {
                    'tokens': rate,
                    'last_update': time.time(),
                    'rate': rate,
                    'burst': burst
                }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics"""
        with self.lock:
            return {
                'total_api_keys': len(self.buckets),
                'global_remaining': int(self.global_bucket['tokens']),
                'global_rate': self.global_rate,
                'active_limits': {
                    api_key: {
                        'remaining': int(bucket['tokens']),
                        'rate': bucket['rate'],
                        'burst': bucket['burst']
                    }
                    for api_key, bucket in list(self.buckets.items())[:10]  # Top 10
                }
            }


class ResponseCache:
    """
    LRU cache for API responses with TTL support
    
    Features:
    - TTL-based expiration
    - LRU eviction
    - Size-based limits
    - Cache key hashing
    - Hit/miss metrics
    """
    
    def __init__(self, max_size: int = 10000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache = {}  # key -> (value, expiry, last_access)
        self.lock = Lock()
        
        # Metrics
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self.lock:
            if key in self.cache:
                value, expiry, _ = self.cache[key]
                
                # Check if expired
                if time.time() < expiry:
                    # Update last access time
                    self.cache[key] = (value, expiry, time.time())
                    self.hits += 1
                    return value
                else:
                    # Expired, remove
                    del self.cache[key]
            
            self.misses += 1
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache"""
        with self.lock:
            # Evict if at max size
            if len(self.cache) >= self.max_size:
                self._evict_lru()
            
            # Calculate expiry
            expiry = time.time() + (ttl or self.default_ttl)
            
            # Store
            self.cache[key] = (value, expiry, time.time())
    
    def _evict_lru(self):
        """Evict least recently used entry"""
        if not self.cache:
            return
        
        # Find LRU entry
        lru_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k][2]  # last_access time
        )
        
        del self.cache[lru_key]
        self.evictions += 1
    
    def clear(self):
        """Clear all cache entries"""
        with self.lock:
            self.cache.clear()
    
    def prune_expired(self):
        """Remove all expired entries"""
        with self.lock:
            now = time.time()
            expired_keys = [
                key for key, (_, expiry, _) in self.cache.items()
                if now >= expiry
            ]
            for key in expired_keys:
                del self.cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'evictions': self.evictions,
                'hit_rate': f"{hit_rate:.2f}%",
                'total_requests': total_requests
            }
    
    @staticmethod
    def generate_key(prompt: str, model: str, **kwargs) -> str:
        """Generate cache key from request parameters"""
        # Normalize parameters
        key_data = {
            'prompt': prompt.strip().lower(),
            'model': model,
            **{k: v for k, v in sorted(kwargs.items())}
        }
        
        # Hash to fixed-length key
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()


class MetricsCollector:
    """
    Collect and expose metrics for monitoring
    
    Tracks:
    - Request counts
    - Response times
    - Error rates
    - TEE attestation metrics
    - Cache performance
    - Rate limit hits
    """
    
    def __init__(self):
        self.metrics = defaultdict(lambda: defaultdict(int))
        self.histograms = defaultdict(list)
        self.lock = Lock()
        self.start_time = time.time()
    
    def increment(self, metric: str, value: int = 1, labels: Optional[Dict] = None):
        """Increment counter metric"""
        with self.lock:
            key = self._make_key(metric, labels)
            self.metrics['counters'][key] += value
    
    def observe(self, metric: str, value: float, labels: Optional[Dict] = None):
        """Record observation for histogram metric"""
        with self.lock:
            key = self._make_key(metric, labels)
            self.histograms[key].append(value)
            
            # Keep only last 1000 observations
            if len(self.histograms[key]) > 1000:
                self.histograms[key] = self.histograms[key][-1000:]
    
    def set_gauge(self, metric: str, value: float, labels: Optional[Dict] = None):
        """Set gauge metric"""
        with self.lock:
            key = self._make_key(metric, labels)
            self.metrics['gauges'][key] = value
    
    def _make_key(self, metric: str, labels: Optional[Dict]) -> str:
        """Create metric key with labels"""
        if not labels:
            return metric
        label_str = ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
        return f"{metric}{{{label_str}}}"
    
    def get_prometheus_format(self) -> str:
        """Export metrics in Prometheus format"""
        with self.lock:
            lines = []
            
            # Counters
            for key, value in self.metrics['counters'].items():
                lines.append(f"{key} {value}")
            
            # Gauges
            for key, value in self.metrics['gauges'].items():
                lines.append(f"{key} {value}")
            
            # Histograms (export as summary with percentiles)
            for key, values in self.histograms.items():
                if values:
                    sorted_values = sorted(values)
                    count = len(sorted_values)
                    total = sum(sorted_values)
                    
                    lines.append(f"{key}_count {count}")
                    lines.append(f"{key}_sum {total:.6f}")
                    
                    # Percentiles
                    for percentile in [0.5, 0.9, 0.95, 0.99]:
                        idx = int(count * percentile)
                        value = sorted_values[min(idx, count - 1)]
                        p_label = str(percentile).replace('.', '')
                        lines.append(f"{key}{{quantile=\"{percentile}\"}} {value:.6f}")
            
            # Uptime
            uptime = time.time() - self.start_time
            lines.append(f"vigil_uptime_seconds {uptime:.0f}")
            
            return '\n'.join(lines)
    
    def get_json_format(self) -> Dict[str, Any]:
        """Export metrics in JSON format"""
        with self.lock:
            return {
                'counters': dict(self.metrics['counters']),
                'gauges': dict(self.metrics['gauges']),
                'histograms': {
                    key: {
                        'count': len(values),
                        'sum': sum(values),
                        'min': min(values) if values else 0,
                        'max': max(values) if values else 0,
                        'avg': sum(values) / len(values) if values else 0
                    }
                    for key, values in self.histograms.items()
                },
                'uptime_seconds': time.time() - self.start_time
            }


# Global instances
rate_limiter = RateLimiter()
response_cache = ResponseCache()
metrics_collector = MetricsCollector()


# Decorators

def with_rate_limit(cost: int = 1):
    """Decorator to add rate limiting to endpoints"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract API key from request
            # This assumes Flask request context
            from flask import request, jsonify
            
            api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not api_key:
                return jsonify({'error': 'Missing API key'}), 401
            
            # Check rate limit
            result = rate_limiter.check_rate_limit(api_key, cost)
            
            if not result['allowed']:
                response = jsonify({
                    'error': 'Rate limit exceeded',
                    'retry_after': result['retry_after']
                })
                response.status_code = 429
                response.headers['Retry-After'] = str(int(result['retry_after']))
                response.headers['X-RateLimit-Remaining'] = '0'
                response.headers['X-RateLimit-Reset'] = str(int(result['reset_at']))
                
                # Track metric
                metrics_collector.increment('rate_limit_exceeded', labels={'api_key': api_key[:8]})
                
                return response
            
            # Add rate limit headers
            response = func(*args, **kwargs)
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Remaining'] = str(result['remaining'])
                response.headers['X-RateLimit-Reset'] = str(int(result['reset_at']))
            
            return response
        return wrapper
    return decorator


def with_cache(ttl: int = 300, cache_key_func: Optional[Callable] = None):
    """Decorator to add response caching"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            from flask import request, jsonify
            
            # Generate cache key
            if cache_key_func:
                cache_key = cache_key_func(*args, **kwargs)
            else:
                # Default: hash request data
                request_data = request.get_json() or {}
                cache_key = ResponseCache.generate_key(
                    prompt=str(request_data),
                    model=request_data.get('model', 'default')
                )
            
            # Check cache
            cached_response = response_cache.get(cache_key)
            if cached_response:
                metrics_collector.increment('cache_hit')
                response = jsonify(cached_response)
                response.headers['X-Cache'] = 'HIT'
                return response
            
            # Cache miss - call function
            metrics_collector.increment('cache_miss')
            response = func(*args, **kwargs)
            
            # Cache successful responses
            if hasattr(response, 'status_code') and response.status_code == 200:
                response_cache.set(cache_key, response.get_json(), ttl)
            
            if hasattr(response, 'headers'):
                response.headers['X-Cache'] = 'MISS'
            
            return response
        return wrapper
    return decorator


def with_metrics(metric_name: str):
    """Decorator to collect metrics"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                # Track success
                metrics_collector.increment(f'{metric_name}_total', labels={'status': 'success'})
                
                return result
            except Exception as e:
                # Track error
                metrics_collector.increment(f'{metric_name}_total', labels={'status': 'error'})
                raise
            finally:
                # Track duration
                duration = time.time() - start_time
                metrics_collector.observe(f'{metric_name}_duration_seconds', duration)
        
        return wrapper
    return decorator


# Health monitoring

class HealthChecker:
    """Check health of various system components"""
    
    @staticmethod
    def check_all() -> Dict[str, Any]:
        """Run all health checks"""
        checks = {
            'cache': HealthChecker.check_cache(),
            'rate_limiter': HealthChecker.check_rate_limiter(),
            'metrics': HealthChecker.check_metrics()
        }
        
        all_healthy = all(check['healthy'] for check in checks.values())
        
        return {
            'healthy': all_healthy,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'checks': checks
        }
    
    @staticmethod
    def check_cache() -> Dict[str, Any]:
        """Check cache health"""
        try:
            stats = response_cache.get_stats()
            size_ratio = stats['size'] / stats['max_size']
            
            return {
                'healthy': size_ratio < 0.9,  # Warn if >90% full
                'size': stats['size'],
                'max_size': stats['max_size'],
                'hit_rate': stats['hit_rate']
            }
        except Exception as e:
            return {'healthy': False, 'error': str(e)}
    
    @staticmethod
    def check_rate_limiter() -> Dict[str, Any]:
        """Check rate limiter health"""
        try:
            stats = rate_limiter.get_stats()
            return {
                'healthy': True,
                'total_api_keys': stats['total_api_keys'],
                'global_remaining': stats['global_remaining']
            }
        except Exception as e:
            return {'healthy': False, 'error': str(e)}
    
    @staticmethod
    def check_metrics() -> Dict[str, Any]:
        """Check metrics collector health"""
        try:
            stats = metrics_collector.get_json_format()
            return {
                'healthy': True,
                'uptime_seconds': stats['uptime_seconds'],
                'counter_count': len(stats['counters']),
                'gauge_count': len(stats['gauges'])
            }
        except Exception as e:
            return {'healthy': False, 'error': str(e)}
