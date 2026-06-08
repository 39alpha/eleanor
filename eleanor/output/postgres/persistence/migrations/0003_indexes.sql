-- FK indexes, composite (fk_col, name/identifier) indexes on named child
-- tables, a (variable_space_id, stage) composite on equilibrium_space for
-- stage-filtered queries, partial indexes on tables whose log_moles defaults
-- to -Infinity for efficient "mineral precipitated" filtering, and standalone
-- B-tree indexes on quantity/measurement columns for global range filters.

-- variable_space → orders FK
CREATE INDEX IF NOT EXISTS "variable_space_order_id_idx"
  ON "variable_space" ("order_id");

-- variable_space: input conditions and convergence status
CREATE INDEX IF NOT EXISTS "variable_space_exit_code_idx"
  ON "variable_space" ("exit_code");

CREATE INDEX IF NOT EXISTS "variable_space_temperature_idx"
  ON "variable_space" ("temperature");

CREATE INDEX IF NOT EXISTS "variable_space_pressure_idx"
  ON "variable_space" ("pressure");

-- VS-side leaf tables: (variable_space_id, name) composites serve both the
-- FK join and name-equality filters in a single index scan.
CREATE INDEX IF NOT EXISTS "elements_variable_space_id_name_idx"
  ON "elements" ("variable_space_id", "name");

CREATE INDEX IF NOT EXISTS "species_variable_space_id_name_idx"
  ON "species" ("variable_space_id", "name");

CREATE INDEX IF NOT EXISTS "mineral_reactants_variable_space_id_name_idx"
  ON "mineral_reactants" ("variable_space_id", "name");

CREATE INDEX IF NOT EXISTS "aqueous_reactants_variable_space_id_name_idx"
  ON "aqueous_reactants" ("variable_space_id", "name");

CREATE INDEX IF NOT EXISTS "gas_reactants_variable_space_id_name_idx"
  ON "gas_reactants" ("variable_space_id", "name");

CREATE INDEX IF NOT EXISTS "element_reactants_variable_space_id_name_idx"
  ON "element_reactants" ("variable_space_id", "name");

CREATE INDEX IF NOT EXISTS "special_reactants_variable_space_id_name_idx"
  ON "special_reactants" ("variable_space_id", "name");

CREATE INDEX IF NOT EXISTS "fixed_gas_reactants_variable_space_id_name_idx"
  ON "fixed_gas_reactants" ("variable_space_id", "name");

CREATE INDEX IF NOT EXISTS "solid_solution_reactants_variable_space_id_name_idx"
  ON "solid_solution_reactants" ("variable_space_id", "name");

-- suppressions: plain FK (name is nullable; composite less useful)
CREATE INDEX IF NOT EXISTS "suppressions_variable_space_id_idx"
  ON "suppressions" ("variable_space_id");

-- Deep VS-side child tables: plain FK / (fk_col, identifier) composites.
CREATE INDEX IF NOT EXISTS "suppression_exceptions_suppression_id_idx"
  ON "suppression_exceptions" ("suppression_id");

CREATE INDEX IF NOT EXISTS "special_reactant_compositions_special_reactant_id_element_idx"
  ON "special_reactant_compositions" ("special_reactant_id", "element");

CREATE INDEX IF NOT EXISTS "solid_solution_reactant_end_members_ssr_id_name_idx"
  ON "solid_solution_reactant_end_members" ("solid_solution_reactant_id", "name");

-- equilibrium_space: (variable_space_id, stage) covers both the FK join and
-- stage-equality filters (e.g. WHERE stage = 'eq6'), and also subsumes the
-- plain variable_space_id FK index since it is the leading column.
CREATE INDEX IF NOT EXISTS "equilibrium_space_variable_space_id_stage_idx"
  ON "equilibrium_space" ("variable_space_id", "stage");

-- equilibrium_space: solution-level quantities
CREATE INDEX IF NOT EXISTS "equilibrium_space_ph_idx"
  ON "equilibrium_space" ("pH");

CREATE INDEX IF NOT EXISTS "equilibrium_space_eh_idx"
  ON "equilibrium_space" ("Eh");

CREATE INDEX IF NOT EXISTS "equilibrium_space_temperature_idx"
  ON "equilibrium_space" ("temperature");

CREATE INDEX IF NOT EXISTS "equilibrium_space_pressure_idx"
  ON "equilibrium_space" ("pressure");

CREATE INDEX IF NOT EXISTS "equilibrium_space_log_fo2_idx"
  ON "equilibrium_space" ("log_fO2");

CREATE INDEX IF NOT EXISTS "equilibrium_space_log_ionic_strength_idx"
  ON "equilibrium_space" ("log_ionic_strength");

CREATE INDEX IF NOT EXISTS "equilibrium_space_tds_idx"
  ON "equilibrium_space" ("tds");

-- equilibrium_space: mass columns used for water-rock ratio calculations
CREATE INDEX IF NOT EXISTS "equilibrium_space_solvent_mass_idx"
  ON "equilibrium_space" ("solvent_mass");

CREATE INDEX IF NOT EXISTS "equilibrium_space_solute_mass_idx"
  ON "equilibrium_space" ("solute_mass");

CREATE INDEX IF NOT EXISTS "equilibrium_space_reactant_mass_reacted_idx"
  ON "equilibrium_space" ("reactant_mass_reacted");

CREATE INDEX IF NOT EXISTS "equilibrium_space_reactant_mass_remaining_idx"
  ON "equilibrium_space" ("reactant_mass_remaining");

