"""
Middleware to add caching headers to media files
"""
from django.conf import settings
from django.utils.cache import patch_cache_control
import hashlib


class MediaCacheMiddleware:
    """
    Middleware that adds cache headers to media file responses.
    This allows browsers and mobile apps to cache images locally.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Only add cache headers to media files
        if request.path.startswith(settings.MEDIA_URL):
            # Cache for 1 year (images rarely change)
            # Use 'public' so CDNs can cache too
            patch_cache_control(
                response,
                public=True,
                max_age=31536000,  # 1 year in seconds
                immutable=True,  # Indicates file won't change at this URL
            )
            
            # Add ETag for cache validation
            # This allows 304 Not Modified responses
            if hasattr(response, 'content') and response.content:
                etag = hashlib.md5(response.content).hexdigest()
                response['ETag'] = f'"{etag}"'
                
                # Check if client has cached version
                if request.META.get('HTTP_IF_NONE_MATCH') == f'"{etag}"':
                    response.status_code = 304
                    response.content = b''
        
        return response
