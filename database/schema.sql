create table articles (
  id text primary key, company text not null, title text, url text, source text,
  published_at timestamptz, snippet text, origin text,
  created_at timestamptz default now(), snippet_tried boolean default false,
  esg_label text, esg_conf real, aspect text, relevance real,
  sentiment text, impact_score real, processed_at timestamptz);

create index on articles (company, published_at desc);
create index on articles (processed_at) where processed_at is null;
alter table articles enable row level security;

create table company_scores (
  company text primary key, e jsonb, s jsonb, g jsonb,
  overall real, label text, articles int,
  updated_at timestamptz default now());

alter table company_scores enable row level security;
create policy "public read" on company_scores for select using (true);
