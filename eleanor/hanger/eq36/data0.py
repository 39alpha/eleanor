import functools
import numpy as np

Integer = int | np.int64
Float = float | np.float64
Number = int | np.int64 | float | np.float64

class ModelParams(object):
    def __init__(self, debye_huckel_a: np.ndarray):
        self.debye_huckel_a = debye_huckel_a

class DebyeHuckelModelParams(ModelParams):
    def __init__(self,
                 debye_huckel_a: np.ndarray,
                 debye_huckel_b: np.ndarray,
                 bdot: np.ndarray,
                 cco2: np.ndarray,):

        super().__init__(debye_huckel_a)
        self.debye_huckel_b = debye_huckel_b
        self.bdot = bdot
        self.cco2 = cco2

class PitzerModelParams(ModelParams):
    def __init__(self, debye_huckel_a: np.ndarray):
        super().__init__(debye_huckel_a)

class Params(object):
    def __init__(self,
                 temperatures: np.ndarray,
                 pressures: np.ndarray,
                 debye_huckel: DebyeHuckelModelParams | None,
                 pitzer: PitzerModelParams | None,
                 ehlogk: np.ndarray):

        self.temperatures = temperatures
        self.pressures = pressures
        self.debye_huckel = debye_huckel
        self.pitzer = pitzer
        self.ehlogk = ehlogk

class BDotSpecies(object):
    def __init__(self, name: str, azer0: Float, neutral_ion_type: Integer):
        self.name = name
        self.azer0 = azer0
        self.neutral_ion_type = neutral_ion_type

class Dissociation(object):
    def __init__(self, substrates: dict[str, Integer], products: dict[str, Integer]):
        self.substrates = substrates
        self.products = products

    def __repr__(self) -> str:
        return f'Dissociation(substrates={repr(self.substrates)}, products={repr(self.products)})'

    def __str__(self) -> str:
        substrates = ' + '.join(f'{count} {name}' for name, count in self.substrates.items())
        products = ' + '.join(f'{count} {name}' for name, count in self.products.items())
        return f'{substrates} ⇌ {products}'

class Volume(object):
    def __init__(self, value: Number, unit: str):
        self.value = value
        self.unit = unit

    def __repr__(self) -> str:
        return f"Volume(value={repr(self.value)}, unit={repr(self.unit)})"

    def __str__(self) -> str:
        return f'{self.value}{self.unit}'

class Species(object):
    def __init__(self,
                 name: str,
                 note: str | None,
                 revised: str | None,
                 species_type: str | None,
                 keys: str | None,
                 composition: dict[str,Integer]):
        self.name = name
        self.note = note
        self.revised = revised
        self.species_type = species_type
        self.keys = keys
        self.composition = composition

    @property
    def elements(self) -> set[str]:
        return set(self.composition.keys())

class BasicSpecies(Species):
    def __init__(self,
                 name: str,
                 note: str | None,
                 revised: str | None,
                 species_type: str | None,
                 keys: str | None,
                 composition: dict[str, Integer],
                 charge: Integer,
                 volume: Volume | None = None):

        super().__init__(name, note, revised, species_type, keys, composition)
        self.charge = charge
        self.volume = volume

class ComplexSpecies(BasicSpecies):
    def __init__(self,
                 name: str,
                 note: str | None,
                 revised: str | None,
                 species_type: str | None,
                 keys: str | None,
                 composition: dict[str, Integer],
                 dissociation: Dissociation,
                 logk: np.ndarray,
                 charge: Integer,
                 volume: Volume | None = None):

        super().__init__(name, note, revised, species_type, keys, composition, charge, volume)
        self.dissociation = dissociation
        self.logk = logk

class BasisSpecies(BasicSpecies):
    def __repr__(self) -> str:
        name = f'name={repr(self.name)}'
        note = f'note={repr(self.note)}'
        revised = f'revised={repr(self.revised)}'
        species_type = f'species_type={repr(self.species_type)}'
        keys = f'keys={repr(self.keys)}'
        charge = f'charge={repr(self.charge)}'
        volume = f'volume={repr(self.volume)}'
        composition = f'composition={repr(self.composition)}'
        return f'BasisSpecies({name}, {note}, {revised}, {species_type}, {keys}, {composition}, {charge}, {volume})'

    def __str__(self) -> str:
        return f'<BasisSpecies {self.name}>'

