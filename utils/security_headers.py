from __future__ import annotations

# SEC: Allowed CORS origins (configure via env)
import os
ALLOWED_ORIGINS = [
    o.strip() for o in
    os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
    if o.strip()
]

def get_cors_headers(origin: str = None) -> dict:
    """WEB-07: CORS headers for web API responses."""
    if origin and origin in ALLOWED_ORIGINS:
        allow_origin = origin
    elif ALLOWED_ORIGINS:
        allow_origin = ALLOWED_ORIGINS[0]
    else:
        allow_origin = '*'  # fallback only for dev
    return {
        'Access-Control-Allow-Origin': allow_origin,
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'",
    }
