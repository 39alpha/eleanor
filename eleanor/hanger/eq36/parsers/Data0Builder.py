from . Data0Listener import Data0Listener
from . Data0Parser import Data0Parser
from .. data0 import Data0, AqueousSpecies, AuxiliaryBasisSpecies, BDotSpecies, BasisSpecies, \
    Composition, Dissociation, Element, FormulaTerm, Gas, Liquid, Params, Solid, SolidSolution, \
    SolidSolutionModel, Volume
import numpy as np

class Data0Builder(Data0Listener):
    def __init__(self, fname=None, permissive=False):
        super().__init__()
        self.fname = fname
        self.permissive = permissive
        self.data = None

    def exitHeader(self, ctx: Data0Parser.HeaderContext):
        ctx.data = ctx.getText()

    def exitRestOfLine(self, ctx: Data0Parser.RestOfLineContext):
        ctx.data = ctx.getText()

    def exitData0(self, ctx: Data0Parser.Data0Context):
        ctx.data = Data0(self.fname)
        ctx.data.magic = ctx.magic().data
        ctx.data.header = ctx.header().data
        ctx.data.params = ctx.paramsSection().data
        ctx.data.bdot = ctx.bdotSpeciesSection().data
        ctx.data.elements = ctx.elementsSection().data
        ctx.data.basis_species = ctx.basisSpeciesSection().data
        ctx.data.auxiliary_basis_species = ctx.auxiliaryBasisSpeciesSection().data
        ctx.data.aqueous_species = ctx.aqueousSpeciesSection().data
        ctx.data.solids = ctx.solidsSection().data
        ctx.data.liquids = ctx.liquidsSection().data
        ctx.data.gases = ctx.gasesSection().data
        ctx.data.solid_solutions = ctx.solidSolutionsSection().data
        ctx.data.references = ctx.referenceSection().data

        self.data = ctx.data

    def exitMagic(self, ctx: Data0Parser.MagicContext):
        ctx.data = ctx.restOfLine().getText()

    def exitSectionHeader(self, ctx: Data0Parser.SectionHeaderContext):
        ctx.data = ctx.getText()

    def exitParamsSection(self, ctx: Data0Parser.ParamsSectionContext):
        ctx.data = Params()
        ctx.data.temperatures = ctx.temperatures().data
        ctx.data.pressures = ctx.pressures().data
        ctx.data.debye_huckel_a = ctx.debyeHuckelA().data
        ctx.data.debye_huckel_b = ctx.debyeHuckelB().data
        ctx.data.bdot = ctx.bdot().data
        ctx.data.cco2 = ctx.cco2().data
        ctx.data.ehlogk = ctx.eHLogK().data

    def exitTemperatures(self, ctx: Data0Parser.TemperaturesContext):
        min, max, *rest = ctx.numberLine().data
        if not self.permissive and len(rest) != 0:
            raise Exception('expected exactly 2 numbers')
        ctx.data = ctx.numberGrid().data

        if not self.permissive and min != ctx.data.min():
            msg = f'expected minimum temperature in grid to be {min}, got {ctx.data.min()}'
            raise Exception(msg)
        if not self.permissive and max != ctx.data.max():
            msg = f'expected maximum temperature in grid to be {max}, got {ctx.data.max()}'
            raise Exception(msg)

    def exitPressures(self, ctx: Data0Parser.PressuresContext):
        ctx.data = ctx.numberGrid().data

    def exitDebyeHuckelA(self, ctx: Data0Parser.DebyeHuckelAContext):
        ctx.data = ctx.numberGrid().data

    def exitDebyeHuckelB(self, ctx: Data0Parser.DebyeHuckelBContext):
        ctx.data = ctx.numberGrid().data

    def exitBdot(self, ctx: Data0Parser.BdotContext):
        ctx.data = ctx.numberGrid().data

    def exitCco2(self, ctx: Data0Parser.Cco2Context):
        ctx.data = ctx.numberGrid().data

    def exitEHLogK(self, ctx: Data0Parser.EHLogKContext):
        ctx.data = ctx.numberGrid().data

    def exitBdotSpeciesSection(self, ctx: Data0Parser.BdotSpeciesSectionContext):
        ctx.data = [bdot.data for bdot in ctx.bdotSpecies()]

    def exitBdotSpecies(self, ctx: Data0Parser.BdotSpeciesContext):
        ctx.data = BDotSpecies()
        ctx.data.name = ctx.WORD().getText()

        azer0, neutral_ion_type = ctx.NUMBER()
        ctx.data.azer0 = np.float64(azer0.getText())
        ctx.data.neutral_ion_type = np.int64(neutral_ion_type.getText())

    def exitElementsSection(self, ctx: Data0Parser.ElementsSectionContext):
        ctx.data = [element.data for element in ctx.element()]

    def exitElement(self, ctx: Data0Parser.ElementContext):
        ctx.data = Element()
        ctx.data.name = ctx.WORD().getText()
        ctx.data.weight = np.float64(ctx.NUMBER().getText())

    def exitBasisSpeciesSection(self, ctx: Data0Parser.BasisSpeciesSectionContext):
        ctx.data = [species.data for species in ctx.basisSpecies()]

    def exitChargeLine(self, ctx: Data0Parser.ChargeLineContext):
        ctx.data = np.float64(ctx.NUMBER().getText())

    def exitComposition(self, ctx: Data0Parser.CompositionContext):
        ctx.data = Composition()
        ctx.data.terms = []

        num_elements = np.int64(ctx.NUMBER().getText())
        for line in ctx.formulaLine():
            ctx.data.terms.extend(line.data)

        if len(ctx.data.terms) != num_elements:
            msg = f'expected {num_elements} terms in composition, got {len(ctx.data.terms)}'
            raise Exception(msg)

    def exitFormulaLine(self, ctx: Data0Parser.FormulaLineContext):
        ctx.data = [term.data for term in ctx.formulaTerm()]

    def exitFormulaTerm(self, ctx: Data0Parser.FormulaTermContext):
        ctx.data = FormulaTerm()
        ctx.data.count = np.int64(np.float64(ctx.NUMBER().getText()))
        ctx.data.element = ctx.WORD().getText()

    def exitAuxiliaryBasisSpeciesSection(self,
                                         ctx: Data0Parser.AuxiliaryBasisSpeciesSectionContext):
        ctx.data = [species.data for species in ctx.auxiliaryBasisSpecies()]

    def exitDissociation(self, ctx: Data0Parser.DissociationContext):
        ctx.data = Dissociation()
        ctx.data.terms = []

        num_elements = np.int64(ctx.NUMBER().getText())
        for line in ctx.formulaLine():
            ctx.data.terms.extend(line.data)

        if len(ctx.data.terms) != num_elements:
            msg = f'expected {num_elements} terms in composition, got {len(ctx.data.terms)}'
            raise Exception(msg)

    def exitPossiblyEmptyNumberGrid(self, ctx: Data0Parser.PossiblyEmptyNumberGridContext):
        grid = []
        for line in ctx.numberLine():
            grid.extend(line.data)
        ctx.data = np.asarray(grid)

    def exitNumberGrid(self, ctx: Data0Parser.NumberGridContext):
        grid = []
        for line in ctx.numberLine():
            grid.extend(line.data)
        ctx.data = np.asarray(grid)

    def exitNumberLine(self, ctx: Data0Parser.NumberLineContext):
        ctx.data = np.asarray([np.float64(n.getText()) for n in ctx.NUMBER()])

    def exitAqueousSpeciesSection(self, ctx: Data0Parser.AqueousSpeciesSectionContext):
        ctx.data = [species.data for species in ctx.aqueousSpecies()]

    def exitSolidsSection(self, ctx: Data0Parser.SolidsSectionContext):
        ctx.data = [solid.data for solid in ctx.solid()]

    def exitLiquidsSection(self, ctx: Data0Parser.LiquidsSectionContext):
        ctx.data = [liquid.data for liquid in ctx.liquid()]

    def exitGasesSection(self, ctx: Data0Parser.GasesSectionContext):
        ctx.data = [gas.data for gas in ctx.gas()]

    def exitVolumeLine(self, ctx: Data0Parser.VolumeLineContext):
        ctx.data = Volume()
        ctx.value = np.float64(ctx.NUMBER().getText())
        ctx.unit = ctx.restOfLine().getText()

    def exitSolidSolutionsSection(self, ctx: Data0Parser.SolidSolutionsSectionContext):
        ctx.data = [solid_solution.data for solid_solution in ctx.solidSolution()]

    def exitComponents(self, ctx: Data0Parser.ComponentsContext):
        ctx.data = Composition()
        ctx.data.terms = []

        num_elements = np.int64(ctx.NUMBER().getText())
        for line in ctx.formulaLine():
            ctx.data.terms.extend(line.data)

        if len(ctx.data.terms) != num_elements:
            msg = f'expected {num_elements} terms in composition, got {len(ctx.data.terms)}'
            raise Exception(msg)

    def exitModelSpec(self, ctx: Data0Parser.ModelSpecContext):
        ctx.data = SolidSolutionModel()
        ctx.data.type = ctx.modelType().data
        ctx.data.params = ctx.modelParams().data

    def exitModelType(self, ctx: Data0Parser.ModelTypeContext):
        ctx.data = np.int64(ctx.NUMBER().getText())

    def exitModelParams(self, ctx: Data0Parser.ModelParamsContext):
        num_params = np.int64(ctx.NUMBER().getText())
        ctx.data = ctx.possiblyEmptyNumberGrid().data
        if not self.permissive and num_params != len(ctx.data):
            raise Exception(f'expected {num_params} model parameters, got ${len(ctx.data)}')

    def exitSiteParams(self, ctx: Data0Parser.SiteParamsContext):
        num_params = np.int64(ctx.NUMBER().getText())
        ctx.data = ctx.numberLine().data
        if not self.permissive and num_params != len(ctx.data):
            raise Exception(f'expected {num_params} site parameters, got ${len(ctx.data)}')

    def exitDateLastRevised(self, ctx: Data0Parser.DateLastRevisedContext):
        pass

    def exitKeys(self, ctx: Data0Parser.KeysContext):
        pass

    def exitSpeciesType(self, ctx: Data0Parser.SpeciesTypeContext):
        pass

    def exitBrackets(self, ctx: Data0Parser.BracketsContext):
        pass

    def exitSpeciesJunk(self, ctx: Data0Parser.SpeciesJunkContext):
        pass

    def exitReferenceSection(self, ctx: Data0Parser.ReferenceSectionContext):
        ctx.data = ctx.references().data

    def exitReferences(self, ctx: Data0Parser.ReferencesContext):
        ctx.data = ctx.getText()

    def exitBasisSpecies(self, ctx: Data0Parser.BasisSpeciesContext):
        ctx.data = BasisSpecies()
        ctx.data.name = ctx.WORD().getText()

        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            ctx.data.charge = charges.data
        elif len(charges) == 1:
            ctx.data.charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        ctx.data.composition = ctx.composition().data

    def exitAuxiliaryBasisSpecies(self, ctx: Data0Parser.AuxiliaryBasisSpeciesContext):
        ctx.data = AuxiliaryBasisSpecies()
        ctx.data.name = ctx.WORD().getText()

        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            ctx.data.charge = charges.data
        elif len(charges) == 1:
            ctx.data.charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            ctx.data.volume = volumes.data
        elif len(volumes) == 1:
            ctx.data.volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        ctx.data.composition = ctx.composition().data
        ctx.data.dissociation = ctx.dissociation().data
        ctx.data.logk = ctx.numberGrid().data

    def exitAqueousSpecies(self, ctx: Data0Parser.AqueousSpeciesContext):
        ctx.data = AqueousSpecies()
        ctx.data.name = ctx.WORD().getText()

        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            ctx.data.charge = charges.data
        elif len(charges) == 1:
            ctx.data.charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            ctx.data.volume = volumes.data
        elif len(volumes) == 1:
            ctx.data.volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        ctx.data.composition = ctx.composition().data
        ctx.data.dissociation = ctx.dissociation().data
        ctx.data.logk = ctx.numberGrid().data

    def exitSolid(self, ctx: Data0Parser.SolidContext):
        ctx.data = Solid()
        ctx.data.name = ctx.WORD().getText()

        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            ctx.data.charge = charges.data
        elif len(charges) == 1:
            ctx.data.charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            ctx.data.volume = volumes.data
        elif len(volumes) == 1:
            ctx.data.volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        ctx.data.composition = ctx.composition().data
        ctx.data.dissociation = ctx.dissociation().data
        ctx.data.logk = ctx.numberGrid().data

    def exitLiquid(self, ctx: Data0Parser.LiquidContext):
        ctx.data = Liquid()
        ctx.data.name = ctx.WORD().getText()

        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            ctx.data.charge = charges.data
        elif len(charges) == 1:
            ctx.data.charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            ctx.data.volume = volumes.data
        elif len(volumes) == 1:
            ctx.data.volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        ctx.data.composition = ctx.composition().data
        ctx.data.dissociation = ctx.dissociation().data
        ctx.data.logk = ctx.numberGrid().data

    def exitGas(self, ctx: Data0Parser.GasContext):
        ctx.data = Gas()
        ctx.data.name = ctx.WORD().getText()

        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            ctx.data.charge = charges.data
        elif len(charges) == 1:
            ctx.data.charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            ctx.data.volume = volumes.data
        elif len(volumes) == 1:
            ctx.data.volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        ctx.data.composition = ctx.composition().data
        ctx.data.dissociation = ctx.dissociation().data
        ctx.data.logk = ctx.numberGrid().data

    def exitSolidSolution(self, ctx: Data0Parser.SolidSolutionContext):
        ctx.data = SolidSolution()
        ctx.data.name = ctx.WORD().getText()
        ctx.data.composition = ctx.components().data
        ctx.data.model = ctx.modelSpec().data
        ctx.data.site_params = ctx.siteParams().data
