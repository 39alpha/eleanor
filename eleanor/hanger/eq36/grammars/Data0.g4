grammar Data0;

NL        : [\r\n];
MAGIC     : ('data0'|'Data0'|'DATA0');
SEPERATOR : '+' '-'+;
WORD      : ~[\-.0-9 \t\r\n]~[. \t\r\n]*;
WS        : [ \t];
NUMBER    : SIGN? INTEGER | SIGN? FLOAT;
COMMENT   : [\r\n] '*' ~[\r\n]* -> skip;
SQ        : ['];

fragment SIGN : '+' | '-';
fragment INTEGER : '0'..'9'+;
fragment FLOAT   : '0'..'9'+ '.' '0'..'9'*;

data0
    : magicLine
      header
      paramsSection
      modelSection
      elementsSection
      basisSpeciesSection
      auxiliaryBasisSpeciesSection
      aqueousSpeciesSection
      solidsSection
      liquidsSection
      gasesSection
      solidSolutionsSection
      referenceSection
      theRest
      EOF;

magicLine
    : MAGIC '.' restOfLine
    | MAGIC NL+;

restOfLine : ~NL* NL+;

header : ~SEPERATOR* NL seperator;

seperator : SEPERATOR WS* NL;

paramsSection
    : (MAGIC | 'Miscellaneous')
      sectionHeader
      temperatures
      pressures
      modelParams
      eHLogK
      seperator;

sectionHeader : restOfLine seperator;

temperatures
    : 'Temperature limits' restOfLine
      temperatureRange
      'temperatures' restOfLine
      numberGrid;

temperatureRange : number number NL;

numberGrid : numberLine+;

numberLine : number+ WS* NL;

number
    : WS* NUMBER
    | WS* 'No_Data'
    | WS* 'NAN'
    | WS* 'nan'
    | WS* 'NaN'
    | WS* 'Nan';

pressures : 'pressures' restOfLine numberGrid;

modelParams : debyeHuckelModelParams | pitzerModelParams;

debyeHuckelModelParams
    : debyeHuckelA
      debyeHuckelB
      bdot
      cco2;

debyeHuckelA
    : 'debye huckel a' restOfLine numberGrid
    | 'debye huckel aphi' restOfLine numberGrid;

debyeHuckelB : 'debye huckel b' restOfLine numberGrid;

bdot : 'bdot' restOfLine numberGrid;

cco2 : 'cco2' restOfLine numberGrid;

pitzerModelParams : debyeHuckelA;

debyeHuckelAphi : 'debye huckel aphi' restOfLine numberGrid;

eHLogK : 'log k for eh reaction' restOfLine numberGrid;

modelSection : bdotSpeciesSection | pitzerCombinations;

bdotSpeciesSection : 'bdot parameters' sectionHeader bdotSpecies+ seperator;

bdotSpecies : bdotSpeciesName number number NL;

// It would be great if we could specify the length of the word to be 32
bdotSpeciesName : WORD | NUMBER '-' WORD;

pitzerCombinations
    : caCombinations
      ccPrimeAaPrimeCombinations
      ncNaCombinations
      nnCombinations
      nnPrimeCombinations
      ccPrimeAAaPrimeCCombinations
      ncaCombinations
      nnnPrimeCombinations;

caCombinations : 'ca combinations:' sectionHeader pitzerAlphaBetaCphiParams+;

ccPrimeAaPrimeCombinations : 'cc\' and aa\' combinations:' sectionHeader pitzerThetaParams+;

ncNaCombinations : 'nc and na combinations:' sectionHeader pitzerLambdaParams+;

nnCombinations : 'nn combinations:' sectionHeader pitzerLambdaMuParams+;

nnPrimeCombinations : 'nn\' combinations:' sectionHeader pitzerLambdaParams+;

ccPrimeAAaPrimeCCombinations : 'cc\'a and aa\'c combinations:' sectionHeader pitzerPsiParams+;

ncaCombinations : 'nca combinations:' sectionHeader pitzerZetaParams+;

nnnPrimeCombinations : 'nnn\' combinations:' sectionHeader pitzerMuParams+;

pitzerAlphaBetaCphiParams : pitzerTuple alpha1 alpha2 beta0 beta1 beta2 cphi seperator;

pitzerLambdaMuParams : pitzerTuple lambda_ mu seperator;

pitzerLambdaParams : pitzerTuple lambda_ seperator;

pitzerMuParams : pitzerTuple mu seperator;

pitzerPsiParams : pitzerTuple psi seperator;

pitzerThetaParams : pitzerTuple theta seperator;

pitzerZetaParams : pitzerTuple zeta seperator;

pitzerTuple : speciesName (WS+ speciesName)* restOfLine;

alpha1 : WS* 'alpha(1)' WS* '=' WS* number restOfLine;

alpha2 : WS* 'alpha(2)' WS* '=' WS* number restOfLine;

beta0 : WS* 'beta(0):' restOfLine a1 a2 a3 a4;

beta1 : WS* 'beta(1):' restOfLine a1 a2 a3 a4;

beta2 : WS* 'beta(2):' restOfLine a1 a2 a3 a4;

cphi : WS* 'Cphi:' restOfLine a1 a2 a3 a4;

theta : WS* 'theta:' restOfLine a1 a2 a3 a4;

lambda_ : WS* 'lambda:' restOfLine a1 a2 a3 a4;

mu : WS* 'mu:' restOfLine a1 a2 a3 a4;

psi : WS* 'psi:' restOfLine a1 a2 a3 a4;

zeta : WS* 'zeta:' restOfLine a1 a2 a3 a4;

a1 : WS* 'a1' WS* '=' WS* number restOfLine;

a2 : WS* 'a2' WS* '=' WS* number restOfLine;

a3 : WS* 'a3' WS* '=' WS* number restOfLine;

a4 : WS* 'a4' WS* '=' WS* number restOfLine;

elementsSection : 'elements' sectionHeader element+ seperator;

element : elementName number NL;

// It would be great if we could specify the length of the word to be 32
elementName : WORD;

basisSpeciesSection
    : 'basis species'
      sectionHeader
      basisSpecies+;

basisSpecies
    : speciesName
      speciesNote?
      (dateRevised|speciesType|keys|chargeLine|volumeLine|ympQualified)*
      composition
      seperator;

speciesName
    : WORD
    | NUMBER '-' WORD
    | WORD '.' speciesName
    | WORD '.' NUMBER speciesName?
    | WORD WS NUMBER speciesName?
    | WORD WS speciesName;

speciesNote : (WS WS+ ~NL+)? NL;

dateRevised : WS+ dateRevisedKey WS* '=' WS* date;

dateRevisedKey : ('date last revised' | 'revised');

date
    : NUMBER ('-' | '.') restOfLine
    | restOfLine;

speciesType : WS+ 'sp.type' WS+ '=' WS+ restOfLine;

keys : WS+ 'keys' WS+ '=' WS+ restOfLine;

chargeLine : WS* 'charge' WS* '=' WS* number WS* NL;

composition : number WS+ 'element(s):' restOfLine formulaGrid;

formulaGrid : formulaLine+;

formulaLine : formulaTerm+ WS* NL;

formulaTerm : number WS+ speciesName;

// Flesh out how to parse the unit?
volumeLine : WS+ 'V0PrTr' WS+ '=' WS+ volume restOfLine;

volume : number;

ympQualified : WS+ 'YMP' ~'='+ '=' WS+ WORD restOfLine;

auxiliaryBasisSpeciesSection : 'auxiliary basis species' sectionHeader auxiliaryBasisSpecies+;

auxiliaryBasisSpecies
    : speciesName
      speciesNote?
      (dateRevised|speciesType|keys|chargeLine|volumeLine|ympQualified)+
      composition
      dissociation
      logKGrid
      seperator;

dissociation : WS+ number WS+ 'species' restOfLine formulaGrid;

logKGrid : numberGrid;

aqueousSpeciesSection : 'aqueous species' sectionHeader aqueousSpecies*;

aqueousSpecies
    : speciesName
      speciesNote?
      (dateRevised|speciesType|keys|chargeLine|volumeLine|ympQualified)+
      composition
      dissociation
      logKGrid
      seperator;

solidsSection : 'solids' sectionHeader solid*;

solid
    : speciesName
      speciesNote?
      (dateRevised|speciesType|keys|chargeLine|volumeLine|ympQualified)+
      composition
      dissociation
      logKGrid
      seperator;

liquidsSection : 'liquids' sectionHeader liquid*;

liquid
    : speciesName
      speciesNote?
      (dateRevised|speciesType|keys|chargeLine|volumeLine|ympQualified)+
      composition
      dissociation
      logKGrid
      seperator;

gasesSection : 'gases' sectionHeader gas*;

gas
    : speciesName
      speciesNote?
      (dateRevised|speciesType|keys|chargeLine|volumeLine|ympQualified)+
      composition
      dissociation
      logKGrid
      seperator;

solidSolutionsSection : 'solid solutions' sectionHeader solidSolution*;

solidSolution
    : speciesName
      speciesNote?
      (dateRevised|speciesType|keys|ympQualified)+
      components
      solidSolutionModelSpec
      siteParams
      seperator;

components : number WS+ ('components'|'end members') restOfLine formulaGrid;

solidSolutionModelSpec : solidSolutionModelType solidSolutionModelParams;

solidSolutionModelType : WS+ 'type' WS+ '=' WS+ number WS* NL;

solidSolutionModelParams : number WS+ 'model parameters' restOfLine possiblyEmptyNumberGrid;

possiblyEmptyNumberGrid : numberLine*;

siteParams : number WS+ 'site parameters' restOfLine numberLine;

referenceSection : 'references' sectionHeader references 'stop.' (WS|NL)*;

references : ~'stop.'*;

theRest : ~EOF+;
