from typing import Iterator

class Data0(object):
    @staticmethod
    def from_file(fname, *args, **kwargs):
        from . parsers import parse_data0
        data0, _ = parse_data0(fname, *args, **kwargs)
        return data0

    def __init__(self, fname=None, magic=None, header=None, params=None, bdot=None, elements=None,
                 basis_species=None, auxiliary_basis_species=None, aqueous_species=None,
                 solids=None, liquids=None, gases=None, solid_solutions=None, references=None):
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

class Params(object):
    def __init__(self):
        self.temperatures = None
        self.pressures = None
        self.debye_huckel_a = None
        self.debye_huckel_b = None
        self.bdot = None
        self.cco2 = None
        self.ehlogk = None

class BDotSpecies(object):
    def __init__(self):
        self.name = None
        self.azer0 = None
        self.neutral_ion_type = None

class Dissociation(object):
    def __init__(self, substrates=None, products=None):
        self.substrates = substrates if substrates is not None else dict()
        self.products = products if products is not None else dict()

    def __repr__(self) -> str:
        return f'Dissociation(substrats={self.substrates}, products={self.products})'

    def __str__(self) -> str:
        substrates = ' + '.join(f'{count} {name}' for name, count in self.substrates.items())
        products = ' + '.join(f'{count} {name}' for name, count in self.products.items())
        return f'{substrates} ⇌ {products}'

class Species(object):
    def __init__(self):
        self.name = None
        self.composition = None

class BasicSpecies(Species):
    def __init__(self):
        self.charge = None
        self.volume = None

class ComplexSpecies(BasicSpecies):
    def __init__(self):
        super().__init__()
        self.dissociation = None
        self.logk = None

class BasisSpecies(BasicSpecies):
    pass

class AuxiliaryBasisSpecies(ComplexSpecies):
    pass

class AqueousSpecies(ComplexSpecies):
    pass

class Solid(ComplexSpecies):
    pass

class Liquid(ComplexSpecies):
    pass

class Gas(ComplexSpecies):
    pass

class SolidSolution(Species):
    def __init__(self):
        super().__init__()
        self.model = None
        self.site_params = None

class SolidSolutionModel(object):
    def __init__(self):
        self.type = None
        self.params = None

class Volume(object):
    def __init__(self):
        self.value = None
        self.unit = None
