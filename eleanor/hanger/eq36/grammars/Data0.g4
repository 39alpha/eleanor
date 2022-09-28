grammar Data0;

NL        : [\r\n];
MAGIC     : ('data0');
SEPERATOR : ('+--------------------------------------------------------------------');
OPAREN    : '(';
CPAREN    : ')';
OBRACK    : '[';
CBRACK    : ']';
SEMICOLON : ';';
COLON     : ':';
HYPHEN    : '-';
COMMA     : ',';
SLASH     : '/';
DQUOTE    : '"';
SQUOTE    : '\'';
CARET     : '^';
WORD      : ('a'..'z'|'A'..'Z'|'(')('a'..'z'|'A'..'Z'|'0'..'9'|'('..')'|'+'|'-'|'*'|','|'_'|':')*;
WS        : [ \t]+ -> skip;
NUMBER    : SIGN? INTEGER | SIGN? FLOAT;
COMMENT   : [\r\n] '*' ~[\r\n]* -> skip;
ANY       : .;

fragment WORDISH : ;
fragment SIGN : '+' | '-';
fragment INTEGER : '0'..'9'+;
fragment FLOAT   : '0'..'9'+ '.' '0'..'9'+;

data0
    : magic
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

magic
    : MAGIC '.' restOfLine NL+
    | MAGIC NL+;

restOfLine : ~NL*;

header : ~SEPERATOR* NL SEPERATOR NL;

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
      SEPERATOR
      NL;

sectionHeader : restOfLine NL SEPERATOR NL;

temperatures
    : 'Temperature limits'
      restOfLine NL
      numberLine
      'temperatures'
      restOfLine NL
      numberGrid;

pressures : 'pressures' restOfLine NL numberGrid;

debyeHuckelA : 'debye huckel a' restOfLine NL numberGrid;

debyeHuckelB : 'debye huckel b' restOfLine NL numberGrid;

bdot : 'bdot' restOfLine NL numberGrid;

cco2 : 'cco2' restOfLine NL numberGrid;

eHLogK : 'log k for eh reaction' restOfLine NL numberGrid;

bdotSpeciesSection : 'bdot' sectionHeader bdotSpecies+ SEPERATOR NL;

bdotSpecies : WORD NUMBER NUMBER NL;

elementsSection : 'elements' sectionHeader element+ SEPERATOR NL;

element : WORD NUMBER NL;

basisSpeciesSection : sectionHeader basisSpecies+;

chargeLine : 'charge' '=' NUMBER NL;

composition : NUMBER 'element(s):' NL formulaLine+;

formulaLine : formulaTerm+ NL;

formulaTerm : NUMBER WORD;

auxiliaryBasisSpeciesSection : 'auxiliary' sectionHeader auxiliaryBasisSpecies+;

dissociation : NUMBER 'species' restOfLine NL formulaLine+;

possiblyEmptyNumberGrid : numberLine*;

numberGrid : numberLine+;

numberLine : NUMBER+ NL;

aqueousSpeciesSection : 'aqueous' sectionHeader aqueousSpecies+;

solidsSection : 'solids' sectionHeader solid+;

liquidsSection : 'liquids' sectionHeader liquid+;

gasesSection : 'gases' sectionHeader gas+;

volumeLine : 'V0PrTr' '=' NUMBER restOfLine NL;

solidSolutionsSection : 'solid solutions' sectionHeader solidSolution+;

components : NUMBER ('components'|'end members') NL formulaLine+;

modelSpec : modelType modelParams;

modelType : 'type' '=' NUMBER NL;

modelParams : NUMBER 'model parameters' NL possiblyEmptyNumberGrid;

siteParams : NUMBER 'site parameters' NL numberLine;

dateLastRevised : 'date last revised' '=' restOfLine NL;

keys : 'keys' '=' restOfLine NL;

speciesType : 'sp.type' '=' restOfLine NL;

brackets : OBRACK CBRACK NL;

speciesJunk : (dateLastRevised|keys|speciesType|brackets)*;

referenceSection : 'references' sectionHeader references 'stop.' NL+;

references : ~'stop.'*;

basisSpecies
    : WORD
      restOfLine
      NL
      speciesJunk
      (chargeLine|volumeLine)+
      composition
      SEPERATOR
      NL;

auxiliaryBasisSpecies
    : WORD
      restOfLine
      NL
      speciesJunk
      (chargeLine|volumeLine)+
      composition
      dissociation
      numberGrid
      SEPERATOR
      NL;

aqueousSpecies
    : WORD
      restOfLine
      NL
      speciesJunk
      (chargeLine|volumeLine)+
      composition
      dissociation
      numberGrid
      SEPERATOR
      NL;

solid
    : WORD
      restOfLine
      NL
      speciesJunk
      (chargeLine|volumeLine)+
      composition
      dissociation
      numberGrid
      SEPERATOR
      NL;

liquid
    : WORD
      restOfLine
      NL
      speciesJunk
      (chargeLine|volumeLine)+
      composition
      dissociation
      numberGrid
      SEPERATOR
      NL;

gas
    : WORD
      restOfLine
      NL
      speciesJunk
      (chargeLine|volumeLine)+
      composition
      dissociation
      numberGrid
      SEPERATOR
      NL;

solidSolution
    : WORD
      restOfLine
      NL
      speciesJunk
      components
      modelSpec
      siteParams
      SEPERATOR
      NL;
