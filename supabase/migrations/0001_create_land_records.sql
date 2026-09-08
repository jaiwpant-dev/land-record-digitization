-- Minimal persistence schema for the FastAPI land-record API.
create extension if not exists pgcrypto;

create table if not exists public.land_records (
    id uuid primary key default gen_random_uuid(),
    document_url text,
    owner_name text,
    father_name text,
    district text,
    tehsil text,
    village text,
    khata_number text,
    khasra_number text,
    area numeric(16, 4) check (area is null or area >= 0),
    area_unit varchar(50),
    land_type varchar(100),
    validation_status varchar(50),
    validation_result jsonb,
    confidence jsonb,
    processing_status varchar(50),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Upgrade a pre-existing table created before the API persistence contract.
alter table public.land_records add column if not exists document_url text;
alter table public.land_records add column if not exists owner_name text;
alter table public.land_records add column if not exists father_name text;
alter table public.land_records add column if not exists district text;
alter table public.land_records add column if not exists tehsil text;
alter table public.land_records add column if not exists village text;
alter table public.land_records add column if not exists khata_number text;
alter table public.land_records add column if not exists khasra_number text;
alter table public.land_records add column if not exists area numeric(16, 4);
alter table public.land_records add column if not exists area_unit varchar(50);
alter table public.land_records add column if not exists land_type varchar(100);
alter table public.land_records add column if not exists validation_status varchar(50);
alter table public.land_records add column if not exists validation_result jsonb;
alter table public.land_records add column if not exists confidence jsonb;
alter table public.land_records add column if not exists processing_status varchar(50);
alter table public.land_records add column if not exists created_at timestamptz not null default now();
alter table public.land_records add column if not exists updated_at timestamptz not null default now();

create index if not exists land_records_location_idx
    on public.land_records (district, tehsil, village);
create index if not exists land_records_created_at_idx
    on public.land_records (created_at desc);

create or replace function public.set_land_records_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists land_records_set_updated_at on public.land_records;
create trigger land_records_set_updated_at
before update on public.land_records
for each row execute function public.set_land_records_updated_at();
