class Data0(object):
    @staticmethod
    def from_file(fname, *args, **kwargs):
        from . parsers import parse_data0
        data0, _ = parse_data0(fname, *args, **kwargs)
        return data0

    def __init__(self, fname=None):
        self.fname = fname
        self.magic = None
        self.header = None
        self.params = None
        self.bdot = None
        self.elements = None
        self.basis_species = None
        self.auxiliary_basis_species = None
        self.aqueous_species = None
        self.solids = None
        self.liquids = None
        self.gases = None
        self.solid_solutions = None
        self.references = None

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

class Element(object):
    def __init__(self):
        self.name = None
        self.weight = None

class Composition(object):
    def __init__(self):
        self.terms = None

class Dissociation(Composition):
    pass

class FormulaTerm(object):
    def __init__(self):
        self.count = None
        self.element = None

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
