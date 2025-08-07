# accounts/middleware.py
from django.core.cache import cache
from django.http import JsonResponse
import time

class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Rate limit settings
        self.RATE_LIMIT = 1000  # Max requests
        self.WINDOW_SECONDS = 5  # Time window
        self.COOLDOWN = 5  # Cooldown period after limit reached

    def __call__(self, request):
        # Apply to ALL API endpoints
        if request.path.startswith('/api/'):
            ip = self.get_client_ip(request)
            cache_key = f'ratelimit:{ip}'

            # Get current request data
            request_data = cache.get(cache_key, {'count': 0, 'reset_time': 0})
            current_time = time.time()

            # Check if we need to reset the counter
            if current_time > request_data['reset_time']:
                request_data = {
                    'count': 0,
                    'reset_time': current_time + self.WINDOW_SECONDS
                }

            # Check if rate limit exceeded
            if request_data['count'] >= self.RATE_LIMIT:
                return JsonResponse(
                    {
                        'detail': f'Too many requests. Please wait {self.COOLDOWN} seconds',
                        'cooldown': self.COOLDOWN,
                        'status': 'rate_limit_exceeded'
                    },
                    status=429
                )

            # Update count and save
            request_data['count'] += 1
            cache.set(cache_key, request_data, self.WINDOW_SECONDS)

        return self.get_response(request)

    def get_client_ip(self, request):
        # Get IP from X-Forwarded-For header if behind proxy
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()

        # Fallback to REMOTE_ADDR
        return request.META.get('REMOTE_ADDR')