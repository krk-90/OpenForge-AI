create extension if not exists vector;

create table if not exists public.rag_documents (
    id text primary key,
    user_id text not null,
    repository_id text not null,
    source text not null,
    file_path text not null,
    content text not null,
    chunk_id integer not null,
    language text not null default 'unknown',
    chunk_type text not null default 'code'
        check (chunk_type in ('code', 'doc', 'config')),
    chunk_kind text not null default 'semantic'
        check (chunk_kind in ('ast', 'semantic', 'hierarchical')),
    symbols text[] not null default '{}',
    metadata jsonb not null default '{}'::jsonb,
    commit_sha text not null default '',
    embedding vector(384) not null,
    search_vector tsvector,
    created_at timestamptz not null default now()
);

alter table public.rag_documents
    add column if not exists chunk_kind text not null default 'semantic'
        check (chunk_kind in ('ast', 'semantic', 'hierarchical'));
alter table public.rag_documents
    add column if not exists symbols text[] not null default '{}';
alter table public.rag_documents
    add column if not exists metadata jsonb not null default '{}'::jsonb;

do $$
begin
    if exists (
        select 1
        from pg_attribute
        where attrelid = 'public.rag_documents'::regclass
          and attname = 'search_vector'
          and attgenerated <> ''
          and not attisdropped
    ) then
        alter table public.rag_documents drop column search_vector;
    end if;
end;
$$;

alter table public.rag_documents
    add column if not exists search_vector tsvector;

create or replace function public.update_rag_document_search_vector()
returns trigger
language plpgsql
as $$
begin
    new.search_vector := to_tsvector(
        'english',
        coalesce(new.content, '') || ' ' || array_to_string(coalesce(new.symbols, '{}'::text[]), ' ')
    );
    return new;
end;
$$;

drop trigger if exists rag_documents_search_vector_trigger on public.rag_documents;
create trigger rag_documents_search_vector_trigger
before insert or update of content, symbols on public.rag_documents
for each row execute function public.update_rag_document_search_vector();

update public.rag_documents
set search_vector = to_tsvector(
    'english',
    coalesce(content, '') || ' ' || array_to_string(coalesce(symbols, '{}'::text[]), ' ')
)
where search_vector is null;

create index if not exists rag_documents_scope_idx
    on public.rag_documents (user_id, repository_id);
create index if not exists rag_documents_embedding_idx
    on public.rag_documents using hnsw (embedding vector_cosine_ops);
create index if not exists rag_documents_search_idx
    on public.rag_documents using gin (search_vector);

create table if not exists public.rag_repository_knowledge (
    user_id text not null,
    repository_id text not null,
    repository_name text not null,
    summary text not null,
    architecture text not null,
    metadata jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    primary key (user_id, repository_id)
);

create table if not exists public.rag_graph_nodes (
    id text primary key,
    user_id text not null,
    repository_id text not null,
    name text not null,
    kind text not null,
    source text not null,
    summary text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    search_vector tsvector
);

do $$
begin
    if exists (
        select 1
        from pg_attribute
        where attrelid = 'public.rag_graph_nodes'::regclass
          and attname = 'search_vector'
          and attgenerated <> ''
          and not attisdropped
    ) then
        alter table public.rag_graph_nodes drop column search_vector;
    end if;
end;
$$;

alter table public.rag_graph_nodes
    add column if not exists search_vector tsvector;

create or replace function public.update_rag_graph_node_search_vector()
returns trigger
language plpgsql
as $$
begin
    new.search_vector := to_tsvector(
        'english',
        coalesce(new.name, '') || ' ' || coalesce(new.summary, '')
    );
    return new;
end;
$$;

drop trigger if exists rag_graph_nodes_search_vector_trigger on public.rag_graph_nodes;
create trigger rag_graph_nodes_search_vector_trigger
before insert or update of name, summary on public.rag_graph_nodes
for each row execute function public.update_rag_graph_node_search_vector();

update public.rag_graph_nodes
set search_vector = to_tsvector('english', coalesce(name, '') || ' ' || coalesce(summary, ''))
where search_vector is null;

create table if not exists public.rag_graph_edges (
    id text primary key,
    user_id text not null,
    repository_id text not null,
    source_node text not null,
    target_node text not null,
    relation text not null,
    source text not null,
    metadata jsonb not null default '{}'::jsonb
);

create index if not exists rag_graph_nodes_scope_idx
    on public.rag_graph_nodes (user_id, repository_id);
create index if not exists rag_graph_nodes_search_idx
    on public.rag_graph_nodes using gin (search_vector);
create index if not exists rag_graph_edges_scope_idx
    on public.rag_graph_edges (user_id, repository_id, relation);
create index if not exists rag_graph_edges_source_idx
    on public.rag_graph_edges (source_node);
create index if not exists rag_graph_edges_target_idx
    on public.rag_graph_edges (target_node);

alter table public.rag_documents enable row level security;
alter table public.rag_repository_knowledge enable row level security;
alter table public.rag_graph_nodes enable row level security;
alter table public.rag_graph_edges enable row level security;
grant usage on schema public to service_role;
grant select, insert, update, delete on public.rag_documents to service_role;
grant select, insert, update, delete on public.rag_repository_knowledge to service_role;
grant select, insert, update, delete on public.rag_graph_nodes to service_role;
grant select, insert, update, delete on public.rag_graph_edges to service_role;
grant usage on schema public to authenticated;
grant select, insert, update, delete on public.rag_documents to authenticated;
grant select, insert, update, delete on public.rag_repository_knowledge to authenticated;
grant select, insert, update, delete on public.rag_graph_nodes to authenticated;
grant select, insert, update, delete on public.rag_graph_edges to authenticated;

