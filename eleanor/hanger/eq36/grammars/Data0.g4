grammar Data0;

NL        : [\r\n];
MAGIC     : ('data0'|'Data0'|'DATA0');
SEPERATOR : '+' '-'+;
WORD      : ~[\-.0-9 \t\r\n]~[. \t\r\n]*;
WS        : [ \t]+;
NUMBER    : SIGN? INTEGER | SIGN? FLOAT;
COMMENT   : [\r\n] '*' ~[\r\n]* -> skip;

fragment SIGN : '+' | '-';
fragment INTEGER : '0'..'9'+;
fragment FLOAT   : '0'..'9'+ '.' '0'..'9'+;

data0
    : magicLine
      header
      paramsSection
      bdotSpeciesSection
      elementsSection
      basisSpeciesSection
      auxiliaryBasisSpeciesSection
      aqueousSpeciesSection
      solidsSection
      liquidsSection
      gasesSection
      solidSolutionsSection
      referenceSection
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
      debyeHuckelA
      debyeHuckelB
      bdot
      cco2
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

number : WS* NUMBER;

pressures : 'pressures' restOfLine numberGrid;

debyeHuckelA : 'debye huckel a' restOfLine numberGrid;

debyeHuckelB : 'debye huckel b' restOfLine numberGrid;

bdot : 'bdot' restOfLine numberGrid;

cco2 : 'cco2' restOfLine numberGrid;

eHLogK : 'log k for eh reaction' restOfLine numberGrid;

bdotSpeciesSection : 'bdot parameters' sectionHeader bdotSpecies+ seperator;

bdotSpecies : bdotSpeciesName number number NL;

// It would be great if we could specify the length of the word to be 32
bdotSpeciesName : WORD;

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
      speciesNote
      (dateRevised|speciesType|keys)+
      (chargeLine|volumeLine)+
      composition
      seperator;

// It would be great if we could specify the length of the word to be 32
speciesName : WORD;

speciesNote : ~NL* NL;

dateRevised :
    WS
    dateRevisedKey
    WS*
    '='
    WS*
    date;

dateRevisedKey : ('date last revised' | 'revised');

date
    : NUMBER ('-' | '.') restOfLine
    | restOfLine;

speciesType : WS 'sp.type' WS '=' WS restOfLine;

keys : WS 'keys' WS '=' WS restOfLine;

chargeLine : WS 'charge' WS '=' WS number WS* NL;

composition : number WS 'element(s):' restOfLine formulaGrid;

formulaGrid : formulaLine+;

formulaLine : formulaTerm+ WS* NL;

formulaTerm : number WS componentName;

componentName : WORD;

// Flesh out how to parse the unit?
volumeLine : WS 'V0PrTr' WS '=' WS volume restOfLine;

volume : number;

auxiliaryBasisSpeciesSection : 'auxiliary basis species' sectionHeader auxiliaryBasisSpecies+;

auxiliaryBasisSpecies
    : speciesName
      speciesNote
      (dateRevised|speciesType|keys)+
      (chargeLine|volumeLine)+
      composition
      dissociation
      logKGrid
      seperator;

dissociation : WS number WS 'species' restOfLine formulaGrid;

logKGrid : numberGrid;

aqueousSpeciesSection : 'aqueous species' sectionHeader aqueousSpecies+;

aqueousSpecies
    : speciesName
      speciesNote
      (dateRevised|speciesType|keys)+
      (chargeLine|volumeLine)+
      composition
      dissociation
      logKGrid
      seperator;

solidsSection : 'solids' sectionHeader solid+;

solid
    : speciesName
      speciesNote
      (dateRevised|speciesType|keys)+
      (chargeLine|volumeLine)+
      composition
      dissociation
      logKGrid
      seperator;

liquidsSection : 'liquids' sectionHeader liquid+;

liquid
    : speciesName
      speciesNote
      (dateRevised|speciesType|keys)+
      (chargeLine|volumeLine)+
      composition
      dissociation
      logKGrid
      seperator;

gasesSection : 'gases' sectionHeader gas+;

gas
    : speciesName
      speciesNote
      (dateRevised|speciesType|keys)+
      (chargeLine|volumeLine)+
      composition
      dissociation
      logKGrid
      seperator;

solidSolutionsSection : 'solid solutions' sectionHeader solidSolution+;

solidSolution
    : speciesName
      speciesNote
      (dateRevised|speciesType|keys)+
      components
      modelSpec
      siteParams
      seperator;

components : number WS ('components'|'end members') restOfLine formulaGrid;

modelSpec : modelType modelParams;

modelType : WS 'type' WS '=' WS number WS* NL;

modelParams : number WS 'model parameters' restOfLine possiblyEmptyNumberGrid;

possiblyEmptyNumberGrid : numberLine*;

siteParams : number WS 'site parameters' restOfLine numberLine;

referenceSection : 'references' sectionHeader references 'stop.' (WS|NL)*;

references : ~'stop.'*;
