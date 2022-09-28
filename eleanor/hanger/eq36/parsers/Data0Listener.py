# Generated from grammars/Data0.g4 by ANTLR 4.11.1
from antlr4 import *
if __name__ is not None and "." in __name__:
    from .Data0Parser import Data0Parser
else:
    from Data0Parser import Data0Parser

# This class defines a complete listener for a parse tree produced by Data0Parser.
class Data0Listener(ParseTreeListener):

    # Enter a parse tree produced by Data0Parser#data0.
    def enterData0(self, ctx:Data0Parser.Data0Context):
        pass

    # Exit a parse tree produced by Data0Parser#data0.
    def exitData0(self, ctx:Data0Parser.Data0Context):
        pass


    # Enter a parse tree produced by Data0Parser#magic.
    def enterMagic(self, ctx:Data0Parser.MagicContext):
        pass

    # Exit a parse tree produced by Data0Parser#magic.
    def exitMagic(self, ctx:Data0Parser.MagicContext):
        pass


    # Enter a parse tree produced by Data0Parser#restOfLine.
    def enterRestOfLine(self, ctx:Data0Parser.RestOfLineContext):
        pass

    # Exit a parse tree produced by Data0Parser#restOfLine.
    def exitRestOfLine(self, ctx:Data0Parser.RestOfLineContext):
        pass


    # Enter a parse tree produced by Data0Parser#header.
    def enterHeader(self, ctx:Data0Parser.HeaderContext):
        pass

    # Exit a parse tree produced by Data0Parser#header.
    def exitHeader(self, ctx:Data0Parser.HeaderContext):
        pass


    # Enter a parse tree produced by Data0Parser#paramsSection.
    def enterParamsSection(self, ctx:Data0Parser.ParamsSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#paramsSection.
    def exitParamsSection(self, ctx:Data0Parser.ParamsSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#sectionHeader.
    def enterSectionHeader(self, ctx:Data0Parser.SectionHeaderContext):
        pass

    # Exit a parse tree produced by Data0Parser#sectionHeader.
    def exitSectionHeader(self, ctx:Data0Parser.SectionHeaderContext):
        pass


    # Enter a parse tree produced by Data0Parser#temperatures.
    def enterTemperatures(self, ctx:Data0Parser.TemperaturesContext):
        pass

    # Exit a parse tree produced by Data0Parser#temperatures.
    def exitTemperatures(self, ctx:Data0Parser.TemperaturesContext):
        pass


    # Enter a parse tree produced by Data0Parser#pressures.
    def enterPressures(self, ctx:Data0Parser.PressuresContext):
        pass

    # Exit a parse tree produced by Data0Parser#pressures.
    def exitPressures(self, ctx:Data0Parser.PressuresContext):
        pass


    # Enter a parse tree produced by Data0Parser#debyeHuckelA.
    def enterDebyeHuckelA(self, ctx:Data0Parser.DebyeHuckelAContext):
        pass

    # Exit a parse tree produced by Data0Parser#debyeHuckelA.
    def exitDebyeHuckelA(self, ctx:Data0Parser.DebyeHuckelAContext):
        pass


    # Enter a parse tree produced by Data0Parser#debyeHuckelB.
    def enterDebyeHuckelB(self, ctx:Data0Parser.DebyeHuckelBContext):
        pass

    # Exit a parse tree produced by Data0Parser#debyeHuckelB.
    def exitDebyeHuckelB(self, ctx:Data0Parser.DebyeHuckelBContext):
        pass


    # Enter a parse tree produced by Data0Parser#bdot.
    def enterBdot(self, ctx:Data0Parser.BdotContext):
        pass

    # Exit a parse tree produced by Data0Parser#bdot.
    def exitBdot(self, ctx:Data0Parser.BdotContext):
        pass


    # Enter a parse tree produced by Data0Parser#cco2.
    def enterCco2(self, ctx:Data0Parser.Cco2Context):
        pass

    # Exit a parse tree produced by Data0Parser#cco2.
    def exitCco2(self, ctx:Data0Parser.Cco2Context):
        pass


    # Enter a parse tree produced by Data0Parser#eHLogK.
    def enterEHLogK(self, ctx:Data0Parser.EHLogKContext):
        pass

    # Exit a parse tree produced by Data0Parser#eHLogK.
    def exitEHLogK(self, ctx:Data0Parser.EHLogKContext):
        pass


    # Enter a parse tree produced by Data0Parser#bdotSpeciesSection.
    def enterBdotSpeciesSection(self, ctx:Data0Parser.BdotSpeciesSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#bdotSpeciesSection.
    def exitBdotSpeciesSection(self, ctx:Data0Parser.BdotSpeciesSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#bdotSpecies.
    def enterBdotSpecies(self, ctx:Data0Parser.BdotSpeciesContext):
        pass

    # Exit a parse tree produced by Data0Parser#bdotSpecies.
    def exitBdotSpecies(self, ctx:Data0Parser.BdotSpeciesContext):
        pass


    # Enter a parse tree produced by Data0Parser#elementsSection.
    def enterElementsSection(self, ctx:Data0Parser.ElementsSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#elementsSection.
    def exitElementsSection(self, ctx:Data0Parser.ElementsSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#element.
    def enterElement(self, ctx:Data0Parser.ElementContext):
        pass

    # Exit a parse tree produced by Data0Parser#element.
    def exitElement(self, ctx:Data0Parser.ElementContext):
        pass


    # Enter a parse tree produced by Data0Parser#basisSpeciesSection.
    def enterBasisSpeciesSection(self, ctx:Data0Parser.BasisSpeciesSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#basisSpeciesSection.
    def exitBasisSpeciesSection(self, ctx:Data0Parser.BasisSpeciesSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#chargeLine.
    def enterChargeLine(self, ctx:Data0Parser.ChargeLineContext):
        pass

    # Exit a parse tree produced by Data0Parser#chargeLine.
    def exitChargeLine(self, ctx:Data0Parser.ChargeLineContext):
        pass


    # Enter a parse tree produced by Data0Parser#composition.
    def enterComposition(self, ctx:Data0Parser.CompositionContext):
        pass

    # Exit a parse tree produced by Data0Parser#composition.
    def exitComposition(self, ctx:Data0Parser.CompositionContext):
        pass


    # Enter a parse tree produced by Data0Parser#formulaLine.
    def enterFormulaLine(self, ctx:Data0Parser.FormulaLineContext):
        pass

    # Exit a parse tree produced by Data0Parser#formulaLine.
    def exitFormulaLine(self, ctx:Data0Parser.FormulaLineContext):
        pass


    # Enter a parse tree produced by Data0Parser#formulaTerm.
    def enterFormulaTerm(self, ctx:Data0Parser.FormulaTermContext):
        pass

    # Exit a parse tree produced by Data0Parser#formulaTerm.
    def exitFormulaTerm(self, ctx:Data0Parser.FormulaTermContext):
        pass


    # Enter a parse tree produced by Data0Parser#auxiliaryBasisSpeciesSection.
    def enterAuxiliaryBasisSpeciesSection(self, ctx:Data0Parser.AuxiliaryBasisSpeciesSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#auxiliaryBasisSpeciesSection.
    def exitAuxiliaryBasisSpeciesSection(self, ctx:Data0Parser.AuxiliaryBasisSpeciesSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#dissociation.
    def enterDissociation(self, ctx:Data0Parser.DissociationContext):
        pass

    # Exit a parse tree produced by Data0Parser#dissociation.
    def exitDissociation(self, ctx:Data0Parser.DissociationContext):
        pass


    # Enter a parse tree produced by Data0Parser#possiblyEmptyNumberGrid.
    def enterPossiblyEmptyNumberGrid(self, ctx:Data0Parser.PossiblyEmptyNumberGridContext):
        pass

    # Exit a parse tree produced by Data0Parser#possiblyEmptyNumberGrid.
    def exitPossiblyEmptyNumberGrid(self, ctx:Data0Parser.PossiblyEmptyNumberGridContext):
        pass


    # Enter a parse tree produced by Data0Parser#numberGrid.
    def enterNumberGrid(self, ctx:Data0Parser.NumberGridContext):
        pass

    # Exit a parse tree produced by Data0Parser#numberGrid.
    def exitNumberGrid(self, ctx:Data0Parser.NumberGridContext):
        pass


    # Enter a parse tree produced by Data0Parser#numberLine.
    def enterNumberLine(self, ctx:Data0Parser.NumberLineContext):
        pass

    # Exit a parse tree produced by Data0Parser#numberLine.
    def exitNumberLine(self, ctx:Data0Parser.NumberLineContext):
        pass


    # Enter a parse tree produced by Data0Parser#aqueousSpeciesSection.
    def enterAqueousSpeciesSection(self, ctx:Data0Parser.AqueousSpeciesSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#aqueousSpeciesSection.
    def exitAqueousSpeciesSection(self, ctx:Data0Parser.AqueousSpeciesSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#solidsSection.
    def enterSolidsSection(self, ctx:Data0Parser.SolidsSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#solidsSection.
    def exitSolidsSection(self, ctx:Data0Parser.SolidsSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#liquidsSection.
    def enterLiquidsSection(self, ctx:Data0Parser.LiquidsSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#liquidsSection.
    def exitLiquidsSection(self, ctx:Data0Parser.LiquidsSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#gasesSection.
    def enterGasesSection(self, ctx:Data0Parser.GasesSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#gasesSection.
    def exitGasesSection(self, ctx:Data0Parser.GasesSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#volumeLine.
    def enterVolumeLine(self, ctx:Data0Parser.VolumeLineContext):
        pass

    # Exit a parse tree produced by Data0Parser#volumeLine.
    def exitVolumeLine(self, ctx:Data0Parser.VolumeLineContext):
        pass


    # Enter a parse tree produced by Data0Parser#solidSolutionsSection.
    def enterSolidSolutionsSection(self, ctx:Data0Parser.SolidSolutionsSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#solidSolutionsSection.
    def exitSolidSolutionsSection(self, ctx:Data0Parser.SolidSolutionsSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#components.
    def enterComponents(self, ctx:Data0Parser.ComponentsContext):
        pass

    # Exit a parse tree produced by Data0Parser#components.
    def exitComponents(self, ctx:Data0Parser.ComponentsContext):
        pass


    # Enter a parse tree produced by Data0Parser#modelSpec.
    def enterModelSpec(self, ctx:Data0Parser.ModelSpecContext):
        pass

    # Exit a parse tree produced by Data0Parser#modelSpec.
    def exitModelSpec(self, ctx:Data0Parser.ModelSpecContext):
        pass


    # Enter a parse tree produced by Data0Parser#modelType.
    def enterModelType(self, ctx:Data0Parser.ModelTypeContext):
        pass

    # Exit a parse tree produced by Data0Parser#modelType.
    def exitModelType(self, ctx:Data0Parser.ModelTypeContext):
        pass


    # Enter a parse tree produced by Data0Parser#modelParams.
    def enterModelParams(self, ctx:Data0Parser.ModelParamsContext):
        pass

    # Exit a parse tree produced by Data0Parser#modelParams.
    def exitModelParams(self, ctx:Data0Parser.ModelParamsContext):
        pass


    # Enter a parse tree produced by Data0Parser#siteParams.
    def enterSiteParams(self, ctx:Data0Parser.SiteParamsContext):
        pass

    # Exit a parse tree produced by Data0Parser#siteParams.
    def exitSiteParams(self, ctx:Data0Parser.SiteParamsContext):
        pass


    # Enter a parse tree produced by Data0Parser#dateLastRevised.
    def enterDateLastRevised(self, ctx:Data0Parser.DateLastRevisedContext):
        pass

    # Exit a parse tree produced by Data0Parser#dateLastRevised.
    def exitDateLastRevised(self, ctx:Data0Parser.DateLastRevisedContext):
        pass


    # Enter a parse tree produced by Data0Parser#keys.
    def enterKeys(self, ctx:Data0Parser.KeysContext):
        pass

    # Exit a parse tree produced by Data0Parser#keys.
    def exitKeys(self, ctx:Data0Parser.KeysContext):
        pass


    # Enter a parse tree produced by Data0Parser#speciesType.
    def enterSpeciesType(self, ctx:Data0Parser.SpeciesTypeContext):
        pass

    # Exit a parse tree produced by Data0Parser#speciesType.
    def exitSpeciesType(self, ctx:Data0Parser.SpeciesTypeContext):
        pass


    # Enter a parse tree produced by Data0Parser#brackets.
    def enterBrackets(self, ctx:Data0Parser.BracketsContext):
        pass

    # Exit a parse tree produced by Data0Parser#brackets.
    def exitBrackets(self, ctx:Data0Parser.BracketsContext):
        pass


    # Enter a parse tree produced by Data0Parser#speciesJunk.
    def enterSpeciesJunk(self, ctx:Data0Parser.SpeciesJunkContext):
        pass

    # Exit a parse tree produced by Data0Parser#speciesJunk.
    def exitSpeciesJunk(self, ctx:Data0Parser.SpeciesJunkContext):
        pass


    # Enter a parse tree produced by Data0Parser#referenceSection.
    def enterReferenceSection(self, ctx:Data0Parser.ReferenceSectionContext):
        pass

    # Exit a parse tree produced by Data0Parser#referenceSection.
    def exitReferenceSection(self, ctx:Data0Parser.ReferenceSectionContext):
        pass


    # Enter a parse tree produced by Data0Parser#references.
    def enterReferences(self, ctx:Data0Parser.ReferencesContext):
        pass

    # Exit a parse tree produced by Data0Parser#references.
    def exitReferences(self, ctx:Data0Parser.ReferencesContext):
        pass


    # Enter a parse tree produced by Data0Parser#basisSpecies.
    def enterBasisSpecies(self, ctx:Data0Parser.BasisSpeciesContext):
        pass

    # Exit a parse tree produced by Data0Parser#basisSpecies.
    def exitBasisSpecies(self, ctx:Data0Parser.BasisSpeciesContext):
        pass


    # Enter a parse tree produced by Data0Parser#auxiliaryBasisSpecies.
    def enterAuxiliaryBasisSpecies(self, ctx:Data0Parser.AuxiliaryBasisSpeciesContext):
        pass

    # Exit a parse tree produced by Data0Parser#auxiliaryBasisSpecies.
    def exitAuxiliaryBasisSpecies(self, ctx:Data0Parser.AuxiliaryBasisSpeciesContext):
        pass


    # Enter a parse tree produced by Data0Parser#aqueousSpecies.
    def enterAqueousSpecies(self, ctx:Data0Parser.AqueousSpeciesContext):
        pass

    # Exit a parse tree produced by Data0Parser#aqueousSpecies.
    def exitAqueousSpecies(self, ctx:Data0Parser.AqueousSpeciesContext):
        pass


    # Enter a parse tree produced by Data0Parser#solid.
    def enterSolid(self, ctx:Data0Parser.SolidContext):
        pass

    # Exit a parse tree produced by Data0Parser#solid.
    def exitSolid(self, ctx:Data0Parser.SolidContext):
        pass


    # Enter a parse tree produced by Data0Parser#liquid.
    def enterLiquid(self, ctx:Data0Parser.LiquidContext):
        pass

    # Exit a parse tree produced by Data0Parser#liquid.
    def exitLiquid(self, ctx:Data0Parser.LiquidContext):
        pass


    # Enter a parse tree produced by Data0Parser#gas.
    def enterGas(self, ctx:Data0Parser.GasContext):
        pass

    # Exit a parse tree produced by Data0Parser#gas.
    def exitGas(self, ctx:Data0Parser.GasContext):
        pass


    # Enter a parse tree produced by Data0Parser#solidSolution.
    def enterSolidSolution(self, ctx:Data0Parser.SolidSolutionContext):
        pass

    # Exit a parse tree produced by Data0Parser#solidSolution.
    def exitSolidSolution(self, ctx:Data0Parser.SolidSolutionContext):
        pass



del Data0Parser