-- VEIMIA UGC Hub - Candidate screening staging area
-- Run after 001_creator_crm.sql in the Supabase SQL Editor.

create table if not exists public.creator_candidates (
  candidate_id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  instagram_username text not null,
  instagram_username_normalized text generated always as (
    lower(trim(leading '@' from instagram_username))
  ) stored,
  instagram_profile_url text,
  follower_count bigint check (follower_count is null or follower_count >= 0),
  is_private boolean,
  last_post_at timestamptz,
  screening_status text not null default 'pending'
    check (screening_status in (
      'pending', 'eligible', 'manual_review', 'filtered', 'promoted'
    )),
  screening_reason text,
  profile_check_status text not null default 'not_started'
    check (profile_check_status in ('not_started', 'queued', 'success', 'failed')),
  profile_checked_at timestamptz,
  source_provider text,
  source_key text,
  promoted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint candidate_username_not_blank
    check (length(trim(instagram_username)) > 0),
  constraint candidate_campaign_username_unique
    unique (campaign_id, instagram_username_normalized)
);

create index if not exists candidates_campaign_status_idx
  on public.creator_candidates (campaign_id, screening_status, updated_at desc);

create unique index if not exists candidates_source_key_unique
  on public.creator_candidates (source_provider, source_key)
  where source_provider is not null and source_key is not null;

drop trigger if exists candidates_set_updated_at on public.creator_candidates;
create trigger candidates_set_updated_at
before update on public.creator_candidates
for each row execute function public.set_updated_at();

alter table public.creator_candidates enable row level security;
revoke all on table public.creator_candidates from anon, authenticated;

comment on table public.creator_candidates is
  'Campaign-scoped screening staging area; candidates are not Creators until promoted.';
comment on column public.creator_candidates.screening_status is
  'Only eligible candidates may be explicitly promoted into Creator CRM.';
