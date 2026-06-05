"""
backend/db/connection.py

Supabase client + SQLAlchemy async engine.
Both are initialised lazily on first use so the import never fails
if the env vars are not yet configured (e.g. during local dev without DB).
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_supabase_client():
    """Return a singleton Supabase admin client (uses service role key)."""
    from supabase import create_client, Client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def get_supabase_anon_client():
    """Return a Supabase client using the anon/public key (for auth ops)."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_ANON_KEY"]
    return create_client(url, key)
