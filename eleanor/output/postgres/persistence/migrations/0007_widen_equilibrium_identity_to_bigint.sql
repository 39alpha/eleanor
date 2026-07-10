ALTER TABLE "equilibrium_space"
  ALTER COLUMN "id" TYPE BIGINT;

ALTER TABLE "equilibrium_elements"
  ALTER COLUMN "id" TYPE BIGINT,
  ALTER COLUMN "equilibrium_space_id" TYPE BIGINT;

ALTER TABLE "equilibrium_aqueous_species"
  ALTER COLUMN "id" TYPE BIGINT,
  ALTER COLUMN "equilibrium_space_id" TYPE BIGINT;

ALTER TABLE "equilibrium_pure_solids"
  ALTER COLUMN "id" TYPE BIGINT,
  ALTER COLUMN "equilibrium_space_id" TYPE BIGINT;

ALTER TABLE "equilibrium_solid_solutions"
  ALTER COLUMN "id" TYPE BIGINT,
  ALTER COLUMN "equilibrium_space_id" TYPE BIGINT;

ALTER TABLE "equilibrium_end_members"
  ALTER COLUMN "id" TYPE BIGINT,
  ALTER COLUMN "equilibrium_solid_solution_id" TYPE BIGINT;

ALTER TABLE "equilibrium_gases"
  ALTER COLUMN "id" TYPE BIGINT,
  ALTER COLUMN "equilibrium_space_id" TYPE BIGINT;

ALTER TABLE "equilibrium_reactants"
  ALTER COLUMN "id" TYPE BIGINT,
  ALTER COLUMN "equilibrium_space_id" TYPE BIGINT;

ALTER TABLE "equilibrium_redox_reactions"
  ALTER COLUMN "id" TYPE BIGINT,
  ALTER COLUMN "equilibrium_space_id" TYPE BIGINT;
