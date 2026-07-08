DROP INDEX IF EXISTS "equilibrium_space_ph_idx";
DROP INDEX IF EXISTS "equilibrium_space_eh_idx";
DROP INDEX IF EXISTS "equilibrium_space_log_fo2_idx";
DROP INDEX IF EXISTS "equilibrium_space_log_ionic_strength_idx";
DROP INDEX IF EXISTS "equilibrium_space_tds_idx";
DROP INDEX IF EXISTS "equilibrium_space_solvent_mass_idx";
DROP INDEX IF EXISTS "equilibrium_space_solute_mass_idx";
DROP INDEX IF EXISTS "equilibrium_space_reactant_mass_reacted_idx";
DROP INDEX IF EXISTS "equilibrium_space_reactant_mass_remaining_idx";

DROP INDEX IF EXISTS "equilibrium_elements_log_molality_idx";
DROP INDEX IF EXISTS "equilibrium_aqueous_species_log_molality_idx";
DROP INDEX IF EXISTS "equilibrium_aqueous_species_log_activity_idx";
DROP INDEX IF EXISTS "equilibrium_pure_solids_affinity_idx";
DROP INDEX IF EXISTS "equilibrium_pure_solids_log_qk_idx";
DROP INDEX IF EXISTS "equilibrium_solid_solutions_affinity_idx";
DROP INDEX IF EXISTS "equilibrium_solid_solutions_log_qk_idx";
DROP INDEX IF EXISTS "equilibrium_end_members_affinity_idx";
DROP INDEX IF EXISTS "equilibrium_end_members_log_qk_idx";
DROP INDEX IF EXISTS "equilibrium_gases_log_fugacity_idx";
DROP INDEX IF EXISTS "equilibrium_reactants_affinity_idx";
DROP INDEX IF EXISTS "equilibrium_reactants_log_moles_reacted_idx";
DROP INDEX IF EXISTS "equilibrium_reactants_log_moles_remaining_idx";
DROP INDEX IF EXISTS "equilibrium_reactants_log_mass_reacted_idx";
DROP INDEX IF EXISTS "equilibrium_reactants_log_mass_remaining_idx";
DROP INDEX IF EXISTS "equilibrium_redox_reactions_eh_idx";
DROP INDEX IF EXISTS "equilibrium_redox_reactions_log_fo2_idx";

DROP INDEX IF EXISTS "orders_eleanor_version_idx";

DROP INDEX IF EXISTS "variable_space_order_id_idx";
DROP INDEX IF EXISTS "variable_space_exit_code_idx";

DROP INDEX IF EXISTS "equilibrium_aqueous_species_equilibrium_space_id_name_idx";
DROP INDEX IF EXISTS "equilibrium_elements_equilibrium_space_id_name_idx";
DROP INDEX IF EXISTS "equilibrium_gases_equilibrium_space_id_name_idx";
DROP INDEX IF EXISTS "equilibrium_pure_solids_equilibrium_space_id_name_idx";
DROP INDEX IF EXISTS "equilibrium_solid_solutions_equilibrium_space_id_name_idx";
DROP INDEX IF EXISTS "equilibrium_end_members_equilibrium_solid_solution_id_name_idx";
DROP INDEX IF EXISTS "equilibrium_reactants_equilibrium_space_id_name_idx";
DROP INDEX IF EXISTS "equilibrium_redox_reactions_equilibrium_space_id_couple_idx";
DROP INDEX IF EXISTS "equilibrium_pure_solids_log_moles_present_idx";
DROP INDEX IF EXISTS "equilibrium_solid_solutions_log_moles_present_idx";
DROP INDEX IF EXISTS "equilibrium_end_members_log_moles_present_idx";

-- "All ES points that have at least this much Na+ in solution."
--
--   SELECT vs.temperature, vs.pressure, a.log_molality
--   FROM equilibrium_aqueous_species a
--   JOIN equilibrium_space es ON es.id = a.equilibrium_space_id
--   JOIN variable_space  vs ON vs.id = es.variable_space_id
--   WHERE a.name = 'Na+' AND a.log_molality >= -3.0
--     AND vs.exit_code = 0;
CREATE INDEX IF NOT EXISTS "equilibrium_aqueous_species_name_log_molality_idx"
  ON "equilibrium_aqueous_species" ("name", "log_molality");

-- "Which ES points precipitate graphite?"
--
--   SELECT es.id, vs.temperature, ps.log_moles
--   FROM equilibrium_pure_solids ps
--   JOIN equilibrium_space es ON es.id = ps.equilibrium_space_id
--   JOIN variable_space  vs ON vs.id = es.variable_space_id
--   WHERE ps.name = 'graphite' AND ps.log_moles > '-Infinity'
--     AND vs.order_id = 1 AND vs.exit_code = 0;
CREATE INDEX IF NOT EXISTS "equilibrium_pure_solids_name_present_idx"
  ON "equilibrium_pure_solids" ("name", "equilibrium_space_id")
  WHERE "log_moles" > '-Infinity'::double precision;

