-- ARM Copilot: Supabase schema for the clause-level knowledge base.
-- Run this once in the Supabase SQL editor (Project > SQL Editor > New query).
-- Embedding size 1536 matches OpenAI text-embedding-3-small. If you change the
-- embedding model, change the vector size here and in arm_copilot/config.py.

create extension if not exists vector;

create table if not exists public.kb_chunks (
  chunk_id       text primary key,            -- e.g. OPS-CUT-001#1.2
  doc_id         text not null,               -- e.g. OPS-CUT-001
  clause_id      text not null,               -- e.g. 1.2
  clause_title   text not null,
  doc_title      text not null,
  category       text not null,               -- cutoff_times, pricing_tiers, ...
  version        text not null,
  effective_date date not null,
  content        text not null,
  embedding      vector(1536) not null,
  updated_at     timestamptz not null default now()
);

create index if not exists kb_chunks_category_idx
  on public.kb_chunks (category);

create index if not exists kb_chunks_embedding_idx
  on public.kb_chunks using hnsw (embedding vector_cosine_ops);

-- Lock the table down. With RLS on and no policies, the public (anon) and
-- logged-in roles cannot read or write it. The backend uses the service role
-- key, which bypasses RLS. Never put the service role key in a browser app.
alter table public.kb_chunks enable row level security;
revoke all on public.kb_chunks from anon, authenticated;

create or replace function public.match_chunks(
  query_embedding  vector(1536),
  match_count      int  default 5,
  filter_category  text default null
)
returns table (
  chunk_id       text,
  doc_id         text,
  clause_id      text,
  clause_title   text,
  doc_title      text,
  category       text,
  version        text,
  effective_date date,
  content        text,
  similarity     float
)
language sql
stable
as $$
  select
    c.chunk_id,
    c.doc_id,
    c.clause_id,
    c.clause_title,
    c.doc_title,
    c.category,
    c.version,
    c.effective_date,
    c.content,
    1 - (c.embedding <=> query_embedding) as similarity
  from public.kb_chunks as c
  where filter_category is null or c.category = filter_category
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

revoke all on function public.match_chunks(vector, int, text) from public, anon, authenticated;
grant execute on function public.match_chunks(vector, int, text) to service_role;