drop policy if exists rag_documents_owner_policy on public.rag_documents;
create policy rag_documents_owner_policy
    on public.rag_documents for all to authenticated
    using (auth.uid()::text = user_id)
    with check (auth.uid()::text = user_id);

drop policy if exists rag_repository_knowledge_owner_policy on public.rag_repository_knowledge;
create policy rag_repository_knowledge_owner_policy
    on public.rag_repository_knowledge for all to authenticated
    using (auth.uid()::text = user_id)
    with check (auth.uid()::text = user_id);

drop policy if exists rag_graph_nodes_owner_policy on public.rag_graph_nodes;
create policy rag_graph_nodes_owner_policy
    on public.rag_graph_nodes for all to authenticated
    using (auth.uid()::text = user_id)
    with check (auth.uid()::text = user_id);

drop policy if exists rag_graph_edges_owner_policy on public.rag_graph_edges;
create policy rag_graph_edges_owner_policy
    on public.rag_graph_edges for all to authenticated
    using (auth.uid()::text = user_id)
    with check (auth.uid()::text = user_id);

drop function if exists public.match_rag_documents(vector, text, text, integer);

create function public.match_rag_documents(
    query_embedding vector(384),
    match_user_id text,
    match_repository_id text,
    match_count integer default 6
)
returns table (
    id text,
    user_id text,
    repository_id text,
    source text,
    file_path text,
    content text,
    chunk_id integer,
    language text,
    chunk_type text,
    chunk_kind text,
    symbols text[],
    metadata jsonb,
    commit_sha text,
    similarity double precision
)
language sql
stable
as $$
    select
        document.id,
        document.user_id,
        document.repository_id,
        document.source,
        document.file_path,
        document.content,
        document.chunk_id,
        document.language,
        document.chunk_type,
        document.chunk_kind,
        document.symbols,
        document.metadata,
        document.commit_sha,
        1 - (document.embedding <=> query_embedding) as similarity
    from public.rag_documents as document
    where document.user_id = match_user_id
      and document.repository_id = match_repository_id
    order by document.embedding <=> query_embedding
    limit greatest(match_count, 0);
$$;

grant execute on function public.match_rag_documents(vector, text, text, integer)
    to service_role;

create or replace function public.search_rag_documents(
    query_text text,
    match_user_id text,
    match_repository_id text,
    match_count integer default 8
)
returns table (
    id text,
    user_id text,
    repository_id text,
    source text,
    file_path text,
    content text,
    chunk_id integer,
    language text,
    chunk_type text,
    chunk_kind text,
    symbols text[],
    metadata jsonb,
    commit_sha text,
    similarity double precision
)
language sql
stable
as $$
    select
        document.id,
        document.user_id,
        document.repository_id,
        document.source,
        document.file_path,
        document.content,
        document.chunk_id,
        document.language,
        document.chunk_type,
        document.chunk_kind,
        document.symbols,
        document.metadata,
        document.commit_sha,
        ts_rank_cd(
            document.search_vector,
            websearch_to_tsquery('english', query_text)
        )::double precision as similarity
    from public.rag_documents as document
    where document.user_id = match_user_id
      and document.repository_id = match_repository_id
      and document.search_vector @@ websearch_to_tsquery('english', query_text)
    order by similarity desc
    limit greatest(match_count, 0);
$$;

create or replace function public.search_rag_graph_nodes(
    query_text text,
    match_user_id text,
    match_repository_id text,
    match_count integer default 8
)
returns table (
    id text,
    name text,
    kind text,
    source text,
    summary text,
    metadata jsonb,
    similarity double precision
)
language sql
stable
as $$
    select
        node.id,
        node.name,
        node.kind,
        node.source,
        node.summary,
        node.metadata,
        ts_rank_cd(
            node.search_vector,
            websearch_to_tsquery('english', query_text)
        )::double precision as similarity
    from public.rag_graph_nodes as node
    where node.user_id = match_user_id
      and node.repository_id = match_repository_id
      and node.search_vector @@ websearch_to_tsquery('english', query_text)
    order by similarity desc
    limit greatest(match_count, 0);
$$;

create or replace function public.expand_rag_graph_nodes(
    match_node_ids text[],
    match_user_id text,
    match_repository_id text,
    match_count integer default 12
)
returns table (
    id text,
    name text,
    kind text,
    source text,
    summary text,
    metadata jsonb,
    relation text,
    similarity double precision
)
language sql
stable
as $$
    select distinct
        node.id,
        node.name,
        node.kind,
        node.source,
        node.summary,
        node.metadata,
        edge.relation,
        0.5::double precision as similarity
    from public.rag_graph_edges as edge
    join public.rag_graph_nodes as node
      on node.id = case
          when edge.source_node = any(match_node_ids) then edge.target_node
          else edge.source_node
      end
    where edge.user_id = match_user_id
      and edge.repository_id = match_repository_id
      and node.user_id = match_user_id
      and node.repository_id = match_repository_id
      and (edge.source_node = any(match_node_ids) or edge.target_node = any(match_node_ids))
    limit greatest(match_count, 0);
$$;

grant execute on function public.search_rag_documents(text, text, text, integer)
    to service_role;
grant execute on function public.search_rag_graph_nodes(text, text, text, integer)
    to service_role;
grant execute on function public.expand_rag_graph_nodes(text[], text, text, integer)
    to service_role;