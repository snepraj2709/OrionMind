-- Qualify the selected snapshot variable used by the aggregate Reflection API RPC.
--
-- PL/pgSQL resolves an unqualified `snapshot_id` in SQL statements ambiguously when
-- both the function variable and a queried table expose that name. Rename only the
-- function variable while preserving the existing SECURITY DEFINER body and ACLs.

DO $migration$
DECLARE
    function_definition text;
    updated_definition text;
BEGIN
    SELECT pg_catalog.pg_get_functiondef(
        'public.get_reflections_for_owner(uuid, integer)'::pg_catalog.regprocedure
    )
    INTO function_definition;

    updated_definition := pg_catalog.replace(
        function_definition,
        E'\n    snapshot_id uuid;\n',
        E'\n    selected_snapshot_id uuid;\n'
    );
    updated_definition := pg_catalog.replace(
        updated_definition,
        'INTO snapshot_id, snapshot_start, snapshot_end, snapshot_source, snapshot_payload',
        'INTO selected_snapshot_id, snapshot_start, snapshot_end, snapshot_source, snapshot_payload'
    );
    updated_definition := pg_catalog.replace(
        updated_definition,
        'IF snapshot_id IS NOT NULL THEN',
        'IF selected_snapshot_id IS NOT NULL THEN'
    );
    updated_definition := pg_catalog.replace(
        updated_definition,
        'insight.snapshot_id = snapshot_id',
        'insight.snapshot_id = selected_snapshot_id'
    );
    updated_definition := pg_catalog.replace(
        updated_definition,
        'feedback.snapshot_id = snapshot_id',
        'feedback.snapshot_id = selected_snapshot_id'
    );

    IF updated_definition = function_definition
       OR pg_catalog.strpos(updated_definition, 'selected_snapshot_id uuid;') = 0
       OR pg_catalog.strpos(updated_definition, 'insight.snapshot_id = snapshot_id') > 0
       OR pg_catalog.strpos(updated_definition, 'feedback.snapshot_id = snapshot_id') > 0
    THEN
        RAISE EXCEPTION 'get_reflections_for_owner definition did not match expected shape';
    END IF;

    EXECUTE updated_definition;
END
$migration$;
