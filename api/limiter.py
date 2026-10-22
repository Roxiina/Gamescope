"""Limitation du nombre de requêtes par adresse IP (OWASP API4 et brute force)."""
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.config import get_settings

limiter = Limiter(key_func=get_remote_address,
                  default_limits=[get_settings().rate_limit_default])