class AuxiliaryBasisSpecies(ComplexSpecies):
    def __repr__(self) -> str:
        name = f'name={repr(self.name)}'
        note = f'note={repr(self.note)}'
        revised = f'revised={repr(self.revised)}'
        species_type = f'species_type={repr(self.species_type)}'
        keys = f'keys={repr(self.keys)}'
        charge = f'charge={repr(self.charge)}'
        volume = f'volume={repr(self.volume)}'
        composition = f'composition={repr(self.composition)}'
        dissociation = f'dissociation={repr(self.dissociation)}'
        logk = f'logk={repr(self.logk)}'
        return f'AuxiliaryBasisSpecies({name}, {note}, {revised}, {species_type}, {keys}, {composition}, {dissociation}, {logk}, {charge}, {volume})'

    def __str__(self) -> str:
        return f'<AuxiliaryBasisSpecies {self.name}>'

class AqueousSpecies(ComplexSpecies):
    def __repr__(self) -> str:
        name = f'name={repr(self.name)}'
        note = f'note={repr(self.note)}'
        revised = f'revised={repr(self.revised)}'
        species_type = f'species_type={repr(self.species_type)}'
        keys = f'keys={repr(self.keys)}'
        charge = f'charge={repr(self.charge)}'
        volume = f'volume={repr(self.volume)}'
        composition = f'composition={repr(self.composition)}'
        dissociation = f'dissociation={repr(self.dissociation)}'
        logk = f'logk={repr(self.logk)}'
        return f'AqueousSpecies({name}, {note}, {revised}, {species_type}, {keys}, {composition}, {dissociation}, {logk}, {charge}, {volume})'

    def __str__(self) -> str:
        return f'<AqueousSpecies {self.name}>'

class Solid(ComplexSpecies):
    def __repr__(self) -> str:
        name = f'name={repr(self.name)}'
        note = f'note={repr(self.note)}'
        revised = f'revised={repr(self.revised)}'
        species_type = f'species_type={repr(self.species_type)}'
        keys = f'keys={repr(self.keys)}'
        charge = f'charge={repr(self.charge)}'
        volume = f'volume={repr(self.volume)}'
        composition = f'composition={repr(self.composition)}'
        dissociation = f'dissociation={repr(self.dissociation)}'
        logk = f'logk={repr(self.logk)}'
        return f'Solid({name}, {note}, {revised}, {species_type}, {keys}, {composition}, {dissociation}, {logk}, {charge}, {volume})'

    def __str__(self) -> str:
        return f'<Solid {self.name}>'

class Liquid(ComplexSpecies):
    def __repr__(self) -> str:
        name = f'name={repr(self.name)}'
        note = f'note={repr(self.note)}'
        revised = f'revised={repr(self.revised)}'
        species_type = f'species_type={repr(self.species_type)}'
        keys = f'keys={repr(self.keys)}'
        charge = f'charge={repr(self.charge)}'
        volume = f'volume={repr(self.volume)}'
        composition = f'composition={repr(self.composition)}'
        dissociation = f'dissociation={repr(self.dissociation)}'
        logk = f'logk={repr(self.logk)}'
        return f'Liquid({name}, {note}, {revised}, {species_type}, {keys}, {composition}, {dissociation}, {logk}, {charge}, {volume})'

    def __str__(self) -> str:
        return f'<Liquid {self.name}>'

class Gas(ComplexSpecies):
    def __repr__(self) -> str:
        name = f'name={repr(self.name)}'
        note = f'note={repr(self.note)}'
        revised = f'revised={repr(self.revised)}'
        species_type = f'species_type={repr(self.species_type)}'
        keys = f'keys={repr(self.keys)}'
        charge = f'charge={repr(self.charge)}'
        volume = f'volume={repr(self.volume)}'
        composition = f'composition={repr(self.composition)}'
        dissociation = f'dissociation={repr(self.dissociation)}'
        logk = f'logk={repr(self.logk)}'
        return f'Gas({name}, {note}, {revised}, {species_type}, {keys}, {composition}, {dissociation}, {logk}, {charge}, {volume})'

    def __str__(self) -> str:
        return f'<Gas {self.name}>'

class SolidSolutionModel(object):
    def __init__(self, type: Integer, params: np.ndarray):
        self.type = type
        self.params = params

    def __repr__(self) -> str:
        return f'SolidSolutionModel(type={repr(self.type)}, params={repr(self.params)})'

    def __str__(self) -> str:
        return f'<SolidSolutionModel {self.type} {self.params}>'

