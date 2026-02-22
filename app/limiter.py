"""Shared Limiter instance — import this everywhere, never create a new one."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
