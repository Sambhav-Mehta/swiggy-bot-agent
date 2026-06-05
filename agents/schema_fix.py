"""
agents/schema_fix.py

Monkey-patches langchain_google_genai's JSON-schema → Gemini-schema converter
to handle MCP tool parameters that use integer enum values.

Gemini's SDK (google-genai) requires every value in an 'enum' list to be a
string.  The Swiggy MCP server returns tools whose vegFilter parameter has
schema `{"enum": [0, 1]}` — integers, not strings — which causes a
ValidationError when langchain_google_genai tries to build the function
declaration for Gemini.

The patch is applied once at module import and is safe to call multiple times.
It adds string-coercion for integer/float enum values before the Gemini
validator sees them; all other schema fields pass through unchanged.
"""

import langchain_google_genai._function_utils as _fu

_orig_fn = None  # set on first apply


def _patched_dict_to_genai_schema(schema_dict, is_property=False):
    """Stringify integer enum values before Gemini schema validation."""
    if isinstance(schema_dict, dict) and "enum" in schema_dict:
        raw = schema_dict["enum"]
        if any(isinstance(v, (int, float)) for v in raw):
            schema_dict = {**schema_dict, "enum": [str(v) for v in raw]}
    return _orig_fn(schema_dict, is_property=is_property)


def apply():
    """Apply the patch once.  Idempotent — safe to call on every import."""
    global _orig_fn
    if _orig_fn is not None:
        return  # already patched
    _orig_fn = _fu._dict_to_genai_schema
    _fu._dict_to_genai_schema = _patched_dict_to_genai_schema


# Auto-apply on import so any file that does `import agents.schema_fix` is enough.
apply()