-- ES-side leaf tables: (equilibrium_space_id, name) composites.
CREATE INDEX IF NOT EXISTS "equilibrium_elements_equilibrium_space_id_name_idx"
  ON "equilibrium_elements" ("equilibrium_space_id", "name");

CREATE INDEX IF NOT EXISTS "equilibrium_aqueous_species_equilibrium_space_id_name_idx"
  ON "equilibrium_aqueous_species" ("equilibrium_space_id", "name");

CREATE INDEX IF NOT EXISTS "equilibrium_pure_solids_equilibrium_space_id_name_idx"
  ON "equilibrium_pure_solids" ("equilibrium_space_id", "name");

CREATE INDEX IF NOT EXISTS "equilibrium_solid_solutions_equilibrium_space_id_name_idx"
  ON "equilibrium_solid_solutions" ("equilibrium_space_id", "name");

CREATE INDEX IF NOT EXISTS "equilibrium_end_members_equilibrium_solid_solution_id_name_idx"
  ON "equilibrium_end_members" ("equilibrium_solid_solution_id", "name");

CREATE INDEX IF NOT EXISTS "equilibrium_gases_equilibrium_space_id_name_idx"
  ON "equilibrium_gases" ("equilibrium_space_id", "name");

CREATE INDEX IF NOT EXISTS "equilibrium_reactants_equilibrium_space_id_name_idx"
  ON "equilibrium_reactants" ("equilibrium_space_id", "name");

CREATE INDEX IF NOT EXISTS "equilibrium_redox_reactions_equilibrium_space_id_couple_idx"
  ON "equilibrium_redox_reactions" ("equilibrium_space_id", "couple");

-- Partial indexes for tables where log_moles defaults to -Infinity.  These
-- index only the rows where the mineral actually precipitated (log_moles is
-- finite), keeping the index small and making "mineral present" joins fast.
CREATE INDEX IF NOT EXISTS "equilibrium_pure_solids_log_moles_present_idx"
  ON "equilibrium_pure_solids" ("equilibrium_space_id")
  WHERE "log_moles" > '-Infinity'::double precision;

CREATE INDEX IF NOT EXISTS "equilibrium_solid_solutions_log_moles_present_idx"
  ON "equilibrium_solid_solutions" ("equilibrium_space_id")
  WHERE "log_moles" > '-Infinity'::double precision;

CREATE INDEX IF NOT EXISTS "equilibrium_end_members_log_moles_present_idx"
  ON "equilibrium_end_members" ("equilibrium_solid_solution_id")
  WHERE "log_moles" > '-Infinity'::double precision;

-- equilibrium_elements: elemental quantities
CREATE INDEX IF NOT EXISTS "equilibrium_elements_log_molality_idx"
  ON "equilibrium_elements" ("log_molality");

-- equilibrium_aqueous_species: per-species quantities
CREATE INDEX IF NOT EXISTS "equilibrium_aqueous_species_log_molality_idx"
  ON "equilibrium_aqueous_species" ("log_molality");

CREATE INDEX IF NOT EXISTS "equilibrium_aqueous_species_log_activity_idx"
  ON "equilibrium_aqueous_species" ("log_activity");

-- equilibrium_pure_solids: saturation quantities
CREATE INDEX IF NOT EXISTS "equilibrium_pure_solids_affinity_idx"
  ON "equilibrium_pure_solids" ("affinity");

CREATE INDEX IF NOT EXISTS "equilibrium_pure_solids_log_qk_idx"
  ON "equilibrium_pure_solids" ("log_qk");

-- equilibrium_solid_solutions: saturation quantities
CREATE INDEX IF NOT EXISTS "equilibrium_solid_solutions_affinity_idx"
  ON "equilibrium_solid_solutions" ("affinity");

CREATE INDEX IF NOT EXISTS "equilibrium_solid_solutions_log_qk_idx"
  ON "equilibrium_solid_solutions" ("log_qk");

-- equilibrium_end_members: saturation quantities
CREATE INDEX IF NOT EXISTS "equilibrium_end_members_affinity_idx"
  ON "equilibrium_end_members" ("affinity");

CREATE INDEX IF NOT EXISTS "equilibrium_end_members_log_qk_idx"
  ON "equilibrium_end_members" ("log_qk");

-- equilibrium_gases: fugacity
CREATE INDEX IF NOT EXISTS "equilibrium_gases_log_fugacity_idx"
  ON "equilibrium_gases" ("log_fugacity");

-- equilibrium_reactants: reaction progress quantities
CREATE INDEX IF NOT EXISTS "equilibrium_reactants_affinity_idx"
  ON "equilibrium_reactants" ("affinity");

CREATE INDEX IF NOT EXISTS "equilibrium_reactants_log_moles_reacted_idx"
  ON "equilibrium_reactants" ("log_moles_reacted");

CREATE INDEX IF NOT EXISTS "equilibrium_reactants_log_moles_remaining_idx"
  ON "equilibrium_reactants" ("log_moles_remaining");

CREATE INDEX IF NOT EXISTS "equilibrium_reactants_log_mass_reacted_idx"
  ON "equilibrium_reactants" ("log_mass_reacted");

CREATE INDEX IF NOT EXISTS "equilibrium_reactants_log_mass_remaining_idx"
  ON "equilibrium_reactants" ("log_mass_remaining");

-- equilibrium_redox_reactions: per-couple redox quantities
CREATE INDEX IF NOT EXISTS "equilibrium_redox_reactions_eh_idx"
  ON "equilibrium_redox_reactions" ("Eh");

CREATE INDEX IF NOT EXISTS "equilibrium_redox_reactions_log_fo2_idx"
  ON "equilibrium_redox_reactions" ("log_fO2");