class SolidSolution(Species):
    def __init__(self,
                 name: str,
                 note: str | None,
                 revised: str | None,
                 species_type: str | None,
                 keys: str | None,
                 composition: dict[str, Integer],
                 model: SolidSolutionModel,
                 site_params: np.ndarray):

        super().__init__(name, note, revised, species_type, keys, composition)
        self.model = model
        self.site_params = site_params

    def __repr__(self) -> str:
        name = f'name={repr(self.name)}'
        note = f'note={repr(self.note)}'
        revised = f'revised={repr(self.revised)}'
        species_type = f'species_type={repr(self.species_type)}'
        keys = f'keys={repr(self.keys)}'
        composition = f'composition={repr(self.composition)}'
        model = f'model={repr(self.model)}'
        site_params = f'site_params={repr(self.site_params)}'
        return f'SolidSolutionModel({name}, {note}, {revised}, {species_type}, {keys}, {composition}, {model}, {site_params})'

    def __str__(self) -> str:
        return f'<SolidSolution {self.name}>'

class ModelSection(object):
    pass

class BdotSpeciesSection(ModelSection):
    def __init__(self, species: dict[str, BDotSpecies]):
        self.species = species

# pitzerAlphaBetaCphiParams : pitzerTuple alpha1 alpha2 beta0 beta1 beta2 cphi seperator;
# pitzerLambdaMuParams : pitzerTuple lambda mu seperator;
# pitzerLambdaParams : pitzerTuple lambda seperator;
# pitzerMuParams : pitzerTuple mu seperator;
# pitzerPsiParams : pitzerTuple psi seperator;
# pitzerThetaParams : pitzerTuple theta seperator;
# pitzerZetaParams : pitzerTuple zeta seperator;

class PitzerTerm(object):
    pass

class PitzerABCTerm(PitzerTerm):
    def __init__(self,
                 alpha1: float,
                 alpha2: float,
                 beta0: np.ndarray,
                 beta1: np.ndarray,
                 beta2: np.ndarray,
                 cphi: np.ndarray):
        self.alpha1 = alpha1
        self.alpha2 = alpha2
        self.beta0 = beta0
        self.beta1 = beta1
        self.beta2 = beta2
        self.cphi = cphi

class PitzerThetaTerm(PitzerTerm):
    def __init__(self, theta: np.ndarray):
        self.theta = theta

class PitzerLambdaTerm(PitzerTerm):
    def __init__(self, lam: np.ndarray):
        self.lam = lam

class PitzerLambdaMuTerm(PitzerTerm):
    def __init__(self, lam: np.ndarray, mu: np.ndarray):
        self.lam = lam
        self.mu = mu

class PitzerPsiTerm(PitzerTerm):
    def __init__(self, psi: np.ndarray):
        self.psi = psi

class PitzerZetaTerm(PitzerTerm):
    def __init__(self, zeta: np.ndarray):
        self.zeta = zeta

class PitzerMuTerm(PitzerTerm):
    def __init__(self, mu: np.ndarray):
        self.mu = mu

class PitzerCombinations(ModelSection):
    def __init__(self,
                 ca: dict[tuple, PitzerABCTerm],
                 ccp_aap: dict[tuple, PitzerThetaTerm],
                 nc_na: dict[tuple, PitzerLambdaTerm],
                 nn: dict[tuple, PitzerLambdaMuTerm],
                 nnp: dict[tuple, PitzerLambdaTerm],
                 ccpa_aapc: dict[tuple, PitzerPsiTerm],
                 nca: dict[tuple, PitzerZetaTerm],
                 nnnp: dict[tuple, PitzerMuTerm]):

        self.ca = ca
        self.ccp_aap = ccp_aap
        self.nc_na = nc_na
        self.nn = nn
        self.nnp = nnp
        self.ccpa_aapc = ccpa_aapc
        self.nca = nca
        self.nnnp = nnnp

