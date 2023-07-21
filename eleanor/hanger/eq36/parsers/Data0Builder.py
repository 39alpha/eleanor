from . Data0Listener import Data0Listener
from . Data0Parser import Data0Parser
from .. data0 import AqueousSpecies, AuxiliaryBasisSpecies, BasisSpecies, BDotSpecies, \
    Data0, DebyeHuckelModelParams, Dissociation, Gas, Liquid, ModelParams, Params, PitzerABCTerm, \
    PitzerCombinations, PitzerLambdaMuTerm, PitzerLambdaTerm, PitzerModelParams, PitzerMuTerm, \
    PitzerPsiTerm, PitzerThetaTerm, PitzerZetaTerm, Solid, SolidSolution, SolidSolutionModel, \
    Volume

import numpy as np
import re

class Data0Builder(Data0Listener):
    def __init__(self, fname=None, permissive=False):
        super().__init__()
        self.fname = fname
        self.permissive = permissive
        self.data = None

    def exitHeader(self, ctx: Data0Parser.HeaderContext):
        ctx.data = ctx.getText().strip()

    def exitRestOfLine(self, ctx: Data0Parser.RestOfLineContext):
        ctx.data = ctx.getText()

    def exitData0(self, ctx: Data0Parser.Data0Context):
        (bdot, pitzer_combinations) = ctx.modelSection().data
        ctx.data = Data0(fname=self.fname,
                         magic=ctx.magicLine().data,
                         header=ctx.header().data,
                         params=ctx.paramsSection().data,
                         bdot=bdot,
                         pitzer_combinations=pitzer_combinations,
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

    def exitMagicLine(self, ctx: Data0Parser.MagicLineContext):
        ctx.data = ctx.restOfLine().getText().strip()

    def exitSectionHeader(self, ctx: Data0Parser.SectionHeaderContext):
        ctx.data = ctx.restOfLine().getText().strip()

    def exitParamsSection(self, ctx: Data0Parser.ParamsSectionContext):
        (debye_huckel, pitzer) = ctx.modelParams().data
        ctx.data = Params(temperatures=ctx.temperatures().data,
                          pressures=ctx.pressures().data,
                          debye_huckel=debye_huckel,
                          pitzer=pitzer,
                          ehlogk=ctx.eHLogK().data)

    def exitTemperatures(self, ctx: Data0Parser.TemperaturesContext):
        min, max = ctx.temperatureRange().data
        ctx.data = ctx.numberGrid().data

        if not self.permissive and min != ctx.data.min():
            msg = f'expected minimum temperature in grid to be {min}, got {ctx.data.min()}'
            raise Exception(msg)
        if not self.permissive and max != ctx.data.max():
            msg = f'expected maximum temperature in grid to be {max}, got {ctx.data.max()}'
            raise Exception(msg)

    def exitTemperatureRange(self, ctx: Data0Parser.TemperatureRangeContext):
        ctx.data = np.asarray([n.data for n in ctx.number()])

    def exitPressures(self, ctx: Data0Parser.PressuresContext):
        ctx.data = ctx.numberGrid().data

    def exitModelParams(self, ctx: Data0Parser.ModelParamsContext):
        if ctx.debyeHuckelModelParams() is None:
            debye_huckel = None
        else:
            debye_huckel = ctx.debyeHuckelModelParams().data

        if ctx.pitzerModelParams() is None:
            pitzer = None
        else:
            pitzer = ctx.pitzerModelParams().data

        ctx.data = (debye_huckel, pitzer)

    def exitDebyeHuckelModelParams(self, ctx: Data0Parser.DebyeHuckelModelParamsContext):
        ctx.data = DebyeHuckelModelParams(debye_huckel_a=ctx.debyeHuckelA().data,
                                          debye_huckel_b=ctx.debyeHuckelB().data,
                                          bdot=ctx.bdot().data,
                                          cco2=ctx.cco2().data)

    def exitPitzerModelParams(self, ctx: Data0Parser.PitzerModelParamsContext):
        ctx.data = PitzerModelParams(debye_huckel_a=ctx.debyeHuckelA().data)

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

    def exitModelSection(self, ctx: Data0Parser.ModelSectionContext):
        if ctx.bdotSpeciesSection() is None:
            bdot = None
        else:
            bdot = ctx.bdotSpeciesSection().data

        if ctx.pitzerCombinations() is None:
            pitzer = None
        else:
            pitzer = ctx.pitzerCombinations().data

        ctx.data = (bdot, pitzer)

    def exitBdotSpeciesSection(self, ctx: Data0Parser.BdotSpeciesSectionContext):
        ctx.data = {bdot.data.name: bdot.data for bdot in ctx.bdotSpecies()}

    def exitBdotSpecies(self, ctx: Data0Parser.BdotSpeciesContext):
        name = ctx.bdotSpeciesName().data

        azer0, neutral_ion_type = [n.data for n in ctx.number()]
        neutral_ion_type = np.int64(neutral_ion_type)

        ctx.data = BDotSpecies(name=name, azer0=azer0, neutral_ion_type=neutral_ion_type)

    def exitBdotSpeciesName(self, ctx: Data0Parser.BdotSpeciesNameContext):
        ctx.data = ctx.getText().strip()

    def exitPitzerCombinations(self, ctx: Data0Parser.PitzerCombinationsContext):
        ctx.data = PitzerCombinations(ca=ctx.caCombinations().data,
                                      ccp_aap=ctx.ccPrimeAaPrimeCombinations().data,
                                      nc_na=ctx.ncNaCombinations().data,
                                      nn=ctx.nnCombinations().data,
                                      nnp=ctx.nnPrimeCombinations().data,
                                      ccpa_aapc=ctx.ccPrimeAAaPrimeCCombinations().data,
                                      nca=ctx.ncaCombinations().data,
                                      nnnp=ctx.nnnPrimeCombinations().data)

    def exitCaCombinations(self, ctx: Data0Parser.CaCombinationsContext):
        ctx.data = dict()
        for abc in ctx.pitzerAlphaBetaCphiParams():
            (name, datum) = abc.data
            ctx.data[name] = datum

    def exitCcPrimeAaPrimeCombinations(self, ctx: Data0Parser.CcPrimeAaPrimeCombinationsContext):
        ctx.data = dict()
        for theta in ctx.pitzerThetaParams():
            (name, datum) = theta.data
            ctx.data[name] = datum

    def exitNcNaCombinations(self, ctx: Data0Parser.NcNaCombinationsContext):
        ctx.data = dict()
        for lam in ctx.pitzerLambdaParams():
            (name, datum) = lam.data
            ctx.data[name] = datum

    def exitNnCombinations(self, ctx: Data0Parser.NnCombinationsContext):
        ctx.data = dict()
        for lambda_mu in ctx.pitzerLambdaMuParams():
            (name, datum) = lambda_mu.data
            ctx.data[name] = datum

    def exitNnPrimeCombinations(self, ctx: Data0Parser.NnPrimeCombinationsContext):
        ctx.data = dict()
        for lam in ctx.pitzerLambdaParams():
            (name, datum) = lam.data
            ctx.data[name] = datum

    def exitCcPrimeAAaPrimeCCombinations(self, ctx: Data0Parser.CcPrimeAAaPrimeCCombinationsContext):
        ctx.data = dict()
        for psi in ctx.pitzerPsiParams():
            (name, datum) = psi.data
            ctx.data[name] = datum

    def exitNcaCombinations(self, ctx: Data0Parser.NcaCombinationsContext):
        ctx.data = dict()
        for zeta in ctx.pitzerZetaParams():
            (name, datum) = zeta.data
            ctx.data[name] = datum

    def exitNnnPrimeCombinations(self, ctx: Data0Parser.NnnPrimeCombinationsContext):
        ctx.data = dict()
        for mu in ctx.pitzerMuParams():
            (name, datum) = mu.data
            ctx.data[name] = datum

    def exitPitzerAlphaBetaCphiParams(self, ctx: Data0Parser.PitzerAlphaBetaCphiParamsContext):
        term = PitzerABCTerm(alpha1=ctx.alpha1().data,
                             alpha2=ctx.alpha2().data,
                             beta0=ctx.beta0().data,
                             beta1=ctx.beta1().data,
                             beta2=ctx.beta2().data,
                             cphi=ctx.cphi().data)
        ctx.data = (ctx.pitzerTuple().data, term)

    def exitPitzerThetaParams(self, ctx: Data0Parser.PitzerThetaParamsContext):
        term = PitzerThetaTerm(theta=ctx.theta().data)
        ctx.data = (ctx.pitzerTuple().data, term)

    def exitPitzerLambdaParams(self, ctx: Data0Parser.PitzerLambdaParamsContext):
        term = PitzerLambdaTerm(lam=ctx.lambda_().data)
        ctx.data = (ctx.pitzerTuple().data, term)

    def exitPitzerLambdaMuParams(self, ctx: Data0Parser.PitzerLambdaMuParamsContext):
        term = PitzerLambdaMuTerm(lam=ctx.lambda_().data,
                                  mu=ctx.mu().data)
        ctx.data = (ctx.pitzerTuple().data, term)

    def exitPitzerPsiParams(self, ctx: Data0Parser.PitzerPsiParamsContext):
        term = PitzerPsiTerm(psi=ctx.psi().data)
        ctx.data = (ctx.pitzerTuple().data, term)

    def exitPitzerZetaParams(self, ctx: Data0Parser.PitzerZetaParamsContext):
        term = PitzerZetaTerm(zeta=ctx.zeta().data)
        ctx.data = (ctx.pitzerTuple().data, term)

    def exitPitzerMuParams(self, ctx: Data0Parser.PitzerMuParamsContext):
        term = PitzerMuTerm(mu=ctx.mu().data)
        ctx.data = (ctx.pitzerTuple().data, term)

    def exitPitzerTuple(self, ctx: Data0Parser.PitzerTupleContext):
        ctx.data = tuple([species.data for species in ctx.speciesName()])

    def exitAlpha1(self, ctx: Data0Parser.Alpha1Context):
        ctx.data = ctx.number().data

    def exitAlpha2(self, ctx: Data0Parser.Alpha2Context):
        ctx.data = ctx.number().data

    def exitBeta0(self, ctx: Data0Parser.Beta0Context):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitBeta1(self, ctx: Data0Parser.Beta1Context):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitBeta2(self, ctx: Data0Parser.Beta2Context):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitCphi(self, ctx: Data0Parser.CphiContext):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitTheta(self, ctx: Data0Parser.ThetaContext):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitLambda_(self, ctx: Data0Parser.Lambda_Context):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitMu(self, ctx: Data0Parser.MuContext):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitPsi(self, ctx: Data0Parser.PsiContext):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitZeta(self, ctx: Data0Parser.ZetaContext):
        ctx.data = [ctx.a1().data, ctx.a2().data, ctx.a3().data, ctx.a4().data]

    def exitA1(self, ctx: Data0Parser.A1Context):
        ctx.data = ctx.number().data

    def exitA2(self, ctx: Data0Parser.A2Context):
        ctx.data = ctx.number().data

    def exitA3(self, ctx: Data0Parser.A3Context):
        ctx.data = ctx.number().data

    def exitA4(self, ctx: Data0Parser.A4Context):
        ctx.data = ctx.number().data

    def exitElementsSection(self, ctx: Data0Parser.ElementsSectionContext):
        ctx.data = {name: weight for name, weight in map(lambda c: c.data, ctx.element())}

    def exitElement(self, ctx: Data0Parser.ElementContext):
        name = ctx.elementName().data
        weight = ctx.number().data
        ctx.data = (name, weight)

    def exitElementName(self, ctx: Data0Parser.ElementNameContext):
        ctx.data = ctx.WORD().getText().strip()

    def exitBasisSpeciesSection(self, ctx: Data0Parser.BasisSpeciesSectionContext):
        ctx.data = {species.data.name: species.data for species in ctx.basisSpecies()}

    def exitChargeLine(self, ctx: Data0Parser.ChargeLineContext):
        ctx.data = ctx.number().data

    def exitComposition(self, ctx: Data0Parser.CompositionContext):
        ctx.data = dict()

        num_elements = np.int64(ctx.number().data)
        for line in ctx.formulaGrid().data:
            for name, count in line:
                ctx.data[name] = count

        if len(ctx.data) != num_elements:
            msg = f'expected {num_elements} terms in composition, got {len(ctx.data)}'
            raise Exception(msg)

    def exitFormulaGrid(self, ctx: Data0Parser.FormulaGridContext):
        ctx.data = [line.data for line in ctx.formulaLine()]

    def exitFormulaLine(self, ctx: Data0Parser.FormulaLineContext):
        ctx.data = [term.data for term in ctx.formulaTerm()]

    def exitFormulaTerm(self, ctx: Data0Parser.FormulaTermContext):
        element = ctx.speciesName().data
        count = np.int64(ctx.number().data)
        ctx.data = (element, count)

    def exitAuxiliaryBasisSpeciesSection(self,
                                         ctx: Data0Parser.AuxiliaryBasisSpeciesSectionContext):
        ctx.data = {species.data.name: species.data for species in ctx.auxiliaryBasisSpecies()}

    def exitDissociation(self, ctx: Data0Parser.DissociationContext):
        substrates = dict()
        products = dict()

        num_elements = np.int64(ctx.number().data)
        for line in ctx.formulaGrid().data:
            for name, count in line:
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

    def exitNumber(self, ctx: Data0Parser.NumberContext):
        if ctx.NUMBER() is not None:
            ctx.data = np.float64(ctx.NUMBER().getText())
        else:
            ctx.data = np.nan

    def exitNumberLine(self, ctx: Data0Parser.NumberLineContext):
        ctx.data = np.asarray([n.data for n in ctx.number()])

    def exitAqueousSpeciesSection(self, ctx: Data0Parser.AqueousSpeciesSectionContext):
        ctx.data = {species.data.name: species.data for species in ctx.aqueousSpecies()}

    def exitSolidsSection(self, ctx: Data0Parser.SolidsSectionContext):
        ctx.data = {solid.data.name: solid.data for solid in ctx.solid()}

    def exitLiquidsSection(self, ctx: Data0Parser.LiquidsSectionContext):
        ctx.data = {liquid.data.name: liquid.data for liquid in ctx.liquid()}

    def exitGasesSection(self, ctx: Data0Parser.GasesSectionContext):
        ctx.data = {gas.data.name: gas.data for gas in ctx.gas()}

    def exitVolumeLine(self, ctx: Data0Parser.VolumeLineContext):
        ctx.data = Volume(value=ctx.volume().data,
                          unit=ctx.restOfLine().getText().strip())

    def exitVolume(self, ctx: Data0Parser.VolumeContext):
        ctx.data = ctx.number().data

    def exitSolidSolutionsSection(self, ctx: Data0Parser.SolidSolutionsSectionContext):
        ctx.data = {solid_solution.data.name: solid_solution.data
                    for solid_solution in ctx.solidSolution()}

    def exitComponents(self, ctx: Data0Parser.ComponentsContext):
        ctx.data = dict()

        num_elements = np.int64(ctx.number().data)
        for line in ctx.formulaGrid().data:
            for name, count in line:
                ctx.data[name] = count

        if len(ctx.data) != num_elements:
            msg = f'expected {num_elements} solid solution components, got {len(ctx.data)}'
            raise Exception(msg)

    def exitSolidSolutionModelSpec(self, ctx: Data0Parser.SolidSolutionModelSpecContext):
        ctx.data = SolidSolutionModel(type=ctx.solidSolutionModelType().data,
                                      params=ctx.solidSolutionModelParams().data)

    def exitSolidSolutionModelType(self, ctx: Data0Parser.SolidSolutionModelTypeContext):
        ctx.data = np.int64(ctx.number().data)

    def exitSolidSolutionModelParams(self, ctx: Data0Parser.SolidSolutionModelParamsContext):
        num_params = np.int64(ctx.number().data)
        ctx.data = ctx.possiblyEmptyNumberGrid().data
        if not self.permissive and num_params != len(ctx.data):
            raise Exception(f'expected {num_params} model parameters, got {len(ctx.data)}')

    def exitSiteParams(self, ctx: Data0Parser.SiteParamsContext):
        num_params = np.int64(ctx.number().data)
        ctx.data = ctx.numberLine().data
        if not self.permissive and num_params != len(ctx.data):
            raise Exception(f'expected {num_params} site parameters, got {len(ctx.data)}')

    def exitDateRevised(self, ctx: Data0Parser.DateRevisedContext):
        ctx.data = ctx.date().data

    def exitDate(self, ctx: Data0Parser.DateContext):
        date = ctx.getText().strip()
        ctx.data = date if date != '' else None

    def exitKeys(self, ctx: Data0Parser.KeysContext):
        keys = re.sub(r'\s+', ' ', ctx.restOfLine().getText().strip())
        ctx.data = keys if keys != '' else None

    def exitSpeciesType(self, ctx: Data0Parser.SpeciesTypeContext):
        species_type = ctx.restOfLine().getText().strip()
        ctx.data = species_type if species_type != '' else None

    def exitReferenceSection(self, ctx: Data0Parser.ReferenceSectionContext):
        ctx.data = ctx.references().data

    def exitReferences(self, ctx: Data0Parser.ReferencesContext):
        ctx.data = ctx.getText().strip()

    def exitBasisSpecies(self, ctx: Data0Parser.BasisSpeciesContext):
        name = ctx.speciesName().data
        note = ctx.speciesNote().data
        revised = ctx.dateRevised()[-1].data if len(ctx.dateRevised()) > 0 else None
        species_type = ctx.speciesType()[-1].data if len(ctx.speciesType()) > 0 else None
        keys = ctx.keys()[-1].data if len(ctx.keys()) > 0 else None

        charges = ctx.chargeLine()
        if isinstance(charges, Data0Parser.ChargeLineContext):
            charge = charges.data
        elif len(charges) == 1:
            charge = charges[0].data
        elif len(charges) > 1:
            raise Exception(f'expected at most 1 charge line, got {len(charges)}')

        composition = ctx.composition().data

        ctx.data = BasisSpecies(name=name,
                                note=note,
                                revised=revised,
                                species_type=species_type,
                                keys=keys,
                                charge=charge,
                                composition=composition)

    def exitSpeciesName(self, ctx: Data0Parser.SpeciesNameContext):
        ctx.data = ctx.getText().strip()

    def exitSpeciesNote(self, ctx: Data0Parser.SpeciesNoteContext):
        content = ctx.getText().strip()
        ctx.data = content if content != '' else None

    def exitAuxiliaryBasisSpecies(self, ctx: Data0Parser.AuxiliaryBasisSpeciesContext):
        name = ctx.speciesName().data
        note = ctx.speciesNote().data
        revised = ctx.dateRevised()[-1].data if len(ctx.dateRevised()) > 0 else None
        species_type = ctx.speciesType()[-1].data if len(ctx.speciesType()) > 0 else None
        keys = ctx.keys()[-1].data if len(ctx.keys()) > 0 else None

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
        logk = ctx.logKGrid().data

        ctx.data = AuxiliaryBasisSpecies(name=name,
                                         note=note,
                                         revised=revised,
                                         species_type=species_type,
                                         keys=keys,
                                         charge=charge,
                                         volume=volume,
                                         composition=composition,
                                         dissociation=dissociation,
                                         logk=logk)

    def exitLogKGrid(self, ctx: Data0Parser.LogKGridContext):
        ctx.data = ctx.numberGrid().data

    def exitAqueousSpecies(self, ctx: Data0Parser.AqueousSpeciesContext):
        name = ctx.speciesName().data
        note = ctx.speciesNote().data
        revised = ctx.dateRevised()[-1].data if len(ctx.dateRevised()) > 0 else None
        species_type = ctx.speciesType()[-1].data if len(ctx.speciesType()) > 0 else None
        keys = ctx.keys()[-1].data if len(ctx.keys()) > 0 else None

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
        logk = ctx.logKGrid().data

        ctx.data = AqueousSpecies(name=name,
                                  note=note,
                                  revised=revised,
                                  species_type=species_type,
                                  keys=keys,
                                  charge=charge,
                                  volume=volume,
                                  composition=composition,
                                  dissociation=dissociation,
                                  logk=logk)

    def exitSolid(self, ctx: Data0Parser.SolidContext):
        name = ctx.speciesName().data
        note = ctx.speciesNote().data
        revised = ctx.dateRevised()[-1].data if len(ctx.dateRevised()) > 0 else None
        species_type = ctx.speciesType()[-1].data if len(ctx.speciesType()) > 0 else None
        keys = ctx.keys()[-1].data if len(ctx.keys()) > 0 else None

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
        logk = ctx.logKGrid().data

        ctx.data = Solid(name=name,
                         note=note,
                         revised=revised,
                         species_type=species_type,
                         keys=keys,
                         charge=charge,
                         volume=volume,
                         composition=composition,
                         dissociation=dissociation,
                         logk=logk)

    def exitLiquid(self, ctx: Data0Parser.LiquidContext):
        name = ctx.speciesName().data
        note = ctx.speciesNote().data
        revised = ctx.dateRevised()[-1].data if len(ctx.dateRevised()) > 0 else None
        species_type = ctx.speciesType()[-1].data if len(ctx.speciesType()) > 0 else None
        keys = ctx.keys()[-1].data if len(ctx.keys()) > 0 else None

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
        logk = ctx.logKGrid().data

        ctx.data = Liquid(name=name,
                          note=note,
                          revised=revised,
                          species_type=species_type,
                          keys=keys,
                          charge=charge,
                          volume=volume,
                          composition=composition,
                          dissociation=dissociation,
                          logk=logk)

    def exitGas(self, ctx: Data0Parser.GasContext):
        name = ctx.speciesName().data
        note = ctx.speciesNote().data
        revised = ctx.dateRevised()[-1].data if len(ctx.dateRevised()) > 0 else None
        species_type = ctx.speciesType()[-1].data if len(ctx.speciesType()) > 0 else None
        keys = ctx.keys()[-1].data if len(ctx.keys()) > 0 else None

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
        logk = ctx.logKGrid().data

        ctx.data = Gas(name=name,
                       note=note,
                       revised=revised,
                       species_type=species_type,
                       keys=keys,
                       charge=charge,
                       volume=volume,
                       composition=composition,
                       dissociation=dissociation,
                       logk=logk)

    def exitSolidSolution(self, ctx: Data0Parser.SolidSolutionContext):
        name = ctx.speciesName().data
        note = ctx.speciesNote().data
        revised = ctx.dateRevised()[-1].data if len(ctx.dateRevised()) > 0 else None
        species_type = ctx.speciesType()[-1].data if len(ctx.speciesType()) > 0 else None
        keys = ctx.keys()[-1].data if len(ctx.keys()) > 0 else None
        composition = ctx.components().data
        model = ctx.solidSolutionModelSpec().data
        site_params = ctx.siteParams().data

        ctx.data = SolidSolution(name=name,
                                 note=note,
                                 revised=revised,
                                 species_type=species_type,
                                 keys=keys,
                                 composition=composition,
                                 model=model,
                                 site_params=site_params)
