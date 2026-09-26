CREATE FUNCTION pg17_uuidv7(ts timestamp) RETURNS uuid AS $$
  SELECT encode(
    set_bit(
      set_bit(
        overlay(uuid_send(gen_random_uuid())
                placing substring(int8send((extract(epoch from ts) * 1000)::bigint) from 3)
                from 1 for 6),
        52, 1),
      53, 1),
    'hex')::uuid
$$ LANGUAGE sql VOLATILE;

-- Orders

ALTER TABLE orders ADD COLUMN uuid UUID;
UPDATE orders SET uuid = pg17_uuidv7(create_date);

ALTER TABLE variable_space ADD COLUMN order_uuid UUID;
UPDATE variable_space
    SET order_uuid = orders.uuid
    FROM orders
    WHERE variable_space.order_id = orders.id;
ALTER TABLE variable_space DROP COLUMN order_id;
ALTER TABLE variable_space RENAME order_uuid TO order_id;
ALTER TABLE variable_space ALTER COLUMN order_id SET NOT NULL;

ALTER TABLE orders DROP COLUMN id;
ALTER TABLE orders RENAME COLUMN uuid TO id;
ALTER TABLE orders ALTER COLUMN id SET NOT NULL;
ALTER TABLE orders ADD PRIMARY KEY (id);

ALTER TABLE variable_space ADD FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS variable_space_order_id_exit_code_idx ON variable_space (order_id, exit_code);

-- Variable Space

ALTER TABLE variable_space ADD COLUMN uuid UUID;
UPDATE variable_space SET uuid = pg17_uuidv7(create_date);

ALTER TABLE kernel ADD COLUMN uuid UUID;
UPDATE kernel
    SET uuid = variable_space.uuid
    FROM variable_space
    WHERE kernel.id = variable_space.id;
ALTER TABLE kernel DROP COLUMN id;
ALTER TABLE kernel RENAME uuid TO id;
ALTER TABLE kernel ALTER COLUMN id SET NOT NULL;

ALTER TABLE scratch ADD COLUMN uuid UUID;
UPDATE scratch
    SET uuid = variable_space.uuid
    FROM variable_space
    WHERE scratch.id = variable_space.id;
ALTER TABLE scratch DROP COLUMN id;
ALTER TABLE scratch RENAME uuid TO id;
ALTER TABLE scratch ALTER COLUMN id SET NOT NULL;

