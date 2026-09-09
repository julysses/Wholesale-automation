-- Hilltop Development Command Center
-- One versioned workspace per operator keeps the first release flexible while
-- preserving account isolation and allowing future normalized project tables.
create table if not exists public.development_workspaces (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  workspace jsonb not null default '{"schema":1,"projects":[],"cash":[]}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint development_workspace_is_object check (jsonb_typeof(workspace) = 'object')
);

alter table public.development_workspaces enable row level security;

drop policy if exists "development workspaces select own" on public.development_workspaces;
create policy "development workspaces select own"
  on public.development_workspaces for select
  using (auth.uid() = user_id);

drop policy if exists "development workspaces insert own" on public.development_workspaces;
create policy "development workspaces insert own"
  on public.development_workspaces for insert
  with check (auth.uid() = user_id);

drop policy if exists "development workspaces update own" on public.development_workspaces;
create policy "development workspaces update own"
  on public.development_workspaces for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select, insert, update on public.development_workspaces to authenticated;
