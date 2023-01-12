import antlr4
from . Data0Builder import Data0Builder
from . Data0Lexer import Data0Lexer
from . Data0Listener import Data0Listener
from . Data0Parser import Data0Parser

def parse_stream(stream, lexerCls, parserCls, builderCls, start, *args, **kwargs):
    lexer = lexerCls(stream)
    token_stream = antlr4.CommonTokenStream(lexer)
    parser = parserCls(token_stream)
    tree = getattr(parser, start)()
    builder = builderCls(*args, **kwargs)
    walker = antlr4.ParseTreeWalker()
    walker.walk(builder, tree)

    return builder.data, tree

def parse_file(fname, *args, encoding='ascii', **kwargs):
    file_stream = antlr4.FileStream(fname, encoding=encoding)
    return parse_stream(file_stream, *args, **kwargs)

def parse_data0(fname, *args, **kwargs):
    return parse_file(fname, Data0Lexer, Data0Parser, Data0Builder, 'data0', *args, **kwargs)
