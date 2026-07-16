"""
Drží rozpracovaný požadavek na grafiku mezi jednotlivými Slack zprávami.
Jedno vlákno (thread_ts) = jeden požadavek, dokud není hotový nebo zrušený.

Potřebuje v Supabase tabulku (spusť v SQL editoru):

create table if not exists grafika_requests (
  id uuid primary key default gen_random_uuid(),
  thread_ts text not null unique,
  channel_id text not null,
  pillar text,
  collected_data jsonb not null default '{}',
  status text not null default 'sbírání_dat',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
"""
import os
from supabase import create_client

_client = None


def get_client():
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],  # service key, ne anon — tohle běží server-side, ne v prohlížeči
        )
    return _client


def get_request(thread_ts: str):
    res = get_client().table("grafika_requests").select("*").eq("thread_ts", thread_ts).execute()
    return res.data[0] if res.data else None


def create_request(thread_ts: str, channel_id: str):
    res = get_client().table("grafika_requests").insert({
        "thread_ts": thread_ts,
        "channel_id": channel_id,
        "collected_data": {},
        "status": "sbírání_dat",
    }).execute()
    return res.data[0]


def update_request(thread_ts: str, **fields):
    fields["updated_at"] = "now()"
    get_client().table("grafika_requests").update(fields).eq("thread_ts", thread_ts).execute()


def get_or_create(thread_ts: str, channel_id: str):
    existing = get_request(thread_ts)
    if existing:
        return existing
    return create_request(thread_ts, channel_id)
