-- VEIMIA UGC Hub - Persistent administrator-started automation jobs
-- Run after 001_creator_crm.sql in the Supabase SQL Editor.

create table if not exists public.automation_jobs (
  job_id uuid primary key default gen_random_uuid(),
  campaign_id text not null,
  job_type text not null
    check (job_type in ('COMMENT_IMPORT', 'PROFILE_SCREENING', 'UGC_MONITORING')),
  status text not null default 'queued'
    check (status in (
      'queued', 'running', 'stop_requested', 'succeeded', 'failed', 'stopped'
    )),
  input jsonb not null default '{}'::jsonb,
  checkpoint jsonb not null default '{}'::jsonb,
  progress_current integer not null default 0
    check (progress_current >= 0),
  progress_total integer not null default 0
    check (progress_total >= 0),
  stats jsonb not null default '{}'::jsonb,
  failure_count integer not null default 0
    check (failure_count >= 0),
  error_message text,
  retry_of_job_id uuid references public.automation_jobs(job_id) on delete set null,
  lease_expires_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint automation_jobs_campaign_not_blank
    check (length(trim(campaign_id)) > 0)
);

create index if not exists automation_jobs_campaign_created_idx
  on public.automation_jobs (campaign_id, created_at desc);

create index if not exists automation_jobs_status_created_idx
  on public.automation_jobs (status, created_at);

create index if not exists automation_jobs_lease_idx
  on public.automation_jobs (lease_expires_at)
  where status = 'running';

drop trigger if exists automation_jobs_set_updated_at on public.automation_jobs;
create trigger automation_jobs_set_updated_at
before update on public.automation_jobs
for each row execute function public.set_updated_at();

alter table public.automation_jobs enable row level security;
revoke all on table public.automation_jobs from anon, authenticated;

comment on table public.automation_jobs is
  'Persistent audit history for administrator-started Campaign automation jobs.';
comment on column public.automation_jobs.status is
  'queued, running, stop_requested, succeeded, failed, or stopped.';
comment on column public.automation_jobs.retry_of_job_id is
  'Original job retained when an administrator creates a retry.';