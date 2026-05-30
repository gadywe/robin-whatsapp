"""Token-usage logging + daily cost calc for the 20:00 cost report."""
from db_postgres import get_connection
from config import PRICE_INPUT, PRICE_OUTPUT, PRICE_CACHE_READ, PRICE_CACHE_WRITE


def log_usage(input_tokens: int, output_tokens: int,
              cache_read: int, cache_creation: int):
    """Record one Claude API call's token usage. Best-effort (never raises up)."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO usage_log
                      (input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
                    VALUES (%s, %s, %s, %s)
                """, (input_tokens or 0, output_tokens or 0, cache_read or 0, cache_creation or 0))
    except Exception as e:
        print(f"WARN log_usage: {e}")


def get_today_totals() -> dict:
    """Sum today's usage (since midnight Israel time)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*),
                       COALESCE(SUM(input_tokens), 0),
                       COALESCE(SUM(output_tokens), 0),
                       COALESCE(SUM(cache_read_tokens), 0),
                       COALESCE(SUM(cache_creation_tokens), 0)
                FROM usage_log
                WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Jerusalem')
                                    AT TIME ZONE 'Asia/Jerusalem'
            """)
            row = cur.fetchone()
    calls, inp, out, cread, cwrite = row
    cost_usd = (inp * PRICE_INPUT + out * PRICE_OUTPUT
                + cread * PRICE_CACHE_READ + cwrite * PRICE_CACHE_WRITE) / 1_000_000
    return {
        "calls": calls, "input": inp, "output": out,
        "cache_read": cread, "cache_creation": cwrite,
        "cost_usd": cost_usd,
    }