ALTER TABLE elements ADD COLUMN variable_space_uuid UUID;
ALTER TABLE elements DROP COLUMN id;
UPDATE elements
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE elements.variable_space_id = variable_space.id;
ALTER TABLE elements DROP COLUMN variable_space_id;
ALTER TABLE elements RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE elements ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE species ADD COLUMN variable_space_uuid UUID;
ALTER TABLE species DROP COLUMN id;
UPDATE species
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE species.variable_space_id = variable_space.id;
ALTER TABLE species DROP COLUMN variable_space_id;
ALTER TABLE species RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE species ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE suppressions ADD COLUMN variable_space_uuid UUID;
UPDATE suppressions
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE suppressions.variable_space_id = variable_space.id;
ALTER TABLE suppressions DROP COLUMN variable_space_id;
ALTER TABLE suppressions RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE suppressions ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE mineral_reactants ADD COLUMN variable_space_uuid UUID;
ALTER TABLE mineral_reactants DROP COLUMN id;
UPDATE mineral_reactants
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE mineral_reactants.variable_space_id = variable_space.id;
ALTER TABLE mineral_reactants DROP COLUMN variable_space_id;
ALTER TABLE mineral_reactants RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE mineral_reactants ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE aqueous_reactants ADD COLUMN variable_space_uuid UUID;
ALTER TABLE aqueous_reactants DROP COLUMN id;
UPDATE aqueous_reactants
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE aqueous_reactants.variable_space_id = variable_space.id;
ALTER TABLE aqueous_reactants DROP COLUMN variable_space_id;
ALTER TABLE aqueous_reactants RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE aqueous_reactants ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE gas_reactants ADD COLUMN variable_space_uuid UUID;
ALTER TABLE gas_reactants DROP COLUMN id;
UPDATE gas_reactants
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE gas_reactants.variable_space_id = variable_space.id;
ALTER TABLE gas_reactants DROP COLUMN variable_space_id;
ALTER TABLE gas_reactants RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE gas_reactants ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE element_reactants ADD COLUMN variable_space_uuid UUID;
ALTER TABLE element_reactants DROP COLUMN id;
UPDATE element_reactants
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE element_reactants.variable_space_id = variable_space.id;
ALTER TABLE element_reactants DROP COLUMN variable_space_id;
ALTER TABLE element_reactants RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE element_reactants ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE special_reactants ADD COLUMN variable_space_uuid UUID;
UPDATE special_reactants
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE special_reactants.variable_space_id = variable_space.id;
ALTER TABLE special_reactants DROP COLUMN variable_space_id;
ALTER TABLE special_reactants RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE special_reactants ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE fixed_gas_reactants ADD COLUMN variable_space_uuid UUID;
ALTER TABLE fixed_gas_reactants DROP COLUMN id;
UPDATE fixed_gas_reactants
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE fixed_gas_reactants.variable_space_id = variable_space.id;
ALTER TABLE fixed_gas_reactants DROP COLUMN variable_space_id;
ALTER TABLE fixed_gas_reactants RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE fixed_gas_reactants ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE solid_solution_reactants ADD COLUMN variable_space_uuid UUID;
UPDATE solid_solution_reactants
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE solid_solution_reactants.variable_space_id = variable_space.id;
ALTER TABLE solid_solution_reactants DROP COLUMN variable_space_id;
ALTER TABLE solid_solution_reactants RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE solid_solution_reactants ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE equilibrium_space ADD COLUMN variable_space_uuid UUID;
UPDATE equilibrium_space
    SET variable_space_uuid = variable_space.uuid
    FROM variable_space
    WHERE equilibrium_space.variable_space_id = variable_space.id;
ALTER TABLE equilibrium_space DROP COLUMN variable_space_id;
ALTER TABLE equilibrium_space RENAME variable_space_uuid TO variable_space_id;
ALTER TABLE equilibrium_space ALTER COLUMN variable_space_id SET NOT NULL;

ALTER TABLE variable_space DROP COLUMN id;
ALTER TABLE variable_space RENAME COLUMN uuid TO id;
ALTER TABLE variable_space ALTER COLUMN id SET NOT NULL;
ALTER TABLE variable_space ADD PRIMARY KEY (id);

ALTER TABLE kernel ADD PRIMARY KEY (id);
ALTER TABLE kernel ADD FOREIGN KEY (id) REFERENCES variable_space (id) ON DELETE CASCADE;

ALTER TABLE scratch ADD PRIMARY KEY (id);
ALTER TABLE scratch ADD FOREIGN KEY (id) REFERENCES variable_space (id) ON DELETE CASCADE;

