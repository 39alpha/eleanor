all: parsers/Data0Parser.py

parsers/%Parser.py: grammars/%.g4
	antlr4 -Dlanguage=Python3 -Xexact-output-dir -o parsers -listener -no-visitor $<
