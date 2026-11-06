-- Synthetic local-only catalog rows. No hosted-project data is imported here.
update public.kra_state
set columns = '["kwd_no", "키워드명", "상품카테고리", "리스크 등급", "대체키워드", "리스크 등급별 세부 심의기준", "증빙자료유형"]'::jsonb
where id = true;

insert into public.kra_keywords (kwd_no, data, hit_count, last_hit)
values
    ('LOCAL001', '{"키워드명":"연구용 테스트키워드","상품카테고리":"테스트","리스크 등급":"테스트","대체키워드":"","리스크 등급별 세부 심의기준":"로컬 QA 전용 가상 행","증빙자료유형":""}'::jsonb, 0, ''),
    ('LOCAL002', '{"키워드명":"가상 후보표현","상품카테고리":"테스트","리스크 등급":"검수용","대체키워드":"","리스크 등급별 세부 심의기준":"로컬 QA 전용 가상 행","증빙자료유형":""}'::jsonb, 0, '')
on conflict (kwd_no) do update
set data = excluded.data, hit_count = 0, last_hit = '';