ALTER TABLE suppressions ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE elements ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE species ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE mineral_reactants ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE aqueous_reactants ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE gas_reactants ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE element_reactants ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE special_reactants ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE fixed_gas_reactants ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE solid_solution_reactants ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;
ALTER TABLE equilibrium_space ADD FOREIGN KEY (variable_space_id) REFERENCES variable_space (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS suppressions_variable_space_id_idx ON suppressions (variable_space_id);
CREATE INDEX IF NOT EXISTS elements_variable_space_id_name_idx ON elements (variable_space_id, name);
CREATE INDEX IF NOT EXISTS species_variable_space_id_name_idx ON species (variable_space_id, name);
CREATE INDEX IF NOT EXISTS mineral_reactants_variable_space_id_name_idx ON mineral_reactants (variable_space_id, name);
CREATE INDEX IF NOT EXISTS aqueous_reactants_variable_space_id_name_idx ON aqueous_reactants (variable_space_id, name);
CREATE INDEX IF NOT EXISTS gas_reactants_variable_space_id_name_idx ON gas_reactants (variable_space_id, name);
CREATE INDEX IF NOT EXISTS element_reactants_variable_space_id_name_idx ON element_reactants (variable_space_id, name);
CREATE INDEX IF NOT EXISTS special_reactants_variable_space_id_name_idx ON special_reactants (variable_space_id, name);
CREATE INDEX IF NOT EXISTS fixed_gas_reactants_variable_space_id_name_idx ON fixed_gas_reactants (variable_space_id, name);
CREATE INDEX IF NOT EXISTS solid_solution_reactants_variable_space_id_name_idx ON solid_solution_reactants (variable_space_id, name);
CREATE INDEX IF NOT EXISTS equilibrium_space_variable_space_id_stage_idx ON equilibrium_space (variable_space_id, stage);
CREATE INDEX IF NOT EXISTS equilibrium_space_stage_variable_space_id_idx ON equilibrium_space (stage, variable_space_id);

-- Suppressions

ALTER TABLE suppressions ADD COLUMN uuid UUID;
UPDATE suppressions
    SET uuid = pg17_uuidv7(variable_space.create_date)
    FROM variable_space
    WHERE suppressions.variable_space_id = variable_space.id;

ALTER TABLE suppression_exceptions ADD COLUMN suppression_uuid UUID;
ALTER TABLE suppression_exceptions DROP COLUMN id;
UPDATE suppression_exceptions
    SET suppression_uuid = suppressions.uuid
    FROM suppressions
    WHERE suppression_exceptions.suppression_id = suppressions.id;
ALTER TABLE suppression_exceptions DROP COLUMN suppression_id;
ALTER TABLE suppression_exceptions RENAME suppression_uuid TO suppression_id;
ALTER TABLE suppression_exceptions ALTER COLUMN suppression_id SET NOT NULL;

ALTER TABLE suppressions DROP COLUMN id;
ALTER TABLE suppressions RENAME COLUMN uuid TO id;
ALTER TABLE suppressions ALTER COLUMN id SET NOT NULL;
ALTER TABLE suppressions ADD PRIMARY KEY (id);

ALTER TABLE suppression_exceptions ADD FOREIGN KEY (suppression_id) REFERENCES suppressions (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS suppression_exceptions_suppression_id_idx ON suppression_exceptions (suppression_id);

-- Special Reactants

ALTER TABLE special_reactants ADD COLUMN uuid UUID;
UPDATE special_reactants
    SET uuid = pg17_uuidv7(variable_space.create_date)
    FROM variable_space
    WHERE special_reactants.variable_space_id = variable_space.id;

ALTER TABLE special_reactant_compositions ADD COLUMN special_reactant_uuid UUID;
ALTER TABLE special_reactant_compositions DROP COLUMN id;
UPDATE special_reactant_compositions
    SET special_reactant_uuid = special_reactants.uuid
    FROM special_reactants
    WHERE special_reactant_compositions.special_reactant_id = special_reactants.id;
ALTER TABLE special_reactant_compositions DROP COLUMN special_reactant_id;
ALTER TABLE special_reactant_compositions RENAME special_reactant_uuid TO special_reactant_id;
ALTER TABLE special_reactant_compositions ALTER COLUMN special_reactant_id SET NOT NULL;

ALTER TABLE special_reactants DROP COLUMN id;
ALTER TABLE special_reactants RENAME COLUMN uuid TO id;
ALTER TABLE special_reactants ALTER COLUMN id SET NOT NULL;
ALTER TABLE special_reactants ADD PRIMARY KEY (id);

ALTER TABLE special_reactant_compositions ADD FOREIGN KEY (special_reactant_id) REFERENCES special_reactants (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS special_reactant_compositions_special_reactant_id_element_idx ON special_reactant_compositions (special_reactant_id, element);

-- Solid Solution Reactants

ALTER TABLE solid_solution_reactants ADD COLUMN uuid UUID;
UPDATE solid_solution_reactants
    SET uuid = pg17_uuidv7(variable_space.create_date)
    FROM variable_space
    WHERE solid_solution_reactants.variable_space_id = variable_space.id;

ALTER TABLE solid_solution_reactant_end_members ADD COLUMN solid_solution_reactant_uuid UUID;
ALTER TABLE solid_solution_reactant_end_members DROP COLUMN id;
UPDATE solid_solution_reactant_end_members
    SET solid_solution_reactant_uuid = solid_solution_reactants.uuid
    FROM solid_solution_reactants
    WHERE solid_solution_reactant_end_members.solid_solution_reactant_id = solid_solution_reactants.id;
ALTER TABLE solid_solution_reactant_end_members DROP COLUMN solid_solution_reactant_id;
ALTER TABLE solid_solution_reactant_end_members RENAME solid_solution_reactant_uuid TO solid_solution_reactant_id;
ALTER TABLE solid_solution_reactant_end_members ALTER COLUMN solid_solution_reactant_id SET NOT NULL;

ALTER TABLE solid_solution_reactants DROP COLUMN id;
ALTER TABLE solid_solution_reactants RENAME COLUMN uuid TO id;
ALTER TABLE solid_solution_reactants ALTER COLUMN id SET NOT NULL;
ALTER TABLE solid_solution_reactants ADD PRIMARY KEY (id);

ALTER TABLE solid_solution_reactant_end_members ADD FOREIGN KEY (solid_solution_reactant_id) REFERENCES solid_solution_reactants (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS solid_solution_reactant_end_members_ssr_id_name_idx ON solid_solution_reactant_end_members (solid_solution_reactant_id, name);

-- Equilibrium Space

ALTER TABLE equilibrium_space ADD COLUMN uuid UUID;
UPDATE equilibrium_space SET uuid = pg17_uuidv7(start_date);

ALTER TABLE equilibrium_elements ADD COLUMN equilibrium_space_uuid UUID;
ALTER TABLE equilibrium_elements DROP COLUMN id;
UPDATE equilibrium_elements
    SET equilibrium_space_uuid = equilibrium_space.uuid
    FROM equilibrium_space
    WHERE equilibrium_elements.equilibrium_space_id = equilibrium_space.id;
ALTER TABLE equilibrium_elements DROP COLUMN equilibrium_space_id;
ALTER TABLE equilibrium_elements RENAME equilibrium_space_uuid TO equilibrium_space_id;
ALTER TABLE equilibrium_elements ALTER COLUMN equilibrium_space_id SET NOT NULL;

ALTER TABLE equilibrium_aqueous_species ADD COLUMN equilibrium_space_uuid UUID;
ALTER TABLE equilibrium_aqueous_species DROP COLUMN id;
UPDATE equilibrium_aqueous_species
    SET equilibrium_space_uuid = equilibrium_space.uuid
    FROM equilibrium_space
    WHERE equilibrium_aqueous_species.equilibrium_space_id = equilibrium_space.id;
ALTER TABLE equilibrium_aqueous_species DROP COLUMN equilibrium_space_id;
ALTER TABLE equilibrium_aqueous_species RENAME equilibrium_space_uuid TO equilibrium_space_id;
ALTER TABLE equilibrium_aqueous_species ALTER COLUMN equilibrium_space_id SET NOT NULL;

ALTER TABLE equilibrium_pure_solids ADD COLUMN equilibrium_space_uuid UUID;
ALTER TABLE equilibrium_pure_solids DROP COLUMN id;
UPDATE equilibrium_pure_solids
    SET equilibrium_space_uuid = equilibrium_space.uuid
    FROM equilibrium_space
    WHERE equilibrium_pure_solids.equilibrium_space_id = equilibrium_space.id;
ALTER TABLE equilibrium_pure_solids DROP COLUMN equilibrium_space_id;
ALTER TABLE equilibrium_pure_solids RENAME equilibrium_space_uuid TO equilibrium_space_id;
ALTER TABLE equilibrium_pure_solids ALTER COLUMN equilibrium_space_id SET NOT NULL;

ALTER TABLE equilibrium_solid_solutions ADD COLUMN equilibrium_space_uuid UUID;
UPDATE equilibrium_solid_solutions
    SET equilibrium_space_uuid = equilibrium_space.uuid
    FROM equilibrium_space
    WHERE equilibrium_solid_solutions.equilibrium_space_id = equilibrium_space.id;
ALTER TABLE equilibrium_solid_solutions DROP COLUMN equilibrium_space_id;
ALTER TABLE equilibrium_solid_solutions RENAME equilibrium_space_uuid TO equilibrium_space_id;
ALTER TABLE equilibrium_solid_solutions ALTER COLUMN equilibrium_space_id SET NOT NULL;

ALTER TABLE equilibrium_gases ADD COLUMN equilibrium_space_uuid UUID;
ALTER TABLE equilibrium_gases DROP COLUMN id;
UPDATE equilibrium_gases
    SET equilibrium_space_uuid = equilibrium_space.uuid
    FROM equilibrium_space
    WHERE equilibrium_gases.equilibrium_space_id = equilibrium_space.id;
ALTER TABLE equilibrium_gases DROP COLUMN equilibrium_space_id;
ALTER TABLE equilibrium_gases RENAME equilibrium_space_uuid TO equilibrium_space_id;
ALTER TABLE equilibrium_gases ALTER COLUMN equilibrium_space_id SET NOT NULL;

ALTER TABLE equilibrium_reactants ADD COLUMN equilibrium_space_uuid UUID;
ALTER TABLE equilibrium_reactants DROP COLUMN id;
UPDATE equilibrium_reactants
    SET equilibrium_space_uuid = equilibrium_space.uuid
    FROM equilibrium_space
    WHERE equilibrium_reactants.equilibrium_space_id = equilibrium_space.id;
ALTER TABLE equilibrium_reactants DROP COLUMN equilibrium_space_id;
ALTER TABLE equilibrium_reactants RENAME equilibrium_space_uuid TO equilibrium_space_id;
ALTER TABLE equilibrium_reactants ALTER COLUMN equilibrium_space_id SET NOT NULL;

ALTER TABLE equilibrium_redox_reactions ADD COLUMN equilibrium_space_uuid UUID;
ALTER TABLE equilibrium_redox_reactions DROP COLUMN id;
UPDATE equilibrium_redox_reactions
    SET equilibrium_space_uuid = equilibrium_space.uuid
    FROM equilibrium_space
    WHERE equilibrium_redox_reactions.equilibrium_space_id = equilibrium_space.id;
ALTER TABLE equilibrium_redox_reactions DROP COLUMN equilibrium_space_id;
ALTER TABLE equilibrium_redox_reactions RENAME equilibrium_space_uuid TO equilibrium_space_id;
ALTER TABLE equilibrium_redox_reactions ALTER COLUMN equilibrium_space_id SET NOT NULL;

ALTER TABLE equilibrium_space DROP COLUMN id;
ALTER TABLE equilibrium_space RENAME COLUMN uuid TO id;
ALTER TABLE equilibrium_space ALTER COLUMN id SET NOT NULL;
ALTER TABLE equilibrium_space ADD PRIMARY KEY (id);

ALTER TABLE equilibrium_elements ADD FOREIGN KEY (equilibrium_space_id) REFERENCES equilibrium_space (id) ON DELETE CASCADE;
ALTER TABLE equilibrium_aqueous_species ADD FOREIGN KEY (equilibrium_space_id) REFERENCES equilibrium_space (id) ON DELETE CASCADE;
ALTER TABLE equilibrium_pure_solids ADD FOREIGN KEY (equilibrium_space_id) REFERENCES equilibrium_space (id) ON DELETE CASCADE;
ALTER TABLE equilibrium_solid_solutions ADD FOREIGN KEY (equilibrium_space_id) REFERENCES equilibrium_space (id) ON DELETE CASCADE;
ALTER TABLE equilibrium_gases ADD FOREIGN KEY (equilibrium_space_id) REFERENCES equilibrium_space (id) ON DELETE CASCADE;
ALTER TABLE equilibrium_reactants ADD FOREIGN KEY (equilibrium_space_id) REFERENCES equilibrium_space (id) ON DELETE CASCADE;
ALTER TABLE equilibrium_redox_reactions ADD FOREIGN KEY (equilibrium_space_id) REFERENCES equilibrium_space (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS equilibrium_aqueous_species_equilibrium_space_id_name_idx ON equilibrium_aqueous_species (equilibrium_space_id, name);

CREATE INDEX IF NOT EXISTS equilibrium_pure_solids_name_present_idx
    ON equilibrium_pure_solids (name, equilibrium_space_id)
    WHERE log_moles > '-Infinity'::double precision;
CREATE INDEX IF NOT EXISTS equilibrium_pure_solids_equilibrium_space_id_name_idx
    ON equilibrium_pure_solids (equilibrium_space_id, name)
    WHERE log_moles > '-Infinity'::double precision;

CREATE INDEX IF NOT EXISTS equilibrium_solid_solutions_name_present_idx
    ON equilibrium_solid_solutions (name, equilibrium_space_id)
    WHERE log_moles > '-Infinity'::double precision;
CREATE INDEX IF NOT EXISTS equilibrium_solid_solutions_equilibrium_space_id_name_idx
    ON equilibrium_solid_solutions (equilibrium_space_id, name)
    WHERE log_moles > '-Infinity'::double precision;

-- Solid Solutions

ALTER TABLE equilibrium_solid_solutions ADD COLUMN uuid UUID;
UPDATE equilibrium_solid_solutions
    SET uuid = pg17_uuidv7(equilibrium_space.start_date)
    FROM equilibrium_space
    WHERE equilibrium_solid_solutions.equilibrium_space_id = equilibrium_space.id;

ALTER TABLE equilibrium_end_members ADD COLUMN equilibrium_solid_solution_uuid UUID;
ALTER TABLE equilibrium_end_members DROP COLUMN id;
UPDATE equilibrium_end_members
    SET equilibrium_solid_solution_uuid = equilibrium_solid_solutions.uuid
    FROM equilibrium_solid_solutions
    WHERE equilibrium_end_members.equilibrium_solid_solution_id = equilibrium_solid_solutions.id;
ALTER TABLE equilibrium_end_members DROP COLUMN equilibrium_solid_solution_id;
ALTER TABLE equilibrium_end_members RENAME equilibrium_solid_solution_uuid TO equilibrium_solid_solution_id;
ALTER TABLE equilibrium_end_members ALTER COLUMN equilibrium_solid_solution_id SET NOT NULL;

ALTER TABLE equilibrium_solid_solutions DROP COLUMN id;
ALTER TABLE equilibrium_solid_solutions RENAME COLUMN uuid TO id;
ALTER TABLE equilibrium_solid_solutions ALTER COLUMN id SET NOT NULL;
ALTER TABLE equilibrium_solid_solutions ADD PRIMARY KEY (id);

ALTER TABLE equilibrium_end_members ADD FOREIGN KEY (equilibrium_solid_solution_id) REFERENCES equilibrium_solid_solutions (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS equilibrium_end_members_name_present_idx
    ON equilibrium_end_members (name, equilibrium_solid_solution_id)
    WHERE log_moles > '-Infinity'::double precision;
CREATE INDEX IF NOT EXISTS equilibrium_end_members_equilibrium_solid_solution_id_name_idx
    ON equilibrium_end_members (equilibrium_solid_solution_id, name)
    WHERE log_moles > '-Infinity'::double precision;

DROP FUNCTION IF EXISTS pg17_uuidv7;
