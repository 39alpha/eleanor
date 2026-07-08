SELECT relname AS table, indexrelname AS index, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan ASC, relname, indexrelname;

SELECT t.relname AS table,
       i.relname AS index,
       pg_size_pretty(pg_relation_size(i.oid)) AS index_size,
       pg_relation_size(i.oid) AS index_bytes,
       ix.indisprimary AS is_pk
FROM pg_class i
JOIN pg_index ix ON ix.indexrelid = i.oid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = i.relnamespace
WHERE n.nspname = 'public' AND i.relkind = 'i'
ORDER BY pg_relation_size(i.oid) DESC;

EXPLAIN (ANALYZE, BUFFERS)
SELECT es.id, vs.temperature, ps.log_moles
FROM equilibrium_pure_solids ps
JOIN equilibrium_space es ON es.id = ps.equilibrium_space_id
JOIN variable_space vs ON vs.id = es.variable_space_id
WHERE ps.name = 'graphite' AND ps.log_moles > '-Infinity'::double precision
  AND vs.exit_code = 0;

EXPLAIN (ANALYZE, BUFFERS)
SELECT es.id, vs.temperature, ps.log_moles
FROM equilibrium_pure_solids ps
JOIN equilibrium_space es ON es.id = ps.equilibrium_space_id
JOIN variable_space vs ON vs.id = es.variable_space_id
WHERE ps.name = 'graphite' AND ps.log_moles != '-inf'
  AND vs.exit_code = 0;

EXPLAIN (ANALYZE, BUFFERS)
SELECT es.id, vs.temperature, vs.pressure
FROM equilibrium_space es
JOIN variable_space vs ON vs.id = es.variable_space_id
WHERE vs.order_id = 1 AND vs.exit_code = 0
  AND NOT EXISTS (
    SELECT 1 FROM equilibrium_pure_solids ps
    WHERE ps.equilibrium_space_id = es.id
      AND ps.name = 'graphite'
      AND ps.log_moles > '-Infinity'::double precision
  );

EXPLAIN (ANALYZE, BUFFERS)
SELECT vs.temperature, vs.pressure, a.log_molality
FROM equilibrium_aqueous_species a
JOIN equilibrium_space es ON es.id = a.equilibrium_space_id
JOIN variable_space vs ON vs.id = es.variable_space_id
WHERE a.name = 'Na+' AND a.log_molality >= -3.0
  AND vs.exit_code = 0;

EXPLAIN (ANALYZE, BUFFERS)
SELECT es.variable_space_id, a.log_molality
FROM equilibrium_space es
JOIN variable_space vs ON vs.id = es.variable_space_id
JOIN equilibrium_aqueous_species a
  ON a.equilibrium_space_id = es.id AND a.name = 'Na+'
WHERE es.stage = 'eq6' AND vs.exit_code = 0;

SELECT stage, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
FROM equilibrium_space
GROUP BY stage
ORDER BY n DESC;

EXPLAIN (ANALYZE, BUFFERS)
SELECT vs.id, vs.temperature, count(es.id) AS n_equilibria
FROM variable_space vs
LEFT JOIN equilibrium_space es ON es.variable_space_id = vs.id
WHERE vs.order_id = 1 AND vs.exit_code = 0
GROUP BY vs.id, vs.temperature;

SELECT exit_code, count(*) AS n,
       round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct
FROM variable_space
GROUP BY exit_code
ORDER BY n DESC;

EXPLAIN (ANALYZE, BUFFERS)
SELECT es.log_xi, es.reactant_mass_reacted, es."pH", es.temperature,
       a.log_molality
FROM equilibrium_space es
JOIN equilibrium_aqueous_species a
  ON a.equilibrium_space_id = es.id AND a.name = 'Na+'
WHERE es.variable_space_id = 1
ORDER BY es.log_xi;

EXPLAIN (ANALYZE, BUFFERS)
SELECT es.reactant_mass_reacted, ps.log_moles
FROM equilibrium_space es
JOIN equilibrium_pure_solids ps
  ON ps.equilibrium_space_id = es.id AND ps.name = 'graphite'
WHERE es.variable_space_id = 1 AND ps.log_moles > '-Infinity'::double precision
ORDER BY es.reactant_mass_reacted;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_id, temperature, pressure
FROM variable_space
WHERE temperature BETWEEN 200 AND 250 AND exit_code = 0;

EXPLAIN (ANALYZE, BUFFERS)
SELECT es.id, es.variable_space_id, es."pH"
FROM equilibrium_space es
WHERE es.temperature BETWEEN 200 AND 250;
