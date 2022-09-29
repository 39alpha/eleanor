from . Data0Listener import Data0Listener
from . Data0Parser import Data0Parser
from .. data0 import Data0, AqueousSpecies, AuxiliaryBasisSpecies, BDotSpecies, BasisSpecies, \
    Dissociation, Gas, Liquid, Params, Solid, SolidSolution, SolidSolutionModel, Volume
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
        ctx.data = Data0(fname=self.fname,
                         magic=ctx.magic().data,
                         header=ctx.header().data,
                         params=ctx.paramsSection().data,
                         bdot=ctx.bdotSpeciesSection().data,
                         elements=ctx.elementsSection().data,
                         basis_species=ctx.basisSpeciesSection().data,
                         auxiliary_basis_species=ctx.auxiliaryBasisSpeciesSection().data,
                         aqueous_species=ctx.aqueousSpeciesSection().data,
                         solids=ctx.solidsSection().data,
                         liquids=ctx.liquidsSection().data,
                         gases=ctx.gasesSection().data,
                         solid_solutions=ctx.solidSolutionsSection().data,
                         references=ctx.referenceSection().data)

        ctx.data.verify()

        self.data = ctx.data

    def exitMagic(self, ctx: Data0Parser.MagicContext):
        ctx.data = ctx.restOfLine().getText()

    def exitSectionHeader(self, ctx: Data0Parser.SectionHeaderContext):
        ctx.data = ctx.getText()

    def exitParamsSection(self, ctx: Data0Parser.ParamsSectionContext):
        ctx.data = Params(temperatures=ctx.temperatures().data,
                          pressures=ctx.pressures().data,
                          debye_huckel_a=ctx.debyeHuckelA().data,
                          debye_huckel_b=ctx.debyeHuckelB().data,
                          bdot=ctx.bdot().data,
                          cco2=ctx.cco2().data,
                          ehlogk=ctx.eHLogK().data)

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
        ctx.data = {bdot.data.name: bdot.data for bdot in ctx.bdotSpecies()}

    def exitBdotSpecies(self, ctx: Data0Parser.BdotSpeciesContext):
        name = ctx.WORD().getText()

        azer0, neutral_ion_type = ctx.NUMBER()
        azer0 = np.float64(azer0.getText())
        neutral_ion_type = np.int64(neutral_ion_type.getText())

        ctx.data = BDotSpecies(name=name, azer0=azer0, neutral_ion_type=neutral_ion_type)

    def exitElementsSection(self, ctx: Data0Parser.ElementsSectionContext):
        ctx.data = {name: weight for name, weight in map(lambda c: c.data, ctx.element())}

    def exitElement(self, ctx: Data0Parser.ElementContext):
        name = ctx.WORD().getText()
        weight = np.float64(ctx.NUMBER().getText())
        ctx.data = (name, weight)

    def exitBasisSpeciesSection(self, ctx: Data0Parser.BasisSpeciesSectionContext):
        ctx.data = {species.data.name: species.data for species in ctx.basisSpecies()}

    def exitChargeLine(self, ctx: Data0Parser.ChargeLineContext):
        ctx.data = np.float64(ctx.NUMBER().getText())

    def exitComposition(self, ctx: Data0Parser.CompositionContext):
        ctx.data = dict()

        num_elements = np.int64(ctx.NUMBER().getText())
        for line in ctx.formulaLine():
            for name, count in line.data:
                ctx.data[name] = count

        if len(ctx.data) != num_elements:
            msg = f'expected {num_elements} terms in composition, got {len(ctx.data)}'
            raise Exception(msg)

    def exitFormulaLine(self, ctx: Data0Parser.FormulaLineContext):
        ctx.data = [term.data for term in ctx.formulaTerm()]

    def exitFormulaTerm(self, ctx: Data0Parser.FormulaTermContext):
        element = ctx.WORD().getText()
        count = np.int64(np.float64(ctx.NUMBER().getText()))
        ctx.data = (element, count)

    def exitAuxiliaryBasisSpeciesSection(self,
                                         ctx: Data0Parser.AuxiliaryBasisSpeciesSectionContext):
        ctx.data = {species.data.name: species.data for species in ctx.auxiliaryBasisSpecies()}

    def exitDissociation(self, ctx: Data0Parser.DissociationContext):
        substrates = dict()
        products = dict()

        num_elements = np.int64(ctx.NUMBER().getText())
        for line in ctx.formulaLine():
            for name, count in line.data:
                if count < 0:
                    substrates[name] = -count
                else:
                    products[name] = count

        n = len(substrates) + len(products)
        if n != num_elements:
            msg = f'expected {num_elements} terms in dissociation reaction, got {n}'
            raise Exception(msg)

        ctx.data = Dissociation(substrates, products)

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
        ctx.data = {species.data.name: species.data for species in ctx.aqueousSpecies()}

    def exitSolidsSection(self, ctx: Data0Parser.SolidsSectionContext):
        ctx.data = {solid.data.name: solid.data for solid in ctx.solid()}

    def exitLiquidsSection(self, ctx: Data0Parser.LiquidsSectionContext):
        ctx.data = {liquid.data.name: liquid.data for liquid in ctx.liquid()}

    def exitGasesSection(self, ctx: Data0Parser.GasesSectionContext):
        ctx.data = {gas.data.name: gas.data for gas in ctx.gas()}

    def exitVolumeLine(self, ctx: Data0Parser.VolumeLineContext):
        ctx.data = Volume(value=np.float64(ctx.NUMBER().getText()),
                          unit=ctx.restOfLine().getText())

    def exitSolidSolutionsSection(self, ctx: Data0Parser.SolidSolutionsSectionContext):
        ctx.data = {solid_solution.data.name: solid_solution.data
                    for solid_solution in ctx.solidSolution()}

    def exitComponents(self, ctx: Data0Parser.ComponentsContext):
        ctx.data = dict()

        num_elements = np.int64(ctx.NUMBER().getText())
        for line in ctx.formulaLine():
            for name, count in line.data:
                ctx.data[name] = count

        if len(ctx.data) != num_elements:
            msg = f'expected {num_elements} solid solution components, got {len(ctx.data)}'
            raise Exception(msg)

    def exitModelSpec(self, ctx: Data0Parser.ModelSpecContext):
        ctx.data = SolidSolutionModel(type=ctx.modelType().data,
                                      params=ctx.modelParams().data)

    def exitModelType(self, ctx: Data0Parser.ModelTypeContext):
        ctx.data = np.int64(ctx.NUMBER().getText())

    def exitModelParams(self, ctx: Data0Parser.ModelParamsContext):
        num_params = np.int64(ctx.NUMBER().getText())
        ctx.data = ctx.possiblyEmptyNumberGrid().data
        if not self.permissive and num_params != len(ctx.data):
            raise Exception(f'expected {num_params} model parameters, got {len(ctx.data)}')

    def exitSiteParams(self, ctx: Data0Parser.SiteParamsContext):
        num_params = np.int64(ctx.NUMBER().getText())
        ctx.data = ctx.numberLine().data
        if not self.permissive and num_params != len(ctx.data):
            raise Exception(f'expected {num_params} site parameters, got {len(ctx.data)}')

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
        name = ctx.WORD().getText()

        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            charge = charges.data
        elif len(charges) == 1:
            charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        composition = ctx.composition().data

        ctx.data = BasisSpecies(name=name, charge=charge, composition=composition)

    def exitAuxiliaryBasisSpecies(self, ctx: Data0Parser.AuxiliaryBasisSpeciesContext):
        name = ctx.WORD().getText()

        charge = None
        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            charge = charges.data
        elif len(charges) == 1:
            charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volume = None
        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            volume = volumes.data
        elif len(volumes) == 1:
            volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        composition = ctx.composition().data
        dissociation = ctx.dissociation().data
        logk = ctx.numberGrid().data

        ctx.data = AuxiliaryBasisSpecies(name=name,
                                         charge=charge,
                                         volume=volume,
                                         composition=composition,
                                         dissociation=dissociation,
                                         logk=logk)

    def exitAqueousSpecies(self, ctx: Data0Parser.AqueousSpeciesContext):
        name = ctx.WORD().getText()

        charge = None
        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            charge = charges.data
        elif len(charges) == 1:
            charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volume = None
        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            volume = volumes.data
        elif len(volumes) == 1:
            volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        composition = ctx.composition().data
        dissociation = ctx.dissociation().data
        logk = ctx.numberGrid().data

        ctx.data = AqueousSpecies(name=name,
                                  charge=charge,
                                  volume=volume,
                                  composition=composition,
                                  dissociation=dissociation,
                                  logk=logk)

    def exitSolid(self, ctx: Data0Parser.SolidContext):
        name = ctx.WORD().getText()

        charge = None
        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            charge = charges.data
        elif len(charges) == 1:
            charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volume = None
        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            volume = volumes.data
        elif len(volumes) == 1:
            volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        composition = ctx.composition().data
        dissociation = ctx.dissociation().data
        logk = ctx.numberGrid().data

        ctx.data = Solid(name=name,
                         charge=charge,
                         volume=volume,
                         composition=composition,
                         dissociation=dissociation,
                         logk=logk)

    def exitLiquid(self, ctx: Data0Parser.LiquidContext):
        name = ctx.WORD().getText()

        charge = None
        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            charge = charges.data
        elif len(charges) == 1:
            charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volume = None
        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            volume = volumes.data
        elif len(volumes) == 1:
            volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        composition = ctx.composition().data
        dissociation = ctx.dissociation().data
        logk = ctx.numberGrid().data

        ctx.data = Liquid(name=name,
                          charge=charge,
                          volume=volume,
                          composition=composition,
                          dissociation=dissociation,
                          logk=logk)

    def exitGas(self, ctx: Data0Parser.GasContext):
        name = ctx.WORD().getText()

        charge = None
        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            charge = charges.data
        elif len(charges) == 1:
            charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        volume = None
        volumes = ctx.volumeLine()
        if isinstance(volumes, Data0Parser.VolumeLineContext):
            volume = volumes.data
        elif len(volumes) == 1:
            volume = volumes[0].data
        elif len(volumes) > 1:
            raise Exception(f'expected at most 1 volume line, got {len(volumes)}')

        composition = ctx.composition().data
        dissociation = ctx.dissociation().data
        logk = ctx.numberGrid().data

        ctx.data = Gas(name=name,
                       charge=charge,
                       volume=volume,
                       composition=composition,
                       dissociation=dissociation,
                       logk=logk)

    def exitSolidSolution(self, ctx: Data0Parser.SolidSolutionContext):
        ctx.data = SolidSolution(name=ctx.WORD().getText(),
                                 composition=ctx.components().data,
                                 model=ctx.modelSpec().data,
                                 site_params=ctx.siteParams().data)