class Data0(object):
    @staticmethod
    def from_file(fname, *args, **kwargs):
        from . parsers import parse_data0
        data0, _ = parse_data0(fname, *args, **kwargs)
        return data0

    def __init__(self,
                 magic: str,
                 header: str,
                 params: Params,
                 bdot: dict[str, BDotSpecies],
                 pitzer_combinations: PitzerCombinations,
                 elements: dict[str, Float],
                 basis_species: dict[str, BasisSpecies],
                 auxiliary_basis_species: dict[str, AuxiliaryBasisSpecies],
                 aqueous_species: dict[str, AqueousSpecies],
                 solids: dict[str, Solid],
                 liquids: dict[str, Liquid],
                 gases: dict[str, Gas],
                 solid_solutions: dict[str, SolidSolution],
                 references: str,
                 fname: str | None = None):

        self.fname = fname
        self.magic = magic
        self.header = header
        self.params = params
        self.bdot = bdot
        self.pitzer_combinations = pitzer_combinations
        self.elements = elements
        self.basis_species = basis_species
        self.auxiliary_basis_species = auxiliary_basis_species
        self.aqueous_species = aqueous_species
        self.solids = solids
        self.liquids = liquids
        self.gases = gases
        self.solid_solutions = solid_solutions
        self.references = references

        self.__species_names: set[str] | None = None
        self.__used_elements: set[str] | None = None

    def __getitem__(self, species_name):
        if species_name in self.basis_species:
            return self.basis_species[species_name]
        elif species_name in self.auxiliary_basis_species:
            return self.auxiliary_basis_species[species_name]
        elif species_name in self.aqueous_species:
            return self.aqueous_species[species_name]
        elif species_name in self.solids:
            return self.solids[species_name]
        elif species_name in self.liquids:
            return self.liquids[species_name]
        elif species_name in self.gases:
            return self.gases[species_name]
        elif species_name in self.solid_solutions:
            return self.solid_solutions[species_name]
        else:
            raise KeyError(species_name)

    @property
    def species_names(self) -> set[str]:
        if self.__species_names is None:
            self.__species_names = set(self.elements.keys())
            self.__species_names.update(self.basis_species.keys())
            self.__species_names.update(self.auxiliary_basis_species.keys())
            self.__species_names.update(self.aqueous_species.keys())
            self.__species_names.update(self.solids.keys())
            self.__species_names.update(self.liquids.keys())
            self.__species_names.update(self.gases.keys())
            self.__species_names.update(self.solid_solutions.keys())

        return self.__species_names

    @property
    def used_elements(self) -> set[str]:
        if self.__used_elements is None:
            def union(acc: set[str], x: Species) -> set[str]:
                acc.update(x.elements)
                return acc

            self.__used_elements = set[str]()
            functools.reduce(union, self.basis_species.values(), self.__used_elements)
            functools.reduce(union, self.auxiliary_basis_species.values(), self.__used_elements)
            functools.reduce(union, self.aqueous_species.values(), self.__used_elements)
            functools.reduce(union, self.solids.values(), self.__used_elements)
            functools.reduce(union, self.liquids.values(), self.__used_elements)
            functools.reduce(union, self.gases.values(), self.__used_elements)

        return self.__used_elements


    def verify(self):
        self.__verify_params()

        self.__verify_basic_species(self.basis_species)
        self.__verify_complex_species(self.auxiliary_basis_species)
        self.__verify_complex_species(self.aqueous_species)
        self.__verify_complex_species(self.solids)
        self.__verify_complex_species(self.liquids)
        self.__verify_complex_species(self.gases)
        self.__verify_solid_solutions(self.solid_solutions)

    def __verify_params(self):
        num_grid_points = len(self.params.temperatures)

        n = len(self.params.pressures)
        if n != num_grid_points:
            raise Exception(f'number of pressures in params section ({n}) differs from the number of temperatures ({num_grid_points})')

        n = len(self.params.ehlogk)
        if n != num_grid_points:
            raise Exception(f'number of ehlogk values in params section ({n}) differs from the number of temperatures ({num_grid_points})')

    def __verify_basic_species(self, species):
        for s in species.values():
            for element in s.composition.keys():
                if element not in self.elements:
                    raise Exception(f'{species} has an element {element} that does not appear in the data0 element list')

    def __verify_complex_species(self, species):
        self.__verify_basic_species(species)

        for s in species.values():
            for substrate in s.dissociation.substrates.keys():
                if substrate not in self.species_names:
                    raise Exception(f'{species} has a substrate ({substrate}) in its dissocation reaction ({species.dissociation}) that does not appear in the elements or any species sections')

            for product in s.dissociation.products.keys():
                if product not in self.species_names:
                    raise Exception(f'{species} has a product ({product}) in its dissocation reaction ({species.dissociation}) that does not appear in the elements or any species sections')

            if len(s.logk) != len(self.params.temperatures):
                raise Exception(f'{species} has a different number of log(K) values than the number of values in the data0 temperature grid')

    def __verify_solid_solutions(self, solid_solutions):
        for solid_solution in solid_solutions.values():
            for solid in solid_solution.composition.keys():
                if solid not in self.solids:
                    raise Exception(f'{solid_solutions} has an solid ({solid}) that does not appear in the data0 solids section')
