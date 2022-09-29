import numpy as np

Integer = int | np.int64
Float = float | np.float64
Number = int | np.int64 | float | np.float64

class Params(object):
    def __init__(self,
                 temperatures: np.ndarray,
                 pressures: np.ndarray,
                 debye_huckel_a: np.ndarray,
                 debye_huckel_b: np.ndarray,
                 bdot: np.ndarray,
                 cco2: np.ndarray,
                 ehlogk: np.ndarray):

        self.temperatures = temperatures
        self.pressures = pressures
        self.debye_huckel_a = debye_huckel_a
        self.debye_huckel_b = debye_huckel_b
        self.bdot = bdot
        self.cco2 = cco2
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
    def __init__(self, name: str, composition: dict[str, Integer]):
        self.name = name
        self.composition = composition

class BasicSpecies(Species):
    def __init__(self, charge: Integer, volume: Volume | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.charge = charge
        self.volume = volume

class ComplexSpecies(BasicSpecies):
    def __init__(self, dissociation: Dissociation, logk: np.ndarray, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dissociation = dissociation
        self.logk = logk

class BasisSpecies(BasicSpecies):
    def __repr__(self) -> str:
        return f'BasisSpecies(name={repr(self.name)}, charge={repr(self.charge)}, volume={repr(self.volume)}, composition={repr(self.composition)})'

    def __str__(self) -> str:
        return f'<BasisSpecies {self.name}>'

class AuxiliaryBasisSpecies(ComplexSpecies):
    def __repr__(self) -> str:
        return f'AuxiliaryBasisSpecies(name={repr(self.name)}, charge={repr(self.charge)}, volume={repr(self.volume)}, composition={repr(self.composition)}, decomposition={repr(self.dissociation)}, logk={repr(self.logk)})'

    def __str__(self) -> str:
        return f'<AuxiliaryBasisSpecies {self.name}>'

class AqueousSpecies(ComplexSpecies):
    def __repr__(self) -> str:
        return f'AqueousSpecies(name={repr(self.name)}, charge={repr(self.charge)}, volume={repr(self.volume)}, composition={repr(self.composition)}, decomposition={repr(self.dissociation)}, logk={repr(self.logk)})'

    def __str__(self) -> str:
        return f'<AqueousSpecies {self.name}>'

class Solid(ComplexSpecies):
    def __repr__(self) -> str:
        return f'Solid(name={repr(self.name)}, charge={repr(self.charge)}, volume={repr(self.volume)}, composition={repr(self.composition)}, decomposition={repr(self.dissociation)}, logk={repr(self.logk)})'

    def __str__(self) -> str:
        return f'<Solid {self.name}>'

class Liquid(ComplexSpecies):
    def __repr__(self) -> str:
        return f'Liquid(name={repr(self.name)}, charge={repr(self.charge)}, volume={repr(self.volume)}, composition={repr(self.composition)}, decomposition={repr(self.dissociation)}, logk={repr(self.logk)})'

    def __str__(self) -> str:
        return f'<Liquid {self.name}>'

class Gas(ComplexSpecies):
    def __repr__(self) -> str:
        return f'Gas(name={repr(self.name)}, charge={repr(self.charge)}, volume={repr(self.volume)}, composition={repr(self.composition)}, decomposition={repr(self.dissociation)}, logk={repr(self.logk)})'

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
    def __init__(self, model: SolidSolutionModel, site_params: np.ndarray, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self.site_params = site_params

    def __repr__(self) -> str:
        return f'SolidSolutionModel(name={repr(self.name)}, composition={repr(self.composition)}, model={repr(self.model)}, site_params={repr(self.site_params)})'

    def __str__(self) -> str:
        return f'<SolidSolution {self.name}>'

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
        self.elements = elements
        self.basis_species = basis_species
        self.auxiliary_basis_species = auxiliary_basis_species
        self.aqueous_species = aqueous_species
        self.solids = solids
        self.liquids = liquids
        self.gases = gases
        self.solid_solutions = solid_solutions
        self.references = references
        self.__species = set[str]()

    def reify(self):
        self.__species = set(self.elements.keys())
        self.__species.update(self.basis_species.keys())
        self.__species.update(self.auxiliary_basis_species.keys())
        self.__species.update(self.aqueous_species.keys())
        self.__species.update(self.solids.keys())
        self.__species.update(self.liquids.keys())
        self.__species.update(self.gases.keys())
        self.__species.update(self.solid_solutions.keys())

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
                if substrate not in self.__species:
                    raise Exception(f'{species} has a substrate ({substrate}) in its dissocation reaction ({species.dissociation}) that does not appear in the elements or any species sections')

            for product in s.dissociation.products.keys():
                if product not in self.__species:
                    raise Exception(f'{species} has a product ({product}) in its dissocation reaction ({species.dissociation}) that does not appear in the elements or any species sections')

            if len(s.logk) != len(self.params.temperatures):
                raise Exception(f'{species} has a different number of log(K) values than the number of values in the data0 temperature grid')

    def __verify_solid_solutions(self, solid_solutions):
        for solid_solution in solid_solutions.values():
            for solid in solid_solution.composition.keys():
                if solid not in self.solids:
                    raise Exception(f'{solid_solutions} has an solid ({solid}) that does not appear in the data0 solids section')
