-- Create a starter org (Lenskart) and optionally Zomato later
insert into organizations (id, name, slug, status)
values ('00000000-0000-0000-0000-000000000001', 'Lenskart', 'lenskart', 'active')
on conflict do nothing;