-- Same shape for solid solutions.
--
--   SELECT es.id, vs.temperature, ss.log_moles
--   FROM equilibrium_solid_solutions ss
--   JOIN equilibrium_space es ON es.id = ss.equilibrium_space_id
--   JOIN variable_space  vs ON vs.id = es.variable_space_id
--   WHERE ss.name = 'olivine-ss' AND ss.log_moles > '-Infinity'
--     AND vs.exit_code = 0;
CREATE INDEX IF NOT EXISTS "equilibrium_solid_solutions_name_present_idx"
  ON "equilibrium_solid_solutions" ("name", "equilibrium_space_id")
  WHERE "log_moles" > '-Infinity'::double precision;

-- Unscoped stage filter, e.g. final-stage ('eq6') species across
-- converged runs. Reversed composite serves stage-only queries + carries
-- variable_space_id for the join. (The 0003 (variable_space_id, stage) composite
-- is kept as the FK join index.)
--
--   SELECT es.variable_space_id, es.log_xi, a.log_molality
--   FROM equilibrium_space es
--   JOIN variable_space vs ON vs.id = es.variable_space_id
--   JOIN equilibrium_aqueous_species a
--     ON a.equilibrium_space_id = es.id AND a.name = 'Na+'
--   WHERE es.stage = 'eq6' AND vs.exit_code = 0;
CREATE INDEX IF NOT EXISTS "equilibrium_space_stage_variable_space_id_idx"
  ON "equilibrium_space" ("stage", "variable_space_id");

-- Convergence filter (critical once only some ES points are
-- written and LEFT JOINs keep failed/empty runs).
--
--   SELECT vs.id, vs.temperature, count(es.id) AS n_equilibria
--   FROM variable_space vs
--   LEFT JOIN equilibrium_space es ON es.variable_space_id = vs.id
--   WHERE vs.order_id = 1 AND vs.exit_code = 0
--   GROUP BY vs.id, vs.temperature;
CREATE INDEX IF NOT EXISTS "variable_space_order_id_exit_code_idx"
  ON "variable_space" ("order_id", "exit_code");

-- Scoped aqueous-species lookup for a single run's reaction path.
--
--   SELECT es.log_xi, es."pH", es.temperature, a.log_molality
--   FROM equilibrium_space es
--   JOIN equilibrium_aqueous_species a
--     ON a.equilibrium_space_id = es.id AND a.name = 'Na+'
--   WHERE es.variable_space_id = 1
--   ORDER BY es.log_xi;
CREATE INDEX IF NOT EXISTS "equilibrium_aqueous_species_equilibrium_space_id_name_idx"
  ON "equilibrium_aqueous_species" ("equilibrium_space_id", "name");

-- Scoped solid abundance for a single run.
--
--   SELECT es.reactant_mass_reacted, es."pH", ps.log_moles
--   FROM equilibrium_space es
--   JOIN equilibrium_pure_solids ps
--     ON ps.equilibrium_space_id = es.id AND ps.name = 'graphite'
--   WHERE es.variable_space_id = 1 AND ps.log_moles > '-Infinity'
--   ORDER BY es.reactant_mass_reacted;
CREATE INDEX IF NOT EXISTS "equilibrium_pure_solids_equilibrium_space_id_name_idx"
  ON "equilibrium_pure_solids" ("equilibrium_space_id", "name")
  WHERE "log_moles" > '-Infinity'::double precision;

CREATE INDEX IF NOT EXISTS "equilibrium_solid_solutions_equilibrium_space_id_name_idx"
  ON "equilibrium_solid_solutions" ("equilibrium_space_id", "name")
  WHERE "log_moles" > '-Infinity'::double precision;

-- End members hang off a solid solution; cross-ensemble "where is this end member
-- present" joins up through equilibrium_solid_solutions.
--
--   SELECT es.id, em.log_moles
--   FROM equilibrium_end_members em
--   JOIN equilibrium_solid_solutions ss ON ss.id = em.equilibrium_solid_solution_id
--   JOIN equilibrium_space es ON es.id = ss.equilibrium_space_id
--   JOIN variable_space  vs ON vs.id = es.variable_space_id
--   WHERE em.name = 'fayalite' AND em.log_moles > '-Infinity'
--     AND vs.exit_code = 0;
CREATE INDEX IF NOT EXISTS "equilibrium_end_members_name_present_idx"
  ON "equilibrium_end_members" ("name", "equilibrium_solid_solution_id")
  WHERE "log_moles" > '-Infinity'::double precision;

CREATE INDEX IF NOT EXISTS "equilibrium_end_members_equilibrium_solid_solution_id_name_idx"
  ON "equilibrium_end_members" ("equilibrium_solid_solution_id", "name")
  WHERE "log_moles" > '-Infinity'::double precision;

-- "Which runs failed, and in which order?"
--
--   SELECT o.name, vs.id, vs.exit_code, vs.error
--   FROM variable_space vs
--   JOIN orders o ON o.id = vs.order_id
--   WHERE vs.exit_code <> 0;
CREATE INDEX IF NOT EXISTS "variable_space_exit_code_failed_idx"
  ON "variable_space" ("exit_code")
  WHERE "exit_code" <> 0;
