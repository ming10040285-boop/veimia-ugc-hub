-- VEIMIA UGC Hub - Phase 1 Creator CRM schema
-- Run in the Supabase SQL Editor for the veimia-ugc-crm project.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.creators (
  creator_id uuid primary key default gen_random_uuid(),
  instagram_user_id text,
  instagram_username text not null,
  instagram_username_normalized text generated always as (
    lower(trim(leading '@' from instagram_username))
  ) stored,
  instagram_profile_url text,
  follower_count bigint check (follower_count is null or follower_count >= 0),
  is_private boolean,
  last_post_at timestamptz,
  tags text[] not null default '{}',
  notes text,
  total_participation_count integer not null default 0
    check (total_participation_count >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint creators_username_not_blank
    check (length(trim(instagram_username)) > 0),
  constraint creators_allowed_tags
    check (tags <@ array['favorite', 'priority', 'do_not_invite']::text[])
);

create unique index if not exists creators_instagram_user_id_unique
  on public.creators (instagram_user_id)
  where instagram_user_id is not null;

create unique index if not exists creators_username_unique
  on public.creators (instagram_username_normalized);

create table if not exists public.campaign_participants (
  participant_id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  creator_id uuid not null references public.creators(creator_id) on delete restrict,
  product_id text,
  product_name text,
  participation_number integer not null check (participation_number > 0),
  screening_status text not null default 'pending'
    check (screening_status in ('pending', 'eligible', 'manual_review', 'filtered')),
  screening_reason text,
  dm_status text not null default 'pending'
    check (dm_status in ('pending', 'sent', 'replied', 'agreed', 'no_response', 'rejected')),
  dm_sent_at timestamptz,
  dm_updated_at timestamptz,
  form_status text not null default 'pending'
    check (form_status in ('pending', 'submitted')),
  form_submitted_at timestamptz,
  shipping_status text not null default 'pending'
    check (shipping_status in ('pending', 'preparing', 'shipped', 'in_transit', 'delivered')),
  order_number text,
  tracking_number text,
  carrier text,
  shipped_at timestamptz,
  delivered_at timestamptz,
  latest_tracking_status text,
  last_logistics_update timestamptz,
  shipping_update_source text
    check (shipping_update_source is null or shipping_update_source in ('logistics_api', 'manual')),
  ugc_status text not null default 'pending'
    check (ugc_status in ('pending', 'waiting_for_content', 'posted', 'completed')),
  source_provider text,
  source_registration_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint campaign_participant_unique unique (campaign_id, creator_id)
);

create index if not exists participants_campaign_idx
  on public.campaign_participants (campaign_id);
create index if not exists participants_creator_idx
  on public.campaign_participants (creator_id);
create index if not exists participants_workflow_idx
  on public.campaign_participants (
    campaign_id, screening_status, dm_status, shipping_status, ugc_status
  );
create unique index if not exists participants_source_key_unique
  on public.campaign_participants (source_provider, source_registration_key)
  where source_provider is not null and source_registration_key is not null;

create or replace function public.assign_participation_number()
returns trigger
language plpgsql
as $$
begin
  perform 1 from public.creators
    where creator_id = new.creator_id
    for update;

  if new.participation_number is null or new.participation_number <= 0 then
    select count(*) + 1
      into new.participation_number
      from public.campaign_participants
      where creator_id = new.creator_id;
  end if;
  return new;
end;
$$;

create or replace function public.sync_creator_participation_count()
returns trigger
language plpgsql
as $$
declare
  affected_creator_id uuid;
begin
  affected_creator_id := coalesce(new.creator_id, old.creator_id);
  update public.creators
    set total_participation_count = (
      select count(*) from public.campaign_participants
      where creator_id = affected_creator_id
    )
    where creator_id = affected_creator_id;

  if tg_op = 'UPDATE' and old.creator_id <> new.creator_id then
    update public.creators
      set total_participation_count = (
        select count(*) from public.campaign_participants
        where creator_id = old.creator_id
      )
      where creator_id = old.creator_id;
  end if;
  return coalesce(new, old);
end;
$$;

drop trigger if exists creators_set_updated_at on public.creators;
create trigger creators_set_updated_at
before update on public.creators
for each row execute function public.set_updated_at();

drop trigger if exists participants_assign_number on public.campaign_participants;
create trigger participants_assign_number
before insert on public.campaign_participants
for each row execute function public.assign_participation_number();

drop trigger if exists participants_set_updated_at on public.campaign_participants;
create trigger participants_set_updated_at
before update on public.campaign_participants
for each row execute function public.set_updated_at();

drop trigger if exists participants_sync_creator_count on public.campaign_participants;
create trigger participants_sync_creator_count
after insert or delete or update of creator_id on public.campaign_participants
for each row execute function public.sync_creator_participation_count();

-- CRM tables contain internal workflow and creator data. Keep them inaccessible
-- to Supabase anon/authenticated Data API roles; only the server connection may use them.
alter table public.creators enable row level security;
alter table public.campaign_participants enable row level security;

revoke all on table public.creators from anon, authenticated;
revoke all on table public.campaign_participants from anon, authenticated;

comment on table public.creators is
  'Long-lived creator identity and CRM profile.';
comment on table public.campaign_participants is
  'Per-Campaign workflow state for a Creator.';
comment on column public.campaign_participants.participation_number is
  'Automatically assigned sequence number for this Creator across Campaigns.';
