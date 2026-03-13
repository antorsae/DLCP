/* A Bison parser, made by GNU Bison 3.7.6.  */

/* Bison implementation for Yacc-like parsers in C

   Copyright (C) 1984, 1989-1990, 2000-2015, 2018-2021 Free Software Foundation,
   Inc.

   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program.  If not, see <https://www.gnu.org/licenses/>.  */

/* As a special exception, you may create a larger work that contains
   part or all of the Bison parser skeleton and distribute that work
   under terms of your choice, so long as that work isn't itself a
   parser generator using the skeleton or a modified version thereof
   as a parser skeleton.  Alternatively, if you modify or redistribute
   the parser skeleton itself, you may (at your option) remove this
   special exception, which will cause the skeleton and the resulting
   Bison output files to be licensed under the GNU General Public
   License without this special exception.

   This special exception was added by the Free Software Foundation in
   version 2.2 of Bison.  */

/* C LALR(1) parser skeleton written by Richard Stallman, by
   simplifying the original so-called "semantic" parser.  */

/* DO NOT RELY ON FEATURES THAT ARE NOT DOCUMENTED in the manual,
   especially those whose name start with YY_ or yy_.  They are
   private implementation details that can be changed or removed.  */

/* All symbols defined below should begin with yy or YY, to avoid
   infringing on user name space.  This should be done even for local
   variables, as they might otherwise be expanded by user macros.
   There are some unavoidable exceptions within include files to
   define necessary library symbols; they are noted "INFRINGES ON
   USER NAME SPACE" below.  */

/* Identify Bison output, and Bison version.  */
#define YYBISON 30706

/* Bison version string.  */
#define YYBISON_VERSION "3.7.6"

/* Skeleton name.  */
#define YYSKELETON_NAME "yacc.c"

/* Pure parsers.  */
#define YYPURE 1

/* Push parsers.  */
#define YYPUSH 0

/* Pull parsers.  */
#define YYPULL 1




/* First part of user prologue.  */
#line 2 "parse.yy"

/* Parser for gpsim
   Copyright (C) 1999 Scott Dattalo

This file is part of gpsim.

gpsim is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2, or (at your option)
any later version.

gpsim is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with gpsim; see the file COPYING.  If not, write to
the Free Software Foundation, 59 Temple Place - Suite 330,
Boston, MA 02111-1307, USA.  */

#include <stdio.h>
#include <iostream>
#include <iomanip>
#include <string>
#include <list>
#include <vector>
#include <typeinfo>
#include <unistd.h>
#include <glib.h>

#include "misc.h"
#include "command.h"

#include "cmd_attach.h"
#include "cmd_break.h"
#include "cmd_bus.h"
#include "cmd_clear.h"
#include "cmd_disasm.h"
#include "cmd_dump.h"
#include "cmd_frequency.h"
#include "cmd_help.h"
#include "cmd_list.h"
#include "cmd_load.h"
#include "cmd_log.h"
#include "cmd_node.h"
#include "cmd_macro.h"
#include "cmd_module.h"
#include "cmd_processor.h"
#include "cmd_quit.h"
#include "cmd_reset.h"
#include "cmd_run.h"
#include "cmd_set.h"
#include "cmd_step.h"
#include "cmd_shell.h"
#include "cmd_stimulus.h"
#include "cmd_symbol.h"
#include "cmd_trace.h"
#include "cmd_version.h"
#include "cmd_x.h"
#include "cmd_icd.h"
#include "../src/expr.h"
#include "../src/operator.h"

#include "../src/symbol.h"
#include "../src/stimuli.h"
#include "../src/processor.h"

extern void lexer_setMacroBodyMode();
extern void lexer_InvokeMacro(Macro *m);
extern void lexer_setDeclarationMode();

#define YYERROR_VERBOSE

extern char *yytext;
int quit_parse=0;
int abort_gpsim=0;
int parser_warnings;
int parser_spanning_lines=0;
int gAbortParserOnSyntaxError=0;
extern int use_gui;
extern int quit_state;

extern command *getLastKnownCommand();
extern void init_cmd_state();
extern const char * GetLastFullCommand();
// From scan.ll
void FlushLexerBuffer();

void yyerror(const char *message)
{
  const char *last = GetLastFullCommand();
  if (last)
  {
     int n = strlen(last);
     char *pt = strdup(last);
     if (n > 0 && *(pt+n-1) == '\n')
	*(pt+n-1) = 0;
     printf("***ERROR: %s while parsing:\n\t'%s'\n",message, pt);
     free(pt);
  }
  else
      printf("***ERROR: %s \n",message);
  init_cmd_state();
  // JRH - I added this hoping that it is an appropriate
  //       place to clear the lexer buffer. An example of
  //       failed command where this is needed is to index
  //       into an undefined symbol. (i.e. undefinedsymbol[0])
  FlushLexerBuffer();
}


int toInt(Expression *expr)
{

  try {
    if(expr) {

      Value *v = expr->evaluate();
      if (v) {
	int i;
	v->get(i);
        delete v;
	return i;
      }
    }

  }

  catch (Error const &err) {
    std::cout << "ERROR:" << err.what() << '\n';
  }

  return -1;
}


#line 209 "parse.cc"

# ifndef YY_CAST
#  ifdef __cplusplus
#   define YY_CAST(Type, Val) static_cast<Type> (Val)
#   define YY_REINTERPRET_CAST(Type, Val) reinterpret_cast<Type> (Val)
#  else
#   define YY_CAST(Type, Val) ((Type) (Val))
#   define YY_REINTERPRET_CAST(Type, Val) ((Type) (Val))
#  endif
# endif
# ifndef YY_NULLPTR
#  if defined __cplusplus
#   if 201103L <= __cplusplus
#    define YY_NULLPTR nullptr
#   else
#    define YY_NULLPTR 0
#   endif
#  else
#   define YY_NULLPTR ((void*)0)
#  endif
# endif

/* Use api.header.include to #include this header
   instead of duplicating it here.  */
#ifndef YY_YY_PARSE_H_INCLUDED
# define YY_YY_PARSE_H_INCLUDED
/* Debug traces.  */
#ifndef YYDEBUG
# define YYDEBUG 1
#endif
#if YYDEBUG
extern int yydebug;
#endif

/* Token kinds.  */
#ifndef YYTOKENTYPE
# define YYTOKENTYPE
  enum yytokentype
  {
    YYEMPTY = -2,
    YYEOF = 0,                     /* "end of file"  */
    YYerror = 256,                 /* error  */
    YYUNDEF = 257,                 /* "invalid token"  */
    ABORT = 258,                   /* ABORT  */
    ATTACH = 259,                  /* ATTACH  */
    BREAK = 260,                   /* BREAK  */
    BUS = 261,                     /* BUS  */
    CLEAR = 262,                   /* CLEAR  */
    DISASSEMBLE = 263,             /* DISASSEMBLE  */
    DUMP = 264,                    /* DUMP  */
    ENDM = 265,                    /* ENDM  */
    FREQUENCY = 266,               /* FREQUENCY  */
    HELP = 267,                    /* HELP  */
    LOAD = 268,                    /* LOAD  */
    LOG = 269,                     /* LOG  */
    LIST = 270,                    /* LIST  */
    NODE = 271,                    /* NODE  */
    MACRO = 272,                   /* MACRO  */
    MODULE = 273,                  /* MODULE  */
    PROCESSOR = 274,               /* PROCESSOR  */
    QUIT = 275,                    /* QUIT  */
    RESET = 276,                   /* RESET  */
    RUN = 277,                     /* RUN  */
    SET = 278,                     /* SET  */
    SHELL = 279,                   /* SHELL  */
    STEP = 280,                    /* STEP  */
    STIMULUS = 281,                /* STIMULUS  */
    SYMBOL = 282,                  /* SYMBOL  */
    TRACE = 283,                   /* TRACE  */
    gpsim_VERSION = 284,           /* gpsim_VERSION  */
    X = 285,                       /* X  */
    ICD = 286,                     /* ICD  */
    END_OF_COMMAND = 287,          /* END_OF_COMMAND  */
    MACROBODY_T = 288,             /* MACROBODY_T  */
    MACROINVOCATION_T = 289,       /* MACROINVOCATION_T  */
    INDIRECT = 290,                /* INDIRECT  */
    END_OF_INPUT = 291,            /* END_OF_INPUT  */
    BIT_FLAG = 292,                /* BIT_FLAG  */
    EXPRESSION_OPTION = 293,       /* EXPRESSION_OPTION  */
    NUMERIC_OPTION = 294,          /* NUMERIC_OPTION  */
    STRING_OPTION = 295,           /* STRING_OPTION  */
    CMD_SUBTYPE = 296,             /* CMD_SUBTYPE  */
    SYMBOL_OPTION = 297,           /* SYMBOL_OPTION  */
    LITERAL_INT_T = 298,           /* LITERAL_INT_T  */
    LITERAL_BOOL_T = 299,          /* LITERAL_BOOL_T  */
    LITERAL_FLOAT_T = 300,         /* LITERAL_FLOAT_T  */
    LITERAL_STRING_T = 301,        /* LITERAL_STRING_T  */
    LITERAL_ARRAY_T = 302,         /* LITERAL_ARRAY_T  */
    SYMBOL_T = 303,                /* SYMBOL_T  */
    GPSIMOBJECT_T = 304,           /* GPSIMOBJECT_T  */
    PORT_T = 305,                  /* PORT_T  */
    EQU_T = 306,                   /* EQU_T  */
    AND_T = 307,                   /* AND_T  */
    COLON_T = 308,                 /* COLON_T  */
    COMMENT_T = 309,               /* COMMENT_T  */
    DIV_T = 310,                   /* DIV_T  */
    EOLN_T = 311,                  /* EOLN_T  */
    MINUS_T = 312,                 /* MINUS_T  */
    MPY_T = 313,                   /* MPY_T  */
    OR_T = 314,                    /* OR_T  */
    PLUS_T = 315,                  /* PLUS_T  */
    SHL_T = 316,                   /* SHL_T  */
    SHR_T = 317,                   /* SHR_T  */
    XOR_T = 318,                   /* XOR_T  */
    INDEXERLEFT_T = 319,           /* INDEXERLEFT_T  */
    INDEXERRIGHT_T = 320,          /* INDEXERRIGHT_T  */
    DECLARE_TYPE = 321,            /* DECLARE_TYPE  */
    DECLARE_INT_T = 322,           /* DECLARE_INT_T  */
    DECLARE_FLOAT_T = 323,         /* DECLARE_FLOAT_T  */
    DECLARE_BOOL_T = 324,          /* DECLARE_BOOL_T  */
    DECLARE_CHAR_T = 325,          /* DECLARE_CHAR_T  */
    LOR_T = 326,                   /* LOR_T  */
    LAND_T = 327,                  /* LAND_T  */
    EQ_T = 328,                    /* EQ_T  */
    NE_T = 329,                    /* NE_T  */
    LT_T = 330,                    /* LT_T  */
    LE_T = 331,                    /* LE_T  */
    GT_T = 332,                    /* GT_T  */
    GE_T = 333,                    /* GE_T  */
    MIN_T = 334,                   /* MIN_T  */
    MAX_T = 335,                   /* MAX_T  */
    ABS_T = 336,                   /* ABS_T  */
    IND_T = 337,                   /* IND_T  */
    BIT_T = 338,                   /* BIT_T  */
    BITS_T = 339,                  /* BITS_T  */
    LOW_T = 340,                   /* LOW_T  */
    HIGH_T = 341,                  /* HIGH_T  */
    LADDR_T = 342,                 /* LADDR_T  */
    WORD_T = 343,                  /* WORD_T  */
    INDEXED_T = 344,               /* INDEXED_T  */
    LNOT_T = 345,                  /* LNOT_T  */
    ONESCOMP_T = 346,              /* ONESCOMP_T  */
    UNARYOP_PREC = 347,            /* UNARYOP_PREC  */
    POW_T = 348,                   /* POW_T  */
    REG_T = 349                    /* REG_T  */
  };
  typedef enum yytokentype yytoken_kind_t;
#endif
/* Token kinds.  */
#define YYEMPTY -2
#define YYEOF 0
#define YYerror 256
#define YYUNDEF 257
#define ABORT 258
#define ATTACH 259
#define BREAK 260
#define BUS 261
#define CLEAR 262
#define DISASSEMBLE 263
#define DUMP 264
#define ENDM 265
#define FREQUENCY 266
#define HELP 267
#define LOAD 268
#define LOG 269
#define LIST 270
#define NODE 271
#define MACRO 272
#define MODULE 273
#define PROCESSOR 274
#define QUIT 275
#define RESET 276
#define RUN 277
#define SET 278
#define SHELL 279
#define STEP 280
#define STIMULUS 281
#define SYMBOL 282
#define TRACE 283
#define gpsim_VERSION 284
#define X 285
#define ICD 286
#define END_OF_COMMAND 287
#define MACROBODY_T 288
#define MACROINVOCATION_T 289
#define INDIRECT 290
#define END_OF_INPUT 291
#define BIT_FLAG 292
#define EXPRESSION_OPTION 293
#define NUMERIC_OPTION 294
#define STRING_OPTION 295
#define CMD_SUBTYPE 296
#define SYMBOL_OPTION 297
#define LITERAL_INT_T 298
#define LITERAL_BOOL_T 299
#define LITERAL_FLOAT_T 300
#define LITERAL_STRING_T 301
#define LITERAL_ARRAY_T 302
#define SYMBOL_T 303
#define GPSIMOBJECT_T 304
#define PORT_T 305
#define EQU_T 306
#define AND_T 307
#define COLON_T 308
#define COMMENT_T 309
#define DIV_T 310
#define EOLN_T 311
#define MINUS_T 312
#define MPY_T 313
#define OR_T 314
#define PLUS_T 315
#define SHL_T 316
#define SHR_T 317
#define XOR_T 318
#define INDEXERLEFT_T 319
#define INDEXERRIGHT_T 320
#define DECLARE_TYPE 321
#define DECLARE_INT_T 322
#define DECLARE_FLOAT_T 323
#define DECLARE_BOOL_T 324
#define DECLARE_CHAR_T 325
#define LOR_T 326
#define LAND_T 327
#define EQ_T 328
#define NE_T 329
#define LT_T 330
#define LE_T 331
#define GT_T 332
#define GE_T 333
#define MIN_T 334
#define MAX_T 335
#define ABS_T 336
#define IND_T 337
#define BIT_T 338
#define BITS_T 339
#define LOW_T 340
#define HIGH_T 341
#define LADDR_T 342
#define WORD_T 343
#define INDEXED_T 344
#define LNOT_T 345
#define ONESCOMP_T 346
#define UNARYOP_PREC 347
#define POW_T 348
#define REG_T 349

/* Value type.  */
#if ! defined YYSTYPE && ! defined YYSTYPE_IS_DECLARED
union YYSTYPE
{
#line 146 "parse.yy"

  guint32              i;
  guint64             li;
  float                f;
  char                *s;
  cmd_options        *co;
  cmd_options_num   *con;
  cmd_options_str   *cos;
  cmd_options_expr  *coe;

  BinaryOperator*           BinaryOperator_P;
  Boolean*                  Boolean_P;
  Expression*               Expression_P;
  Float*                    Float_P;
  Integer*                  Integer_P;
  String*                   String_P;
  gpsimObject*              Symbol_P;
  gpsimObject*              gpsimObject_P;

  StringList_t             *StringList_P;
  ExprList_t               *ExprList_P;
  gpsimObjectList_t        *gpsimObjectList_P;

  Macro                    *Macro_P;

#line 476 "parse.cc"

};
typedef union YYSTYPE YYSTYPE;
# define YYSTYPE_IS_TRIVIAL 1
# define YYSTYPE_IS_DECLARED 1
#endif



int yyparse (void);

#endif /* !YY_YY_PARSE_H_INCLUDED  */
/* Symbol kind.  */
enum yysymbol_kind_t
{
  YYSYMBOL_YYEMPTY = -2,
  YYSYMBOL_YYEOF = 0,                      /* "end of file"  */
  YYSYMBOL_YYerror = 1,                    /* error  */
  YYSYMBOL_YYUNDEF = 2,                    /* "invalid token"  */
  YYSYMBOL_ABORT = 3,                      /* ABORT  */
  YYSYMBOL_ATTACH = 4,                     /* ATTACH  */
  YYSYMBOL_BREAK = 5,                      /* BREAK  */
  YYSYMBOL_BUS = 6,                        /* BUS  */
  YYSYMBOL_CLEAR = 7,                      /* CLEAR  */
  YYSYMBOL_DISASSEMBLE = 8,                /* DISASSEMBLE  */
  YYSYMBOL_DUMP = 9,                       /* DUMP  */
  YYSYMBOL_ENDM = 10,                      /* ENDM  */
  YYSYMBOL_FREQUENCY = 11,                 /* FREQUENCY  */
  YYSYMBOL_HELP = 12,                      /* HELP  */
  YYSYMBOL_LOAD = 13,                      /* LOAD  */
  YYSYMBOL_LOG = 14,                       /* LOG  */
  YYSYMBOL_LIST = 15,                      /* LIST  */
  YYSYMBOL_NODE = 16,                      /* NODE  */
  YYSYMBOL_MACRO = 17,                     /* MACRO  */
  YYSYMBOL_MODULE = 18,                    /* MODULE  */
  YYSYMBOL_PROCESSOR = 19,                 /* PROCESSOR  */
  YYSYMBOL_QUIT = 20,                      /* QUIT  */
  YYSYMBOL_RESET = 21,                     /* RESET  */
  YYSYMBOL_RUN = 22,                       /* RUN  */
  YYSYMBOL_SET = 23,                       /* SET  */
  YYSYMBOL_SHELL = 24,                     /* SHELL  */
  YYSYMBOL_STEP = 25,                      /* STEP  */
  YYSYMBOL_STIMULUS = 26,                  /* STIMULUS  */
  YYSYMBOL_SYMBOL = 27,                    /* SYMBOL  */
  YYSYMBOL_TRACE = 28,                     /* TRACE  */
  YYSYMBOL_gpsim_VERSION = 29,             /* gpsim_VERSION  */
  YYSYMBOL_X = 30,                         /* X  */
  YYSYMBOL_ICD = 31,                       /* ICD  */
  YYSYMBOL_END_OF_COMMAND = 32,            /* END_OF_COMMAND  */
  YYSYMBOL_MACROBODY_T = 33,               /* MACROBODY_T  */
  YYSYMBOL_MACROINVOCATION_T = 34,         /* MACROINVOCATION_T  */
  YYSYMBOL_INDIRECT = 35,                  /* INDIRECT  */
  YYSYMBOL_END_OF_INPUT = 36,              /* END_OF_INPUT  */
  YYSYMBOL_BIT_FLAG = 37,                  /* BIT_FLAG  */
  YYSYMBOL_EXPRESSION_OPTION = 38,         /* EXPRESSION_OPTION  */
  YYSYMBOL_NUMERIC_OPTION = 39,            /* NUMERIC_OPTION  */
  YYSYMBOL_STRING_OPTION = 40,             /* STRING_OPTION  */
  YYSYMBOL_CMD_SUBTYPE = 41,               /* CMD_SUBTYPE  */
  YYSYMBOL_SYMBOL_OPTION = 42,             /* SYMBOL_OPTION  */
  YYSYMBOL_LITERAL_INT_T = 43,             /* LITERAL_INT_T  */
  YYSYMBOL_LITERAL_BOOL_T = 44,            /* LITERAL_BOOL_T  */
  YYSYMBOL_LITERAL_FLOAT_T = 45,           /* LITERAL_FLOAT_T  */
  YYSYMBOL_LITERAL_STRING_T = 46,          /* LITERAL_STRING_T  */
  YYSYMBOL_LITERAL_ARRAY_T = 47,           /* LITERAL_ARRAY_T  */
  YYSYMBOL_SYMBOL_T = 48,                  /* SYMBOL_T  */
  YYSYMBOL_GPSIMOBJECT_T = 49,             /* GPSIMOBJECT_T  */
  YYSYMBOL_PORT_T = 50,                    /* PORT_T  */
  YYSYMBOL_EQU_T = 51,                     /* EQU_T  */
  YYSYMBOL_AND_T = 52,                     /* AND_T  */
  YYSYMBOL_COLON_T = 53,                   /* COLON_T  */
  YYSYMBOL_COMMENT_T = 54,                 /* COMMENT_T  */
  YYSYMBOL_DIV_T = 55,                     /* DIV_T  */
  YYSYMBOL_EOLN_T = 56,                    /* EOLN_T  */
  YYSYMBOL_MINUS_T = 57,                   /* MINUS_T  */
  YYSYMBOL_MPY_T = 58,                     /* MPY_T  */
  YYSYMBOL_OR_T = 59,                      /* OR_T  */
  YYSYMBOL_PLUS_T = 60,                    /* PLUS_T  */
  YYSYMBOL_SHL_T = 61,                     /* SHL_T  */
  YYSYMBOL_SHR_T = 62,                     /* SHR_T  */
  YYSYMBOL_XOR_T = 63,                     /* XOR_T  */
  YYSYMBOL_INDEXERLEFT_T = 64,             /* INDEXERLEFT_T  */
  YYSYMBOL_INDEXERRIGHT_T = 65,            /* INDEXERRIGHT_T  */
  YYSYMBOL_DECLARE_TYPE = 66,              /* DECLARE_TYPE  */
  YYSYMBOL_DECLARE_INT_T = 67,             /* DECLARE_INT_T  */
  YYSYMBOL_DECLARE_FLOAT_T = 68,           /* DECLARE_FLOAT_T  */
  YYSYMBOL_DECLARE_BOOL_T = 69,            /* DECLARE_BOOL_T  */
  YYSYMBOL_DECLARE_CHAR_T = 70,            /* DECLARE_CHAR_T  */
  YYSYMBOL_LOR_T = 71,                     /* LOR_T  */
  YYSYMBOL_LAND_T = 72,                    /* LAND_T  */
  YYSYMBOL_EQ_T = 73,                      /* EQ_T  */
  YYSYMBOL_NE_T = 74,                      /* NE_T  */
  YYSYMBOL_LT_T = 75,                      /* LT_T  */
  YYSYMBOL_LE_T = 76,                      /* LE_T  */
  YYSYMBOL_GT_T = 77,                      /* GT_T  */
  YYSYMBOL_GE_T = 78,                      /* GE_T  */
  YYSYMBOL_MIN_T = 79,                     /* MIN_T  */
  YYSYMBOL_MAX_T = 80,                     /* MAX_T  */
  YYSYMBOL_ABS_T = 81,                     /* ABS_T  */
  YYSYMBOL_IND_T = 82,                     /* IND_T  */
  YYSYMBOL_BIT_T = 83,                     /* BIT_T  */
  YYSYMBOL_BITS_T = 84,                    /* BITS_T  */
  YYSYMBOL_LOW_T = 85,                     /* LOW_T  */
  YYSYMBOL_HIGH_T = 86,                    /* HIGH_T  */
  YYSYMBOL_LADDR_T = 87,                   /* LADDR_T  */
  YYSYMBOL_WORD_T = 88,                    /* WORD_T  */
  YYSYMBOL_INDEXED_T = 89,                 /* INDEXED_T  */
  YYSYMBOL_LNOT_T = 90,                    /* LNOT_T  */
  YYSYMBOL_ONESCOMP_T = 91,                /* ONESCOMP_T  */
  YYSYMBOL_UNARYOP_PREC = 92,              /* UNARYOP_PREC  */
  YYSYMBOL_POW_T = 93,                     /* POW_T  */
  YYSYMBOL_REG_T = 94,                     /* REG_T  */
  YYSYMBOL_95_ = 95,                       /* '('  */
  YYSYMBOL_96_ = 96,                       /* ')'  */
  YYSYMBOL_97_ = 97,                       /* ','  */
  YYSYMBOL_98_ = 98,                       /* '\\'  */
  YYSYMBOL_99_ = 99,                       /* '{'  */
  YYSYMBOL_100_ = 100,                     /* '}'  */
  YYSYMBOL_YYACCEPT = 101,                 /* $accept  */
  YYSYMBOL_list_of_commands = 102,         /* list_of_commands  */
  YYSYMBOL_cmd = 103,                      /* cmd  */
  YYSYMBOL_rol = 104,                      /* rol  */
  YYSYMBOL_opt_comment = 105,              /* opt_comment  */
  YYSYMBOL_aborting = 106,                 /* aborting  */
  YYSYMBOL_attach_cmd = 107,               /* attach_cmd  */
  YYSYMBOL_break_cmd = 108,                /* break_cmd  */
  YYSYMBOL_log_cmd = 109,                  /* log_cmd  */
  YYSYMBOL_break_set = 110,                /* break_set  */
  YYSYMBOL_bus_cmd = 111,                  /* bus_cmd  */
  YYSYMBOL_call_cmd = 112,                 /* call_cmd  */
  YYSYMBOL_clear_cmd = 113,                /* clear_cmd  */
  YYSYMBOL_disassemble_cmd = 114,          /* disassemble_cmd  */
  YYSYMBOL_dump_cmd = 115,                 /* dump_cmd  */
  YYSYMBOL_eval_cmd = 116,                 /* eval_cmd  */
  YYSYMBOL_frequency_cmd = 117,            /* frequency_cmd  */
  YYSYMBOL_help_cmd = 118,                 /* help_cmd  */
  YYSYMBOL_list_cmd = 119,                 /* list_cmd  */
  YYSYMBOL_load_cmd = 120,                 /* load_cmd  */
  YYSYMBOL_node_cmd = 121,                 /* node_cmd  */
  YYSYMBOL_module_cmd = 122,               /* module_cmd  */
  YYSYMBOL_processor_cmd = 123,            /* processor_cmd  */
  YYSYMBOL_quit_cmd = 124,                 /* quit_cmd  */
  YYSYMBOL_reset_cmd = 125,                /* reset_cmd  */
  YYSYMBOL_run_cmd = 126,                  /* run_cmd  */
  YYSYMBOL_set_cmd = 127,                  /* set_cmd  */
  YYSYMBOL_step_cmd = 128,                 /* step_cmd  */
  YYSYMBOL_shell_cmd = 129,                /* shell_cmd  */
  YYSYMBOL_stimulus_cmd = 130,             /* stimulus_cmd  */
  YYSYMBOL_stimulus_opt = 131,             /* stimulus_opt  */
  YYSYMBOL_symbol_cmd = 132,               /* symbol_cmd  */
  YYSYMBOL_trace_cmd = 133,                /* trace_cmd  */
  YYSYMBOL_version_cmd = 134,              /* version_cmd  */
  YYSYMBOL_x_cmd = 135,                    /* x_cmd  */
  YYSYMBOL_icd_cmd = 136,                  /* icd_cmd  */
  YYSYMBOL_macro_cmd = 137,                /* macro_cmd  */
  YYSYMBOL_macrodef_directive = 138,       /* macrodef_directive  */
  YYSYMBOL_139_1 = 139,                    /* $@1  */
  YYSYMBOL_140_2 = 140,                    /* $@2  */
  YYSYMBOL_opt_mdef_arglist = 141,         /* opt_mdef_arglist  */
  YYSYMBOL_mdef_body = 142,                /* mdef_body  */
  YYSYMBOL_mdef_body_ = 143,               /* mdef_body_  */
  YYSYMBOL_mdef_end = 144,                 /* mdef_end  */
  YYSYMBOL_declaration_cmd = 145,          /* declaration_cmd  */
  YYSYMBOL_146_3 = 146,                    /* $@3  */
  YYSYMBOL_147_4 = 147,                    /* $@4  */
  YYSYMBOL_opt_declaration_type = 148,     /* opt_declaration_type  */
  YYSYMBOL_bit_flag = 149,                 /* bit_flag  */
  YYSYMBOL_cmd_subtype = 150,              /* cmd_subtype  */
  YYSYMBOL_expression_option = 151,        /* expression_option  */
  YYSYMBOL_numeric_option = 152,           /* numeric_option  */
  YYSYMBOL_string_option = 153,            /* string_option  */
  YYSYMBOL_string_list = 154,              /* string_list  */
  YYSYMBOL_expr = 155,                     /* expr  */
  YYSYMBOL_array = 156,                    /* array  */
  YYSYMBOL_gpsimObject = 157,              /* gpsimObject  */
  YYSYMBOL_gpsimObject_list = 158,         /* gpsimObject_list  */
  YYSYMBOL_expr_list = 159,                /* expr_list  */
  YYSYMBOL_binary_expr = 160,              /* binary_expr  */
  YYSYMBOL_unary_expr = 161,               /* unary_expr  */
  YYSYMBOL_literal = 162                   /* literal  */
};
typedef enum yysymbol_kind_t yysymbol_kind_t;


/* Second part of user prologue.  */
#line 174 "parse.yy"

/* Define the interface to the lexer */
extern int yylex(YYSTYPE* lvalP);

#line 666 "parse.cc"


#ifdef short
# undef short
#endif

/* On compilers that do not define __PTRDIFF_MAX__ etc., make sure
   <limits.h> and (if available) <stdint.h> are included
   so that the code can choose integer types of a good width.  */

#ifndef __PTRDIFF_MAX__
# include <limits.h> /* INFRINGES ON USER NAME SPACE */
# if defined __STDC_VERSION__ && 199901 <= __STDC_VERSION__
#  include <stdint.h> /* INFRINGES ON USER NAME SPACE */
#  define YY_STDINT_H
# endif
#endif

/* Narrow types that promote to a signed type and that can represent a
   signed or unsigned integer of at least N bits.  In tables they can
   save space and decrease cache pressure.  Promoting to a signed type
   helps avoid bugs in integer arithmetic.  */

#ifdef __INT_LEAST8_MAX__
typedef __INT_LEAST8_TYPE__ yytype_int8;
#elif defined YY_STDINT_H
typedef int_least8_t yytype_int8;
#else
typedef signed char yytype_int8;
#endif

#ifdef __INT_LEAST16_MAX__
typedef __INT_LEAST16_TYPE__ yytype_int16;
#elif defined YY_STDINT_H
typedef int_least16_t yytype_int16;
#else
typedef short yytype_int16;
#endif

/* Work around bug in HP-UX 11.23, which defines these macros
   incorrectly for preprocessor constants.  This workaround can likely
   be removed in 2023, as HPE has promised support for HP-UX 11.23
   (aka HP-UX 11i v2) only through the end of 2022; see Table 2 of
   <https://h20195.www2.hpe.com/V2/getpdf.aspx/4AA4-7673ENW.pdf>.  */
#ifdef __hpux
# undef UINT_LEAST8_MAX
# undef UINT_LEAST16_MAX
# define UINT_LEAST8_MAX 255
# define UINT_LEAST16_MAX 65535
#endif

#if defined __UINT_LEAST8_MAX__ && __UINT_LEAST8_MAX__ <= __INT_MAX__
typedef __UINT_LEAST8_TYPE__ yytype_uint8;
#elif (!defined __UINT_LEAST8_MAX__ && defined YY_STDINT_H \
       && UINT_LEAST8_MAX <= INT_MAX)
typedef uint_least8_t yytype_uint8;
#elif !defined __UINT_LEAST8_MAX__ && UCHAR_MAX <= INT_MAX
typedef unsigned char yytype_uint8;
#else
typedef short yytype_uint8;
#endif

#if defined __UINT_LEAST16_MAX__ && __UINT_LEAST16_MAX__ <= __INT_MAX__
typedef __UINT_LEAST16_TYPE__ yytype_uint16;
#elif (!defined __UINT_LEAST16_MAX__ && defined YY_STDINT_H \
       && UINT_LEAST16_MAX <= INT_MAX)
typedef uint_least16_t yytype_uint16;
#elif !defined __UINT_LEAST16_MAX__ && USHRT_MAX <= INT_MAX
typedef unsigned short yytype_uint16;
#else
typedef int yytype_uint16;
#endif

#ifndef YYPTRDIFF_T
# if defined __PTRDIFF_TYPE__ && defined __PTRDIFF_MAX__
#  define YYPTRDIFF_T __PTRDIFF_TYPE__
#  define YYPTRDIFF_MAXIMUM __PTRDIFF_MAX__
# elif defined PTRDIFF_MAX
#  ifndef ptrdiff_t
#   include <stddef.h> /* INFRINGES ON USER NAME SPACE */
#  endif
#  define YYPTRDIFF_T ptrdiff_t
#  define YYPTRDIFF_MAXIMUM PTRDIFF_MAX
# else
#  define YYPTRDIFF_T long
#  define YYPTRDIFF_MAXIMUM LONG_MAX
# endif
#endif

#ifndef YYSIZE_T
# ifdef __SIZE_TYPE__
#  define YYSIZE_T __SIZE_TYPE__
# elif defined size_t
#  define YYSIZE_T size_t
# elif defined __STDC_VERSION__ && 199901 <= __STDC_VERSION__
#  include <stddef.h> /* INFRINGES ON USER NAME SPACE */
#  define YYSIZE_T size_t
# else
#  define YYSIZE_T unsigned
# endif
#endif

#define YYSIZE_MAXIMUM                                  \
  YY_CAST (YYPTRDIFF_T,                                 \
           (YYPTRDIFF_MAXIMUM < YY_CAST (YYSIZE_T, -1)  \
            ? YYPTRDIFF_MAXIMUM                         \
            : YY_CAST (YYSIZE_T, -1)))

#define YYSIZEOF(X) YY_CAST (YYPTRDIFF_T, sizeof (X))


/* Stored state numbers (used for stacks). */
typedef yytype_int16 yy_state_t;

/* State numbers in computations.  */
typedef int yy_state_fast_t;

#ifndef YY_
# if defined YYENABLE_NLS && YYENABLE_NLS
#  if ENABLE_NLS
#   include <libintl.h> /* INFRINGES ON USER NAME SPACE */
#   define YY_(Msgid) dgettext ("bison-runtime", Msgid)
#  endif
# endif
# ifndef YY_
#  define YY_(Msgid) Msgid
# endif
#endif


#ifndef YY_ATTRIBUTE_PURE
# if defined __GNUC__ && 2 < __GNUC__ + (96 <= __GNUC_MINOR__)
#  define YY_ATTRIBUTE_PURE __attribute__ ((__pure__))
# else
#  define YY_ATTRIBUTE_PURE
# endif
#endif

#ifndef YY_ATTRIBUTE_UNUSED
# if defined __GNUC__ && 2 < __GNUC__ + (7 <= __GNUC_MINOR__)
#  define YY_ATTRIBUTE_UNUSED __attribute__ ((__unused__))
# else
#  define YY_ATTRIBUTE_UNUSED
# endif
#endif

/* Suppress unused-variable warnings by "using" E.  */
#if ! defined lint || defined __GNUC__
# define YY_USE(E) ((void) (E))
#else
# define YY_USE(E) /* empty */
#endif

#if defined __GNUC__ && ! defined __ICC && 407 <= __GNUC__ * 100 + __GNUC_MINOR__
/* Suppress an incorrect diagnostic about yylval being uninitialized.  */
# define YY_IGNORE_MAYBE_UNINITIALIZED_BEGIN                            \
    _Pragma ("GCC diagnostic push")                                     \
    _Pragma ("GCC diagnostic ignored \"-Wuninitialized\"")              \
    _Pragma ("GCC diagnostic ignored \"-Wmaybe-uninitialized\"")
# define YY_IGNORE_MAYBE_UNINITIALIZED_END      \
    _Pragma ("GCC diagnostic pop")
#else
# define YY_INITIAL_VALUE(Value) Value
#endif
#ifndef YY_IGNORE_MAYBE_UNINITIALIZED_BEGIN
# define YY_IGNORE_MAYBE_UNINITIALIZED_BEGIN
# define YY_IGNORE_MAYBE_UNINITIALIZED_END
#endif
#ifndef YY_INITIAL_VALUE
# define YY_INITIAL_VALUE(Value) /* Nothing. */
#endif

#if defined __cplusplus && defined __GNUC__ && ! defined __ICC && 6 <= __GNUC__
# define YY_IGNORE_USELESS_CAST_BEGIN                          \
    _Pragma ("GCC diagnostic push")                            \
    _Pragma ("GCC diagnostic ignored \"-Wuseless-cast\"")
# define YY_IGNORE_USELESS_CAST_END            \
    _Pragma ("GCC diagnostic pop")
#endif
#ifndef YY_IGNORE_USELESS_CAST_BEGIN
# define YY_IGNORE_USELESS_CAST_BEGIN
# define YY_IGNORE_USELESS_CAST_END
#endif


#define YY_ASSERT(E) ((void) (0 && (E)))

#if !defined yyoverflow

/* The parser invokes alloca or malloc; define the necessary symbols.  */

# ifdef YYSTACK_USE_ALLOCA
#  if YYSTACK_USE_ALLOCA
#   ifdef __GNUC__
#    define YYSTACK_ALLOC __builtin_alloca
#   elif defined __BUILTIN_VA_ARG_INCR
#    include <alloca.h> /* INFRINGES ON USER NAME SPACE */
#   elif defined _AIX
#    define YYSTACK_ALLOC __alloca
#   elif defined _MSC_VER
#    include <malloc.h> /* INFRINGES ON USER NAME SPACE */
#    define alloca _alloca
#   else
#    define YYSTACK_ALLOC alloca
#    if ! defined _ALLOCA_H && ! defined EXIT_SUCCESS
#     include <stdlib.h> /* INFRINGES ON USER NAME SPACE */
      /* Use EXIT_SUCCESS as a witness for stdlib.h.  */
#     ifndef EXIT_SUCCESS
#      define EXIT_SUCCESS 0
#     endif
#    endif
#   endif
#  endif
# endif

# ifdef YYSTACK_ALLOC
   /* Pacify GCC's 'empty if-body' warning.  */
#  define YYSTACK_FREE(Ptr) do { /* empty */; } while (0)
#  ifndef YYSTACK_ALLOC_MAXIMUM
    /* The OS might guarantee only one guard page at the bottom of the stack,
       and a page size can be as small as 4096 bytes.  So we cannot safely
       invoke alloca (N) if N exceeds 4096.  Use a slightly smaller number
       to allow for a few compiler-allocated temporary stack slots.  */
#   define YYSTACK_ALLOC_MAXIMUM 4032 /* reasonable circa 2006 */
#  endif
# else
#  define YYSTACK_ALLOC YYMALLOC
#  define YYSTACK_FREE YYFREE
#  ifndef YYSTACK_ALLOC_MAXIMUM
#   define YYSTACK_ALLOC_MAXIMUM YYSIZE_MAXIMUM
#  endif
#  if (defined __cplusplus && ! defined EXIT_SUCCESS \
       && ! ((defined YYMALLOC || defined malloc) \
             && (defined YYFREE || defined free)))
#   include <stdlib.h> /* INFRINGES ON USER NAME SPACE */
#   ifndef EXIT_SUCCESS
#    define EXIT_SUCCESS 0
#   endif
#  endif
#  ifndef YYMALLOC
#   define YYMALLOC malloc
#   if ! defined malloc && ! defined EXIT_SUCCESS
void *malloc (YYSIZE_T); /* INFRINGES ON USER NAME SPACE */
#   endif
#  endif
#  ifndef YYFREE
#   define YYFREE free
#   if ! defined free && ! defined EXIT_SUCCESS
void free (void *); /* INFRINGES ON USER NAME SPACE */
#   endif
#  endif
# endif
#endif /* !defined yyoverflow */

#if (! defined yyoverflow \
     && (! defined __cplusplus \
         || (defined YYSTYPE_IS_TRIVIAL && YYSTYPE_IS_TRIVIAL)))

/* A type that is properly aligned for any stack member.  */
union yyalloc
{
  yy_state_t yyss_alloc;
  YYSTYPE yyvs_alloc;
};

/* The size of the maximum gap between one aligned stack and the next.  */
# define YYSTACK_GAP_MAXIMUM (YYSIZEOF (union yyalloc) - 1)

/* The size of an array large to enough to hold all stacks, each with
   N elements.  */
# define YYSTACK_BYTES(N) \
     ((N) * (YYSIZEOF (yy_state_t) + YYSIZEOF (YYSTYPE)) \
      + YYSTACK_GAP_MAXIMUM)

# define YYCOPY_NEEDED 1

/* Relocate STACK from its old location to the new one.  The
   local variables YYSIZE and YYSTACKSIZE give the old and new number of
   elements in the stack, and YYPTR gives the new location of the
   stack.  Advance YYPTR to a properly aligned location for the next
   stack.  */
# define YYSTACK_RELOCATE(Stack_alloc, Stack)                           \
    do                                                                  \
      {                                                                 \
        YYPTRDIFF_T yynewbytes;                                         \
        YYCOPY (&yyptr->Stack_alloc, Stack, yysize);                    \
        Stack = &yyptr->Stack_alloc;                                    \
        yynewbytes = yystacksize * YYSIZEOF (*Stack) + YYSTACK_GAP_MAXIMUM; \
        yyptr += yynewbytes / YYSIZEOF (*yyptr);                        \
      }                                                                 \
    while (0)

#endif

#if defined YYCOPY_NEEDED && YYCOPY_NEEDED
/* Copy COUNT objects from SRC to DST.  The source and destination do
   not overlap.  */
# ifndef YYCOPY
#  if defined __GNUC__ && 1 < __GNUC__
#   define YYCOPY(Dst, Src, Count) \
      __builtin_memcpy (Dst, Src, YY_CAST (YYSIZE_T, (Count)) * sizeof (*(Src)))
#  else
#   define YYCOPY(Dst, Src, Count)              \
      do                                        \
        {                                       \
          YYPTRDIFF_T yyi;                      \
          for (yyi = 0; yyi < (Count); yyi++)   \
            (Dst)[yyi] = (Src)[yyi];            \
        }                                       \
      while (0)
#  endif
# endif
#endif /* !YYCOPY_NEEDED */

/* YYFINAL -- State number of the termination state.  */
#define YYFINAL  138
/* YYLAST -- Last index in YYTABLE.  */
#define YYLAST   507

/* YYNTOKENS -- Number of terminals.  */
#define YYNTOKENS  101
/* YYNNTS -- Number of nonterminals.  */
#define YYNNTS  62
/* YYNRULES -- Number of rules.  */
#define YYNRULES  201
/* YYNSTATES -- Number of states.  */
#define YYNSTATES  270

/* YYMAXUTOK -- Last valid token kind.  */
#define YYMAXUTOK   349


/* YYTRANSLATE(TOKEN-NUM) -- Symbol number corresponding to TOKEN-NUM
   as returned by yylex, with out-of-bounds checking.  */
#define YYTRANSLATE(YYX)                                \
  (0 <= (YYX) && (YYX) <= YYMAXUTOK                     \
   ? YY_CAST (yysymbol_kind_t, yytranslate[YYX])        \
   : YYSYMBOL_YYUNDEF)

/* YYTRANSLATE[TOKEN-NUM] -- Symbol number corresponding to TOKEN-NUM
   as returned by yylex.  */
static const yytype_int8 yytranslate[] =
{
       0,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
      95,    96,     2,     2,    97,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,    98,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,    99,     2,   100,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     1,     2,     3,     4,
       5,     6,     7,     8,     9,    10,    11,    12,    13,    14,
      15,    16,    17,    18,    19,    20,    21,    22,    23,    24,
      25,    26,    27,    28,    29,    30,    31,    32,    33,    34,
      35,    36,    37,    38,    39,    40,    41,    42,    43,    44,
      45,    46,    47,    48,    49,    50,    51,    52,    53,    54,
      55,    56,    57,    58,    59,    60,    61,    62,    63,    64,
      65,    66,    67,    68,    69,    70,    71,    72,    73,    74,
      75,    76,    77,    78,    79,    80,    81,    82,    83,    84,
      85,    86,    87,    88,    89,    90,    91,    92,    93,    94
};

#if YYDEBUG
  /* YYRLINE[YYN] -- Source line where rule number YYN was defined.  */
static const yytype_int16 yyrline[] =
{
       0,   319,   319,   323,   329,   331,   332,   333,   334,   335,
     336,   337,   338,   339,   340,   341,   342,   343,   344,   345,
     346,   347,   348,   349,   350,   351,   352,   353,   354,   355,
     356,   357,   358,   359,   360,   361,   362,   372,   389,   394,
     395,   399,   408,   415,   416,   417,   427,   428,   429,   434,
     435,   436,   440,   441,   444,   451,   455,   456,   460,   461,
     462,   468,   482,   490,   494,   509,   515,   522,   532,   545,
     546,   550,   551,   552,   553,   557,   558,   561,   572,   583,
     597,   610,   624,   644,   645,   649,   650,   651,   656,   666,
     670,   674,   679,   687,   692,   701,   705,   709,   710,   711,
     715,   716,   727,   731,   734,   738,   742,   746,   756,   762,
     768,   774,   784,   785,   791,   796,   804,   805,   806,   807,
     808,   809,   812,   815,   816,   820,   821,   842,   843,   844,
     850,   852,   849,   858,   859,   864,   873,   874,   878,   879,
     883,   884,   905,   910,   904,   921,   922,   923,   924,   925,
     949,   955,   961,   964,   973,   981,  1001,  1002,  1008,  1009,
    1010,  1014,  1017,  1033,  1039,  1060,  1061,  1065,  1066,  1070,
    1071,  1072,  1073,  1074,  1075,  1076,  1077,  1078,  1079,  1080,
    1081,  1082,  1083,  1084,  1085,  1086,  1087,  1091,  1092,  1093,
    1094,  1095,  1096,  1097,  1098,  1101,  1102,  1103,  1104,  1105,
    1115,  1116
};
#endif

/** Accessing symbol of state STATE.  */
#define YY_ACCESSING_SYMBOL(State) YY_CAST (yysymbol_kind_t, yystos[State])

#if YYDEBUG || 0
/* The user-facing name of the symbol whose (internal) number is
   YYSYMBOL.  No bounds checking.  */
static const char *yysymbol_name (yysymbol_kind_t yysymbol) YY_ATTRIBUTE_UNUSED;

/* YYTNAME[SYMBOL-NUM] -- String name of the symbol SYMBOL-NUM.
   First, the terminals, then, starting at YYNTOKENS, nonterminals.  */
static const char *const yytname[] =
{
  "\"end of file\"", "error", "\"invalid token\"", "ABORT", "ATTACH",
  "BREAK", "BUS", "CLEAR", "DISASSEMBLE", "DUMP", "ENDM", "FREQUENCY",
  "HELP", "LOAD", "LOG", "LIST", "NODE", "MACRO", "MODULE", "PROCESSOR",
  "QUIT", "RESET", "RUN", "SET", "SHELL", "STEP", "STIMULUS", "SYMBOL",
  "TRACE", "gpsim_VERSION", "X", "ICD", "END_OF_COMMAND", "MACROBODY_T",
  "MACROINVOCATION_T", "INDIRECT", "END_OF_INPUT", "BIT_FLAG",
  "EXPRESSION_OPTION", "NUMERIC_OPTION", "STRING_OPTION", "CMD_SUBTYPE",
  "SYMBOL_OPTION", "LITERAL_INT_T", "LITERAL_BOOL_T", "LITERAL_FLOAT_T",
  "LITERAL_STRING_T", "LITERAL_ARRAY_T", "SYMBOL_T", "GPSIMOBJECT_T",
  "PORT_T", "EQU_T", "AND_T", "COLON_T", "COMMENT_T", "DIV_T", "EOLN_T",
  "MINUS_T", "MPY_T", "OR_T", "PLUS_T", "SHL_T", "SHR_T", "XOR_T",
  "INDEXERLEFT_T", "INDEXERRIGHT_T", "DECLARE_TYPE", "DECLARE_INT_T",
  "DECLARE_FLOAT_T", "DECLARE_BOOL_T", "DECLARE_CHAR_T", "LOR_T", "LAND_T",
  "EQ_T", "NE_T", "LT_T", "LE_T", "GT_T", "GE_T", "MIN_T", "MAX_T",
  "ABS_T", "IND_T", "BIT_T", "BITS_T", "LOW_T", "HIGH_T", "LADDR_T",
  "WORD_T", "INDEXED_T", "LNOT_T", "ONESCOMP_T", "UNARYOP_PREC", "POW_T",
  "REG_T", "'('", "')'", "','", "'\\\\'", "'{'", "'}'", "$accept",
  "list_of_commands", "cmd", "rol", "opt_comment", "aborting",
  "attach_cmd", "break_cmd", "log_cmd", "break_set", "bus_cmd", "call_cmd",
  "clear_cmd", "disassemble_cmd", "dump_cmd", "eval_cmd", "frequency_cmd",
  "help_cmd", "list_cmd", "load_cmd", "node_cmd", "module_cmd",
  "processor_cmd", "quit_cmd", "reset_cmd", "run_cmd", "set_cmd",
  "step_cmd", "shell_cmd", "stimulus_cmd", "stimulus_opt", "symbol_cmd",
  "trace_cmd", "version_cmd", "x_cmd", "icd_cmd", "macro_cmd",
  "macrodef_directive", "$@1", "$@2", "opt_mdef_arglist", "mdef_body",
  "mdef_body_", "mdef_end", "declaration_cmd", "$@3", "$@4",
  "opt_declaration_type", "bit_flag", "cmd_subtype", "expression_option",
  "numeric_option", "string_option", "string_list", "expr", "array",
  "gpsimObject", "gpsimObject_list", "expr_list", "binary_expr",
  "unary_expr", "literal", YY_NULLPTR
};

static const char *
yysymbol_name (yysymbol_kind_t yysymbol)
{
  return yytname[yysymbol];
}
#endif

#ifdef YYPRINT
/* YYTOKNUM[NUM] -- (External) token number corresponding to the
   (internal) symbol number NUM (which must be that of a token).  */
static const yytype_int16 yytoknum[] =
{
       0,   256,   257,   258,   259,   260,   261,   262,   263,   264,
     265,   266,   267,   268,   269,   270,   271,   272,   273,   274,
     275,   276,   277,   278,   279,   280,   281,   282,   283,   284,
     285,   286,   287,   288,   289,   290,   291,   292,   293,   294,
     295,   296,   297,   298,   299,   300,   301,   302,   303,   304,
     305,   306,   307,   308,   309,   310,   311,   312,   313,   314,
     315,   316,   317,   318,   319,   320,   321,   322,   323,   324,
     325,   326,   327,   328,   329,   330,   331,   332,   333,   334,
     335,   336,   337,   338,   339,   340,   341,   342,   343,   344,
     345,   346,   347,   348,   349,    40,    41,    44,    92,   123,
     125
};
#endif

#define YYPACT_NINF (-133)

#define yypact_value_is_default(Yyn) \
  ((Yyn) == YYPACT_NINF)

#define YYTABLE_NINF (-5)

#define yytable_value_is_error(Yyn) \
  ((Yyn) == YYTABLE_NINF)

  /* YYPACT[STATE-NUM] -- Index in YYTABLE of the portion describing
     STATE-NUM.  */
static const yytype_int16 yypact[] =
{
     174,  -133,  -133,   -15,    -9,    36,   236,   236,    51,   236,
     -21,    44,    51,    51,    36,  -133,    43,    47,   236,  -133,
    -133,    51,  -133,   169,    65,   -30,   196,  -133,   236,    71,
    -133,  -133,   102,    27,    29,   236,  -133,    41,    74,  -133,
    -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,
    -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,
    -133,  -133,  -133,     5,  -133,  -133,  -133,  -133,  -133,  -133,
    -133,  -133,    83,  -133,  -133,  -133,   236,  -133,    91,  -133,
    -133,  -133,  -133,  -133,    76,   254,   254,   254,   254,   254,
     254,    46,   236,   388,  -133,  -133,  -133,   388,    90,   388,
    -133,  -133,  -133,   107,   126,    48,   236,  -133,    91,    77,
    -133,    36,   109,  -133,   388,   236,  -133,   388,  -133,  -133,
     125,  -133,   236,   236,  -133,  -133,  -133,  -133,   388,   388,
    -133,  -133,   236,   236,   236,   236,   280,    45,  -133,    74,
    -133,  -133,   128,  -133,   -14,  -133,  -133,   114,  -133,    83,
     388,   121,  -133,   236,  -133,  -133,  -133,  -133,  -133,  -133,
     236,   307,   236,   236,   236,   236,   236,   236,   236,   236,
     236,   236,   236,   236,   236,   236,   236,   236,   236,   236,
     165,  -133,  -133,  -133,   173,   121,  -133,  -133,    91,  -133,
     388,   230,   388,   388,   177,   388,   -57,    55,   334,  -133,
    -133,  -133,  -133,  -133,  -133,  -133,  -133,   236,  -133,  -133,
    -133,   -13,  -133,   236,    11,   361,  -133,    72,   415,   246,
      72,   246,    72,    72,   423,   423,    72,    26,   406,   296,
     296,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,   -18,
     180,  -133,   181,   178,    21,   129,   141,   388,  -133,  -133,
     192,  -133,   236,   236,  -133,  -133,  -133,  -133,  -133,   212,
     388,   388,  -133,    28,   216,  -133,   240,  -133,  -133,  -133
};

  /* YYDEFACT[STATE-NUM] -- Default reduction number in state STATE-NUM.
     Performed when YYTABLE does not specify something else to do.  Zero
     means the default is an error.  */
static const yytype_uint8 yydefact[] =
{
       0,    37,    41,     0,    43,    52,     0,    56,    58,    69,
      71,     0,    46,    75,    83,   127,    85,    89,    93,    95,
      96,    97,   103,   100,   104,   112,   116,   122,   123,   125,
     129,    36,     0,    62,     0,     0,   142,     0,    39,     5,
       6,     7,    18,    45,     8,     9,    10,    12,    13,    14,
      15,    16,    17,    19,    20,    22,    23,    24,    25,    26,
      27,    28,    29,    30,    31,    32,    33,    34,    35,    21,
     128,    11,     0,   150,    44,    51,    50,   156,    53,   195,
     196,   198,   197,   201,   199,     0,     0,     0,     0,     0,
       0,     0,     0,    55,   158,   159,   187,    57,    59,    70,
      73,    74,    72,    79,    80,     0,    47,    76,    84,     0,
      86,    87,    91,    90,    94,    98,   102,   101,   151,   105,
     114,   115,     0,     0,   120,   121,   118,   119,   117,   124,
     126,   130,     0,     0,     0,     0,     0,   145,     1,    39,
      40,     2,     0,   107,   106,   108,   164,     0,   165,    42,
     167,    49,   157,     0,   193,   189,   192,   188,   191,   190,
       0,     0,     0,     0,     0,     0,     0,     0,     0,     0,
       0,     0,     0,     0,     0,     0,     0,     0,     0,     0,
      60,    82,    81,    77,     0,    48,   154,   155,    88,    92,
      99,     0,   152,   153,   133,    64,     0,     0,     0,    63,
     146,   147,   148,   149,   143,     3,    38,     0,   109,   110,
     111,     0,   166,     0,     0,     0,   194,   173,   186,   172,
     170,   171,   174,   169,   176,   177,   175,   185,   184,   178,
     179,   180,   182,   181,   183,    61,    78,   113,   134,    39,
      65,    54,    67,     0,     0,     0,     0,   168,   200,   160,
       0,   131,     0,     0,   144,   161,   163,   162,   135,   136,
      66,    68,   138,     0,   137,   140,     0,   132,   139,   141
};

  /* YYPGOTO[NTERM-NUM].  */
static const yytype_int16 yypgoto[] =
{
    -133,  -133,   214,  -132,  -133,  -133,  -133,  -133,  -133,  -133,
    -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,
    -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,
    -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,
    -133,  -133,  -133,  -133,  -133,  -133,  -133,  -133,    -2,  -133,
     189,  -133,   -24,    -1,    -6,  -133,   106,  -133,  -102,  -133,
     417,    66
};

  /* YYDEFGOTO[NTERM-NUM].  */
static const yytype_int16 yydefgoto[] =
{
       0,    37,    38,   141,   142,    39,    40,    41,    42,    43,
      44,    45,    46,    47,    48,    49,    50,    51,    52,    53,
      54,    55,    56,    57,    58,    59,    60,    61,    62,    63,
     144,    64,    65,    66,    67,    68,    69,    70,   194,   259,
     239,   263,   264,   267,    71,   137,   243,   204,    76,   119,
     125,   126,   111,    78,   150,   210,   148,   149,   151,    94,
      95,    96
};

  /* YYTABLE[YYPACT[STATE-NUM]] -- What to do in state STATE-NUM.  If
     positive, shift that token.  If negative, reduce the rule whose
     number is the opposite.  If YYTABLE_NINF, syntax error.  */
static const yytype_int16 yytable[] =
{
      93,    97,   127,    99,   185,   130,    98,   205,   240,   105,
     106,   107,   114,   108,   110,   113,   120,   117,   121,   115,
     128,   116,   129,    73,   124,   100,   109,   101,    73,   136,
     245,   196,   197,    72,    74,   246,   140,   143,   265,    75,
     213,   138,     1,   122,     2,     3,     4,     5,     6,     7,
       8,   214,     9,    10,    11,    12,    13,    14,    15,    16,
      17,    18,    19,    20,    21,    22,    23,    24,    25,    26,
      27,    28,    29,   102,   266,    30,   248,    31,   132,   250,
      73,    73,    77,   109,    73,   207,   161,    32,    73,    33,
     103,   133,   104,   112,   183,    -4,   184,    -4,   173,   174,
     175,   176,   177,   178,   179,   244,   118,   251,   213,   190,
     188,   109,   200,   201,   202,   203,   192,   193,   213,   131,
     209,   255,   134,   186,   135,   187,   195,   164,   140,   198,
     166,   146,   147,   169,   170,    34,    35,   152,   180,    36,
     153,   160,   208,   172,   173,   174,   175,   176,   177,   178,
     179,   241,   213,   181,   215,   189,   217,   218,   219,   220,
     221,   222,   223,   224,   225,   226,   227,   228,   229,   230,
     231,   232,   233,   234,   182,     1,   191,     2,     3,     4,
       5,     6,     7,     8,   206,     9,    10,    11,    12,    13,
      14,    15,    16,    17,    18,    19,    20,    21,    22,    23,
      24,    25,    26,    27,    28,    29,    73,   247,    30,   211,
      31,   235,    79,    80,    81,    82,    83,    84,   213,   236,
      32,    85,    33,   238,   254,   256,    86,    87,    -4,    88,
      -4,   252,   253,    73,   122,   123,   109,   257,   258,    79,
      80,    81,    82,    83,    84,   262,   260,   261,    85,   268,
     269,   139,   145,    86,    87,   212,    88,   237,     0,    89,
      90,     0,     0,    91,    92,     0,     0,     0,    34,    35,
       0,     0,    36,    79,    80,    81,    82,    83,    84,    79,
      80,    81,    82,    83,    84,     0,    89,    90,    85,     0,
      91,    92,     0,    86,    87,     0,    88,    79,    80,    81,
      82,    83,    84,     0,     0,     0,    85,   169,   170,     0,
       0,    86,    87,     0,    88,     0,     0,   172,   173,   174,
     175,   176,   177,   178,   179,     0,    89,    90,     0,     0,
      91,    92,   162,   163,     0,   164,     0,   165,   166,   167,
     168,   169,   170,   171,    89,    90,     0,     0,     0,    92,
       0,   172,   173,   174,   175,   176,   177,   178,   179,   162,
     163,     0,   164,     0,   165,   166,   167,   168,   169,   170,
     171,   176,   177,   178,   179,     0,   199,     0,   172,   173,
     174,   175,   176,   177,   178,   179,   162,   163,     0,   164,
       0,   165,   166,   167,   168,   169,   170,   171,     0,     0,
       0,     0,     0,   216,     0,   172,   173,   174,   175,   176,
     177,   178,   179,   162,   163,     0,   164,     0,   165,   166,
     167,   168,   169,   170,   171,     0,     0,     0,     0,     0,
     242,     0,   172,   173,   174,   175,   176,   177,   178,   179,
     162,   163,     0,   164,     0,   165,   166,   167,   168,   169,
     170,   171,     0,     0,     0,     0,     0,   249,     0,   172,
     173,   174,   175,   176,   177,   178,   179,   162,    -5,     0,
     164,     0,   165,   166,   167,   168,   169,   170,   171,   174,
     175,   176,   177,   178,   179,     0,   172,   173,   174,   175,
     176,   177,   178,   179,   172,   173,   174,   175,   176,   177,
     178,   179,   154,   155,   156,   157,   158,   159
};

static const yytype_int16 yycheck[] =
{
       6,     7,    26,     9,   106,    29,     8,   139,    65,    11,
      12,    13,    18,    14,    16,    17,    46,    23,    48,    21,
      26,    23,    28,    37,    26,    46,    40,    48,    37,    35,
      43,   133,   134,    48,    43,    48,    54,    32,    10,    48,
      97,     0,     1,    38,     3,     4,     5,     6,     7,     8,
       9,   153,    11,    12,    13,    14,    15,    16,    17,    18,
      19,    20,    21,    22,    23,    24,    25,    26,    27,    28,
      29,    30,    31,    94,    46,    34,    65,    36,    51,    97,
      37,    37,    46,    40,    37,    99,    92,    46,    37,    48,
      46,    64,    48,    46,    46,    54,    48,    56,    72,    73,
      74,    75,    76,    77,    78,   207,    41,   239,    97,   115,
     111,    40,    67,    68,    69,    70,   122,   123,    97,    17,
     144,   100,    95,    46,    95,    48,   132,    55,    54,   135,
      58,    48,    49,    61,    62,    94,    95,    46,    48,    98,
      64,    95,   144,    71,    72,    73,    74,    75,    76,    77,
      78,    96,    97,    46,   160,    46,   162,   163,   164,   165,
     166,   167,   168,   169,   170,   171,   172,   173,   174,   175,
     176,   177,   178,   179,    48,     1,    51,     3,     4,     5,
       6,     7,     8,     9,    56,    11,    12,    13,    14,    15,
      16,    17,    18,    19,    20,    21,    22,    23,    24,    25,
      26,    27,    28,    29,    30,    31,    37,   213,    34,    95,
      36,    46,    43,    44,    45,    46,    47,    48,    97,    46,
      46,    52,    48,    46,    46,    96,    57,    58,    54,    60,
      56,    51,    51,    37,    38,    39,    40,    96,    46,    43,
      44,    45,    46,    47,    48,    33,   252,   253,    52,    33,
      10,    37,    63,    57,    58,   149,    60,   191,    -1,    90,
      91,    -1,    -1,    94,    95,    -1,    -1,    -1,    94,    95,
      -1,    -1,    98,    43,    44,    45,    46,    47,    48,    43,
      44,    45,    46,    47,    48,    -1,    90,    91,    52,    -1,
      94,    95,    -1,    57,    58,    -1,    60,    43,    44,    45,
      46,    47,    48,    -1,    -1,    -1,    52,    61,    62,    -1,
      -1,    57,    58,    -1,    60,    -1,    -1,    71,    72,    73,
      74,    75,    76,    77,    78,    -1,    90,    91,    -1,    -1,
      94,    95,    52,    53,    -1,    55,    -1,    57,    58,    59,
      60,    61,    62,    63,    90,    91,    -1,    -1,    -1,    95,
      -1,    71,    72,    73,    74,    75,    76,    77,    78,    52,
      53,    -1,    55,    -1,    57,    58,    59,    60,    61,    62,
      63,    75,    76,    77,    78,    -1,    96,    -1,    71,    72,
      73,    74,    75,    76,    77,    78,    52,    53,    -1,    55,
      -1,    57,    58,    59,    60,    61,    62,    63,    -1,    -1,
      -1,    -1,    -1,    96,    -1,    71,    72,    73,    74,    75,
      76,    77,    78,    52,    53,    -1,    55,    -1,    57,    58,
      59,    60,    61,    62,    63,    -1,    -1,    -1,    -1,    -1,
      96,    -1,    71,    72,    73,    74,    75,    76,    77,    78,
      52,    53,    -1,    55,    -1,    57,    58,    59,    60,    61,
      62,    63,    -1,    -1,    -1,    -1,    -1,    96,    -1,    71,
      72,    73,    74,    75,    76,    77,    78,    52,    53,    -1,
      55,    -1,    57,    58,    59,    60,    61,    62,    63,    73,
      74,    75,    76,    77,    78,    -1,    71,    72,    73,    74,
      75,    76,    77,    78,    71,    72,    73,    74,    75,    76,
      77,    78,    85,    86,    87,    88,    89,    90
};

  /* YYSTOS[STATE-NUM] -- The (internal number of the) accessing
     symbol of state STATE-NUM.  */
static const yytype_uint8 yystos[] =
{
       0,     1,     3,     4,     5,     6,     7,     8,     9,    11,
      12,    13,    14,    15,    16,    17,    18,    19,    20,    21,
      22,    23,    24,    25,    26,    27,    28,    29,    30,    31,
      34,    36,    46,    48,    94,    95,    98,   102,   103,   106,
     107,   108,   109,   110,   111,   112,   113,   114,   115,   116,
     117,   118,   119,   120,   121,   122,   123,   124,   125,   126,
     127,   128,   129,   130,   132,   133,   134,   135,   136,   137,
     138,   145,    48,    37,    43,    48,   149,    46,   154,    43,
      44,    45,    46,    47,    48,    52,    57,    58,    60,    90,
      91,    94,    95,   155,   160,   161,   162,   155,   149,   155,
      46,    48,    94,    46,    48,   149,   149,   149,   154,    40,
     149,   153,    46,   149,   155,   149,   149,   155,    41,   150,
      46,    48,    38,    39,   149,   151,   152,   153,   155,   155,
     153,    17,    51,    64,    95,    95,   155,   146,     0,   103,
      54,   104,   105,    32,   131,   151,    48,    49,   157,   158,
     155,   159,    46,    64,   161,   161,   161,   161,   161,   161,
      95,   155,    52,    53,    55,    57,    58,    59,    60,    61,
      62,    63,    71,    72,    73,    74,    75,    76,    77,    78,
      48,    46,    48,    46,    48,   159,    46,    48,   154,    46,
     155,    51,   155,   155,   139,   155,   159,   159,   155,    96,
      67,    68,    69,    70,   148,   104,    56,    99,   149,   153,
     156,    95,   157,    97,   159,   155,    96,   155,   155,   155,
     155,   155,   155,   155,   155,   155,   155,   155,   155,   155,
     155,   155,   155,   155,   155,    46,    46,   162,    46,   141,
      65,    96,    96,   147,   159,    43,    48,   155,    65,    96,
      97,   104,    51,    51,    46,   100,    96,    96,    46,   140,
     155,   155,    33,   142,   143,    10,    46,   144,    33,    10
};

  /* YYR1[YYN] -- Symbol number of symbol that rule YYN derives.  */
static const yytype_uint8 yyr1[] =
{
       0,   101,   102,   102,   103,   103,   103,   103,   103,   103,
     103,   103,   103,   103,   103,   103,   103,   103,   103,   103,
     103,   103,   103,   103,   103,   103,   103,   103,   103,   103,
     103,   103,   103,   103,   103,   103,   103,   103,   104,   105,
     105,   106,   107,   108,   108,   108,   109,   109,   109,   110,
     110,   110,   111,   111,   112,   113,   114,   114,   115,   115,
     115,   115,   116,   116,   116,   116,   116,   116,   116,   117,
     117,   118,   118,   118,   118,   119,   119,   120,   120,   120,
     120,   120,   120,   121,   121,   122,   122,   122,   122,   123,
     123,   123,   123,   124,   124,   125,   126,   127,   127,   127,
     128,   128,   128,   129,   130,   130,   130,   130,   131,   131,
     131,   131,   132,   132,   132,   132,   133,   133,   133,   133,
     133,   133,   134,   135,   135,   136,   136,   137,   137,   137,
     139,   140,   138,   141,   141,   141,   142,   142,   143,   143,
     144,   144,   146,   147,   145,   148,   148,   148,   148,   148,
     149,   150,   151,   152,   153,   153,   154,   154,   155,   155,
     155,   156,   157,   157,   157,   158,   158,   159,   159,   160,
     160,   160,   160,   160,   160,   160,   160,   160,   160,   160,
     160,   160,   160,   160,   160,   160,   160,   161,   161,   161,
     161,   161,   161,   161,   161,   162,   162,   162,   162,   162,
     162,   162
};

  /* YYR2[YYN] -- Number of symbols on the right hand side of rule YYN.  */
static const yytype_int8 yyr2[] =
{
       0,     2,     2,     3,     0,     1,     1,     1,     1,     1,
       1,     1,     1,     1,     1,     1,     1,     1,     1,     1,
       1,     1,     1,     1,     1,     1,     1,     1,     1,     1,
       1,     1,     1,     1,     1,     1,     1,     1,     2,     0,
       1,     1,     3,     1,     2,     1,     1,     2,     3,     3,
       2,     2,     1,     2,     4,     2,     1,     2,     1,     2,
       3,     4,     1,     3,     3,     4,     6,     4,     6,     1,
       2,     1,     2,     2,     2,     1,     2,     3,     4,     2,
       2,     3,     3,     1,     2,     1,     2,     2,     3,     1,
       2,     2,     3,     1,     2,     1,     1,     1,     2,     3,
       1,     2,     2,     1,     1,     2,     2,     2,     1,     2,
       2,     2,     1,     4,     2,     2,     1,     2,     2,     2,
       2,     2,     1,     1,     2,     1,     2,     1,     1,     1,
       0,     0,     8,     0,     1,     3,     0,     1,     1,     2,
       1,     2,     0,     0,     5,     0,     1,     1,     1,     1,
       1,     1,     2,     2,     2,     2,     1,     2,     1,     1,
       4,     3,     4,     4,     1,     1,     2,     1,     3,     3,
       3,     3,     3,     3,     3,     3,     3,     3,     3,     3,
       3,     3,     3,     3,     3,     3,     3,     1,     2,     2,
       2,     2,     2,     2,     3,     1,     1,     1,     1,     1,
       4,     1
};


enum { YYENOMEM = -2 };

#define yyerrok         (yyerrstatus = 0)
#define yyclearin       (yychar = YYEMPTY)

#define YYACCEPT        goto yyacceptlab
#define YYABORT         goto yyabortlab
#define YYERROR         goto yyerrorlab


#define YYRECOVERING()  (!!yyerrstatus)

#define YYBACKUP(Token, Value)                                    \
  do                                                              \
    if (yychar == YYEMPTY)                                        \
      {                                                           \
        yychar = (Token);                                         \
        yylval = (Value);                                         \
        YYPOPSTACK (yylen);                                       \
        yystate = *yyssp;                                         \
        goto yybackup;                                            \
      }                                                           \
    else                                                          \
      {                                                           \
        yyerror (YY_("syntax error: cannot back up")); \
        YYERROR;                                                  \
      }                                                           \
  while (0)

/* Backward compatibility with an undocumented macro.
   Use YYerror or YYUNDEF. */
#define YYERRCODE YYUNDEF


/* Enable debugging if requested.  */
#if YYDEBUG

# ifndef YYFPRINTF
#  include <stdio.h> /* INFRINGES ON USER NAME SPACE */
#  define YYFPRINTF fprintf
# endif

# define YYDPRINTF(Args)                        \
do {                                            \
  if (yydebug)                                  \
    YYFPRINTF Args;                             \
} while (0)

/* This macro is provided for backward compatibility. */
# ifndef YY_LOCATION_PRINT
#  define YY_LOCATION_PRINT(File, Loc) ((void) 0)
# endif


# define YY_SYMBOL_PRINT(Title, Kind, Value, Location)                    \
do {                                                                      \
  if (yydebug)                                                            \
    {                                                                     \
      YYFPRINTF (stderr, "%s ", Title);                                   \
      yy_symbol_print (stderr,                                            \
                  Kind, Value); \
      YYFPRINTF (stderr, "\n");                                           \
    }                                                                     \
} while (0)


/*-----------------------------------.
| Print this symbol's value on YYO.  |
`-----------------------------------*/

static void
yy_symbol_value_print (FILE *yyo,
                       yysymbol_kind_t yykind, YYSTYPE const * const yyvaluep)
{
  FILE *yyoutput = yyo;
  YY_USE (yyoutput);
  if (!yyvaluep)
    return;
# ifdef YYPRINT
  if (yykind < YYNTOKENS)
    YYPRINT (yyo, yytoknum[yykind], *yyvaluep);
# endif
  YY_IGNORE_MAYBE_UNINITIALIZED_BEGIN
  YY_USE (yykind);
  YY_IGNORE_MAYBE_UNINITIALIZED_END
}


/*---------------------------.
| Print this symbol on YYO.  |
`---------------------------*/

static void
yy_symbol_print (FILE *yyo,
                 yysymbol_kind_t yykind, YYSTYPE const * const yyvaluep)
{
  YYFPRINTF (yyo, "%s %s (",
             yykind < YYNTOKENS ? "token" : "nterm", yysymbol_name (yykind));

  yy_symbol_value_print (yyo, yykind, yyvaluep);
  YYFPRINTF (yyo, ")");
}

/*------------------------------------------------------------------.
| yy_stack_print -- Print the state stack from its BOTTOM up to its |
| TOP (included).                                                   |
`------------------------------------------------------------------*/

static void
yy_stack_print (yy_state_t *yybottom, yy_state_t *yytop)
{
  YYFPRINTF (stderr, "Stack now");
  for (; yybottom <= yytop; yybottom++)
    {
      int yybot = *yybottom;
      YYFPRINTF (stderr, " %d", yybot);
    }
  YYFPRINTF (stderr, "\n");
}

# define YY_STACK_PRINT(Bottom, Top)                            \
do {                                                            \
  if (yydebug)                                                  \
    yy_stack_print ((Bottom), (Top));                           \
} while (0)


/*------------------------------------------------.
| Report that the YYRULE is going to be reduced.  |
`------------------------------------------------*/

static void
yy_reduce_print (yy_state_t *yyssp, YYSTYPE *yyvsp,
                 int yyrule)
{
  int yylno = yyrline[yyrule];
  int yynrhs = yyr2[yyrule];
  int yyi;
  YYFPRINTF (stderr, "Reducing stack by rule %d (line %d):\n",
             yyrule - 1, yylno);
  /* The symbols being reduced.  */
  for (yyi = 0; yyi < yynrhs; yyi++)
    {
      YYFPRINTF (stderr, "   $%d = ", yyi + 1);
      yy_symbol_print (stderr,
                       YY_ACCESSING_SYMBOL (+yyssp[yyi + 1 - yynrhs]),
                       &yyvsp[(yyi + 1) - (yynrhs)]);
      YYFPRINTF (stderr, "\n");
    }
}

# define YY_REDUCE_PRINT(Rule)          \
do {                                    \
  if (yydebug)                          \
    yy_reduce_print (yyssp, yyvsp, Rule); \
} while (0)

/* Nonzero means print parse trace.  It is left uninitialized so that
   multiple parsers can coexist.  */
int yydebug;
#else /* !YYDEBUG */
# define YYDPRINTF(Args) ((void) 0)
# define YY_SYMBOL_PRINT(Title, Kind, Value, Location)
# define YY_STACK_PRINT(Bottom, Top)
# define YY_REDUCE_PRINT(Rule)
#endif /* !YYDEBUG */


/* YYINITDEPTH -- initial size of the parser's stacks.  */
#ifndef YYINITDEPTH
# define YYINITDEPTH 200
#endif

/* YYMAXDEPTH -- maximum size the stacks can grow to (effective only
   if the built-in stack extension method is used).

   Do not make this value too large; the results are undefined if
   YYSTACK_ALLOC_MAXIMUM < YYSTACK_BYTES (YYMAXDEPTH)
   evaluated with infinite-precision integer arithmetic.  */

#ifndef YYMAXDEPTH
# define YYMAXDEPTH 10000
#endif






/*-----------------------------------------------.
| Release the memory associated to this symbol.  |
`-----------------------------------------------*/

static void
yydestruct (const char *yymsg,
            yysymbol_kind_t yykind, YYSTYPE *yyvaluep)
{
  YY_USE (yyvaluep);
  if (!yymsg)
    yymsg = "Deleting";
  YY_SYMBOL_PRINT (yymsg, yykind, yyvaluep, yylocationp);

  YY_IGNORE_MAYBE_UNINITIALIZED_BEGIN
  YY_USE (yykind);
  YY_IGNORE_MAYBE_UNINITIALIZED_END
}






/*----------.
| yyparse.  |
`----------*/

int
yyparse (void)
{
/* Lookahead token kind.  */
int yychar;


/* The semantic value of the lookahead symbol.  */
/* Default value used for initialization, for pacifying older GCCs
   or non-GCC compilers.  */
YY_INITIAL_VALUE (static YYSTYPE yyval_default;)
YYSTYPE yylval YY_INITIAL_VALUE (= yyval_default);

    /* Number of syntax errors so far.  */
    int yynerrs = 0;

    yy_state_fast_t yystate = 0;
    /* Number of tokens to shift before error messages enabled.  */
    int yyerrstatus = 0;

    /* Refer to the stacks through separate pointers, to allow yyoverflow
       to reallocate them elsewhere.  */

    /* Their size.  */
    YYPTRDIFF_T yystacksize = YYINITDEPTH;

    /* The state stack: array, bottom, top.  */
    yy_state_t yyssa[YYINITDEPTH];
    yy_state_t *yyss = yyssa;
    yy_state_t *yyssp = yyss;

    /* The semantic value stack: array, bottom, top.  */
    YYSTYPE yyvsa[YYINITDEPTH];
    YYSTYPE *yyvs = yyvsa;
    YYSTYPE *yyvsp = yyvs;

  int yyn;
  /* The return value of yyparse.  */
  int yyresult;
  /* Lookahead symbol kind.  */
  yysymbol_kind_t yytoken = YYSYMBOL_YYEMPTY;
  /* The variables used to return semantic value and location from the
     action routines.  */
  YYSTYPE yyval;



#define YYPOPSTACK(N)   (yyvsp -= (N), yyssp -= (N))

  /* The number of symbols on the RHS of the reduced rule.
     Keep to zero when no symbol should be popped.  */
  int yylen = 0;

  YYDPRINTF ((stderr, "Starting parse\n"));

  yychar = YYEMPTY; /* Cause a token to be read.  */
  goto yysetstate;


/*------------------------------------------------------------.
| yynewstate -- push a new state, which is found in yystate.  |
`------------------------------------------------------------*/
yynewstate:
  /* In all cases, when you get here, the value and location stacks
     have just been pushed.  So pushing a state here evens the stacks.  */
  yyssp++;


/*--------------------------------------------------------------------.
| yysetstate -- set current state (the top of the stack) to yystate.  |
`--------------------------------------------------------------------*/
yysetstate:
  YYDPRINTF ((stderr, "Entering state %d\n", yystate));
  YY_ASSERT (0 <= yystate && yystate < YYNSTATES);
  YY_IGNORE_USELESS_CAST_BEGIN
  *yyssp = YY_CAST (yy_state_t, yystate);
  YY_IGNORE_USELESS_CAST_END
  YY_STACK_PRINT (yyss, yyssp);

  if (yyss + yystacksize - 1 <= yyssp)
#if !defined yyoverflow && !defined YYSTACK_RELOCATE
    goto yyexhaustedlab;
#else
    {
      /* Get the current used size of the three stacks, in elements.  */
      YYPTRDIFF_T yysize = yyssp - yyss + 1;

# if defined yyoverflow
      {
        /* Give user a chance to reallocate the stack.  Use copies of
           these so that the &'s don't force the real ones into
           memory.  */
        yy_state_t *yyss1 = yyss;
        YYSTYPE *yyvs1 = yyvs;

        /* Each stack pointer address is followed by the size of the
           data in use in that stack, in bytes.  This used to be a
           conditional around just the two extra args, but that might
           be undefined if yyoverflow is a macro.  */
        yyoverflow (YY_("memory exhausted"),
                    &yyss1, yysize * YYSIZEOF (*yyssp),
                    &yyvs1, yysize * YYSIZEOF (*yyvsp),
                    &yystacksize);
        yyss = yyss1;
        yyvs = yyvs1;
      }
# else /* defined YYSTACK_RELOCATE */
      /* Extend the stack our own way.  */
      if (YYMAXDEPTH <= yystacksize)
        goto yyexhaustedlab;
      yystacksize *= 2;
      if (YYMAXDEPTH < yystacksize)
        yystacksize = YYMAXDEPTH;

      {
        yy_state_t *yyss1 = yyss;
        union yyalloc *yyptr =
          YY_CAST (union yyalloc *,
                   YYSTACK_ALLOC (YY_CAST (YYSIZE_T, YYSTACK_BYTES (yystacksize))));
        if (! yyptr)
          goto yyexhaustedlab;
        YYSTACK_RELOCATE (yyss_alloc, yyss);
        YYSTACK_RELOCATE (yyvs_alloc, yyvs);
#  undef YYSTACK_RELOCATE
        if (yyss1 != yyssa)
          YYSTACK_FREE (yyss1);
      }
# endif

      yyssp = yyss + yysize - 1;
      yyvsp = yyvs + yysize - 1;

      YY_IGNORE_USELESS_CAST_BEGIN
      YYDPRINTF ((stderr, "Stack size increased to %ld\n",
                  YY_CAST (long, yystacksize)));
      YY_IGNORE_USELESS_CAST_END

      if (yyss + yystacksize - 1 <= yyssp)
        YYABORT;
    }
#endif /* !defined yyoverflow && !defined YYSTACK_RELOCATE */

  if (yystate == YYFINAL)
    YYACCEPT;

  goto yybackup;


/*-----------.
| yybackup.  |
`-----------*/
yybackup:
  /* Do appropriate processing given the current state.  Read a
     lookahead token if we need one and don't already have one.  */

  /* First try to decide what to do without reference to lookahead token.  */
  yyn = yypact[yystate];
  if (yypact_value_is_default (yyn))
    goto yydefault;

  /* Not known => get a lookahead token if don't already have one.  */

  /* YYCHAR is either empty, or end-of-input, or a valid lookahead.  */
  if (yychar == YYEMPTY)
    {
      YYDPRINTF ((stderr, "Reading a token\n"));
      yychar = yylex (&yylval);
    }

  if (yychar <= YYEOF)
    {
      yychar = YYEOF;
      yytoken = YYSYMBOL_YYEOF;
      YYDPRINTF ((stderr, "Now at end of input.\n"));
    }
  else if (yychar == YYerror)
    {
      /* The scanner already issued an error message, process directly
         to error recovery.  But do not keep the error token as
         lookahead, it is too special and may lead us to an endless
         loop in error recovery. */
      yychar = YYUNDEF;
      yytoken = YYSYMBOL_YYerror;
      goto yyerrlab1;
    }
  else
    {
      yytoken = YYTRANSLATE (yychar);
      YY_SYMBOL_PRINT ("Next token is", yytoken, &yylval, &yylloc);
    }

  /* If the proper action on seeing token YYTOKEN is to reduce or to
     detect an error, take that action.  */
  yyn += yytoken;
  if (yyn < 0 || YYLAST < yyn || yycheck[yyn] != yytoken)
    goto yydefault;
  yyn = yytable[yyn];
  if (yyn <= 0)
    {
      if (yytable_value_is_error (yyn))
        goto yyerrlab;
      yyn = -yyn;
      goto yyreduce;
    }

  /* Count tokens shifted since error; after three, turn off error
     status.  */
  if (yyerrstatus)
    yyerrstatus--;

  /* Shift the lookahead token.  */
  YY_SYMBOL_PRINT ("Shifting", yytoken, &yylval, &yylloc);
  yystate = yyn;
  YY_IGNORE_MAYBE_UNINITIALIZED_BEGIN
  *++yyvsp = yylval;
  YY_IGNORE_MAYBE_UNINITIALIZED_END

  /* Discard the shifted token.  */
  yychar = YYEMPTY;
  goto yynewstate;


/*-----------------------------------------------------------.
| yydefault -- do the default action for the current state.  |
`-----------------------------------------------------------*/
yydefault:
  yyn = yydefact[yystate];
  if (yyn == 0)
    goto yyerrlab;
  goto yyreduce;


/*-----------------------------.
| yyreduce -- do a reduction.  |
`-----------------------------*/
yyreduce:
  /* yyn is the number of a rule to reduce with.  */
  yylen = yyr2[yyn];

  /* If YYLEN is nonzero, implement the default value of the action:
     '$$ = $1'.

     Otherwise, the following line sets YYVAL to garbage.
     This behavior is undocumented and Bison
     users should not rely upon it.  Assigning to YYVAL
     unconditionally makes the parser a bit smaller, and it avoids a
     GCC warning that YYVAL may be used uninitialized.  */
  yyval = yyvsp[1-yylen];


  YY_REDUCE_PRINT (yyn);
  switch (yyn)
    {
  case 2: /* list_of_commands: cmd rol  */
#line 319 "parse.yy"
               {
        init_cmd_state();

      }
#line 1920 "parse.cc"
    break;

  case 3: /* list_of_commands: list_of_commands cmd rol  */
#line 324 "parse.yy"
      {
        init_cmd_state();
      }
#line 1928 "parse.cc"
    break;

  case 36: /* cmd: END_OF_INPUT  */
#line 363 "parse.yy"
     {
       //if(verbose&2)
         std::cout << "got an END_OF_INPUT\n";
        /* If we're processing a command file then quit parsing
         * when we run out of input */
	 //if(Gcmd_file_ref_count)
       	 //quit_parse = 1;
       YYABORT;
     }
#line 1942 "parse.cc"
    break;

  case 37: /* cmd: error  */
#line 372 "parse.yy"
             {

       init_cmd_state();
       yyclearin;
       // FIXME
       // In some cases we may wish to abort parsing while in others not.
       if (gAbortParserOnSyntaxError) {
         YYABORT;
       }
     }
#line 1957 "parse.cc"
    break;

  case 41: /* aborting: ABORT  */
#line 400 "parse.yy"
          {
       	  abort_gpsim = 1;
          quit_parse = 1;
          YYABORT;
          }
#line 1967 "parse.cc"
    break;

  case 42: /* attach_cmd: ATTACH SYMBOL_T gpsimObject_list  */
#line 409 "parse.yy"
          {
            attach.attach((yyvsp[-1].Symbol_P),(yyvsp[0].gpsimObjectList_P));
          }
#line 1975 "parse.cc"
    break;

  case 43: /* break_cmd: BREAK  */
#line 415 "parse.yy"
                                       {c_break.list();}
#line 1981 "parse.cc"
    break;

  case 44: /* break_cmd: BREAK LITERAL_INT_T  */
#line 416 "parse.yy"
                                       {c_break.list((yyvsp[0].Integer_P)->getVal());delete (yyvsp[0].Integer_P);}
#line 1987 "parse.cc"
    break;

  case 45: /* break_cmd: break_set  */
#line 417 "parse.yy"
                                       {
					  int n = (yyvsp[0].i);
					  if (n < 0)
					  {
					     yyerror("Breakpoint not set");
					  }
				       }
#line 1999 "parse.cc"
    break;

  case 46: /* log_cmd: LOG  */
#line 427 "parse.yy"
                                        {c_log.log();}
#line 2005 "parse.cc"
    break;

  case 47: /* log_cmd: LOG bit_flag  */
#line 428 "parse.yy"
                                        {c_log.log((yyvsp[0].co));}
#line 2011 "parse.cc"
    break;

  case 48: /* log_cmd: LOG bit_flag expr_list  */
#line 429 "parse.yy"
                                        {c_log.log((yyvsp[-1].co),(yyvsp[0].ExprList_P));}
#line 2017 "parse.cc"
    break;

  case 49: /* break_set: BREAK bit_flag expr_list  */
#line 434 "parse.yy"
                                         { (yyval.i)=c_break.set_break((yyvsp[-1].co),(yyvsp[0].ExprList_P));}
#line 2023 "parse.cc"
    break;

  case 50: /* break_set: BREAK bit_flag  */
#line 435 "parse.yy"
                                          {(yyval.i)=c_break.set_break((yyvsp[0].co));}
#line 2029 "parse.cc"
    break;

  case 51: /* break_set: BREAK SYMBOL_T  */
#line 436 "parse.yy"
                                          {(yyval.i)=c_break.set_break((yyvsp[0].Symbol_P));}
#line 2035 "parse.cc"
    break;

  case 52: /* bus_cmd: BUS  */
#line 440 "parse.yy"
                                        {c_bus.list_busses();}
#line 2041 "parse.cc"
    break;

  case 53: /* bus_cmd: BUS string_list  */
#line 441 "parse.yy"
                                        {c_bus.add_busses((yyvsp[0].StringList_P)); delete (yyvsp[0].StringList_P);}
#line 2047 "parse.cc"
    break;

  case 54: /* call_cmd: SYMBOL_T '(' expr_list ')'  */
#line 445 "parse.yy"
        {
          std::cout << " call\n";
          //$$ = $3;
        }
#line 2056 "parse.cc"
    break;

  case 55: /* clear_cmd: CLEAR expr  */
#line 451 "parse.yy"
                                        {clear.clear((yyvsp[0].Expression_P));}
#line 2062 "parse.cc"
    break;

  case 56: /* disassemble_cmd: DISASSEMBLE  */
#line 455 "parse.yy"
                                        {disassemble.disassemble(0);}
#line 2068 "parse.cc"
    break;

  case 57: /* disassemble_cmd: DISASSEMBLE expr  */
#line 456 "parse.yy"
                                        {disassemble.disassemble((yyvsp[0].Expression_P));}
#line 2074 "parse.cc"
    break;

  case 58: /* dump_cmd: DUMP  */
#line 460 "parse.yy"
                                        {dump.dump(2);}
#line 2080 "parse.cc"
    break;

  case 59: /* dump_cmd: DUMP bit_flag  */
#line 461 "parse.yy"
                                        {dump.dump((yyvsp[0].co)->value);}
#line 2086 "parse.cc"
    break;

  case 60: /* dump_cmd: DUMP bit_flag SYMBOL_T  */
#line 464 "parse.yy"
          {
            //                   key,  module_name
            quit_parse = dump.dump((yyvsp[-1].co)->value, (yyvsp[0].Symbol_P), NULL) == 0;
          }
#line 2095 "parse.cc"
    break;

  case 61: /* dump_cmd: DUMP bit_flag SYMBOL_T LITERAL_STRING_T  */
#line 470 "parse.yy"
          {
            //                   key,  module_name, filename
            //quit_parse = dump.dump($2->value, $3, $4->getVal()) == 0;
            if (dump.dump((yyvsp[-2].co)->value, (yyvsp[-1].Symbol_P), (yyvsp[0].String_P)->getVal()) == 0)
              std::cout << "dump to file failed\n";
            delete (yyvsp[0].String_P);

          }
#line 2108 "parse.cc"
    break;

  case 62: /* eval_cmd: SYMBOL_T  */
#line 482 "parse.yy"
                                              {c_symbol.dump_one((yyvsp[0].Symbol_P));}
#line 2114 "parse.cc"
    break;

  case 63: /* eval_cmd: '(' expr ')'  */
#line 490 "parse.yy"
                                        {
                                          c_symbol.EvaluateAndDisplay((yyvsp[-1].Expression_P));
                                          delete (yyvsp[-1].Expression_P);
                                        }
#line 2123 "parse.cc"
    break;

  case 64: /* eval_cmd: SYMBOL_T EQU_T expr  */
#line 494 "parse.yy"
                                        {

            Value *pValue = dynamic_cast<Value *>((yyvsp[-2].Symbol_P));
            if (pValue) {
              try {
                pValue->set((yyvsp[0].Expression_P));
              }
              catch(Error  const &Message)  {
                GetUserInterface().DisplayMessage("%s (maybe missing quotes?)\n", Message.what());
              }
              pValue->update();
            }
            delete (yyvsp[0].Expression_P);
          }
#line 2142 "parse.cc"
    break;

  case 65: /* eval_cmd: SYMBOL_T INDEXERLEFT_T expr_list INDEXERRIGHT_T  */
#line 510 "parse.yy"
                                        {
                                          c_symbol.dump((yyvsp[-3].Symbol_P),(yyvsp[-1].ExprList_P));
                                          (yyvsp[-1].ExprList_P)->clear();
                                          delete (yyvsp[-1].ExprList_P);
                                        }
#line 2152 "parse.cc"
    break;

  case 66: /* eval_cmd: SYMBOL_T INDEXERLEFT_T expr_list INDEXERRIGHT_T EQU_T expr  */
#line 516 "parse.yy"
                                        {
                                          c_symbol.Set((yyvsp[-5].Symbol_P), (yyvsp[-3].ExprList_P), (yyvsp[0].Expression_P));
                                          (yyvsp[-3].ExprList_P)->clear();
                                          delete (yyvsp[-3].ExprList_P);
                                          delete (yyvsp[0].Expression_P);
                                        }
#line 2163 "parse.cc"
    break;

  case 67: /* eval_cmd: REG_T '(' expr ')'  */
#line 523 "parse.yy"
                                        {
/*
					  int i=toInt($3);
					  if (i>=0)
					    c_x.x(toInt($3));
                                          delete $3;
*/  
					  c_x.x((yyvsp[-1].Expression_P));
                                        }
#line 2177 "parse.cc"
    break;

  case 68: /* eval_cmd: REG_T '(' expr ')' EQU_T expr  */
#line 533 "parse.yy"
                                        {
/*
					  int i=toInt($3);
					  if (i>=0)
					    c_x.x(toInt($3), $6);
                                          delete $3;
*/
					  c_x.x((yyvsp[-3].Expression_P), (yyvsp[0].Expression_P));
                                        }
#line 2191 "parse.cc"
    break;

  case 69: /* frequency_cmd: FREQUENCY  */
#line 545 "parse.yy"
                                        {frequency.print();}
#line 2197 "parse.cc"
    break;

  case 70: /* frequency_cmd: FREQUENCY expr  */
#line 546 "parse.yy"
                                        {frequency.set((yyvsp[0].Expression_P));}
#line 2203 "parse.cc"
    break;

  case 71: /* help_cmd: HELP  */
#line 550 "parse.yy"
                                        {help.help(); }
#line 2209 "parse.cc"
    break;

  case 72: /* help_cmd: HELP REG_T  */
#line 551 "parse.yy"
                                        {help.help("reg");}
#line 2215 "parse.cc"
    break;

  case 73: /* help_cmd: HELP LITERAL_STRING_T  */
#line 552 "parse.yy"
                                        {help.help((yyvsp[0].String_P)->getVal()); delete (yyvsp[0].String_P);}
#line 2221 "parse.cc"
    break;

  case 74: /* help_cmd: HELP SYMBOL_T  */
#line 553 "parse.yy"
                                        {help.help((yyvsp[0].Symbol_P));}
#line 2227 "parse.cc"
    break;

  case 75: /* list_cmd: LIST  */
#line 557 "parse.yy"
                                        {c_list.list();}
#line 2233 "parse.cc"
    break;

  case 76: /* list_cmd: LIST bit_flag  */
#line 558 "parse.yy"
                                        {c_list.list((yyvsp[0].co));}
#line 2239 "parse.cc"
    break;

  case 77: /* load_cmd: LOAD bit_flag LITERAL_STRING_T  */
#line 562 "parse.yy"
          {
            quit_parse = c_load.load((yyvsp[-1].co)->value,(yyvsp[0].String_P)->getVal()) == 0;
            delete (yyvsp[0].String_P);

            if(quit_parse)
            {
              quit_parse = 0;
              YYABORT;
            }
          }
#line 2254 "parse.cc"
    break;

  case 78: /* load_cmd: LOAD bit_flag SYMBOL_T LITERAL_STRING_T  */
#line 573 "parse.yy"
          {
            quit_parse = c_load.load((yyvsp[-2].co)->value, (yyvsp[-1].Symbol_P), (yyvsp[0].String_P)->getVal()) == 0;
            delete (yyvsp[0].String_P);

            if(quit_parse)
            {
              quit_parse = 0;
              YYABORT;
            }
	  }
#line 2269 "parse.cc"
    break;

  case 79: /* load_cmd: LOAD LITERAL_STRING_T  */
#line 585 "parse.yy"
          {
            quit_parse = c_load.load((yyvsp[0].String_P)->getVal(), (const char *)NULL) == 0;
            delete (yyvsp[0].String_P);
            quit_parse =0;

            if(quit_parse)
            {
              quit_parse = 0;
              YYABORT;
            }

          }
#line 2286 "parse.cc"
    break;

  case 80: /* load_cmd: LOAD SYMBOL_T  */
#line 599 "parse.yy"
          {
            quit_parse = c_load.load((yyvsp[0].Symbol_P)) == 0;
            quit_parse =0;

            if(quit_parse)
            {
              quit_parse = 0;
              YYABORT;
            }

          }
#line 2302 "parse.cc"
    break;

  case 81: /* load_cmd: LOAD SYMBOL_T SYMBOL_T  */
#line 612 "parse.yy"
          {
            //                        filename,   processor
            quit_parse = c_load.load((yyvsp[0].Symbol_P), (yyvsp[-1].Symbol_P)) == 0;
            delete (yyvsp[-1].Symbol_P);
            delete (yyvsp[0].Symbol_P);

            if(quit_parse)
            {
              quit_parse = 0;
              YYABORT;
            }
          }
#line 2319 "parse.cc"
    break;

  case 82: /* load_cmd: LOAD LITERAL_STRING_T LITERAL_STRING_T  */
#line 628 "parse.yy"
          {
            //                        filename,   processor
            quit_parse = c_load.load((yyvsp[0].String_P), (yyvsp[-1].String_P)) == 0;
            delete (yyvsp[-1].String_P);
            delete (yyvsp[0].String_P);

            if(quit_parse)
            {
              quit_parse = 0;
              YYABORT;
            }
          }
#line 2336 "parse.cc"
    break;

  case 83: /* node_cmd: NODE  */
#line 644 "parse.yy"
                                        {c_node.list_nodes();}
#line 2342 "parse.cc"
    break;

  case 84: /* node_cmd: NODE string_list  */
#line 645 "parse.yy"
                                        {c_node.add_nodes((yyvsp[0].StringList_P));  delete (yyvsp[0].StringList_P);}
#line 2348 "parse.cc"
    break;

  case 85: /* module_cmd: MODULE  */
#line 649 "parse.yy"
                                        {c_module.module();}
#line 2354 "parse.cc"
    break;

  case 86: /* module_cmd: MODULE bit_flag  */
#line 650 "parse.yy"
                                        {c_module.module((yyvsp[0].co));}
#line 2360 "parse.cc"
    break;

  case 87: /* module_cmd: MODULE string_option  */
#line 652 "parse.yy"
          {
            c_module.module((yyvsp[0].cos),(std::list<std::string> *)0);
            delete (yyvsp[0].cos);
          }
#line 2369 "parse.cc"
    break;

  case 88: /* module_cmd: MODULE string_option string_list  */
#line 657 "parse.yy"
          {
	    if ((yyvsp[-1].cos) != NULL && (yyvsp[0].StringList_P) != NULL)
                c_module.module((yyvsp[-1].cos), (yyvsp[0].StringList_P));
            if ((yyvsp[-1].cos) != NULL) delete (yyvsp[-1].cos);
            if ((yyvsp[0].StringList_P) != NULL) delete (yyvsp[0].StringList_P);
          }
#line 2380 "parse.cc"
    break;

  case 89: /* processor_cmd: PROCESSOR  */
#line 667 "parse.yy"
          {
            c_processor.processor();
          }
#line 2388 "parse.cc"
    break;

  case 90: /* processor_cmd: PROCESSOR bit_flag  */
#line 671 "parse.yy"
          {
            c_processor.processor((yyvsp[0].co)->value);
          }
#line 2396 "parse.cc"
    break;

  case 91: /* processor_cmd: PROCESSOR LITERAL_STRING_T  */
#line 675 "parse.yy"
          {
            c_processor.processor((yyvsp[0].String_P)->getVal(),0);
            delete (yyvsp[0].String_P);
          }
#line 2405 "parse.cc"
    break;

  case 92: /* processor_cmd: PROCESSOR LITERAL_STRING_T LITERAL_STRING_T  */
#line 680 "parse.yy"
          {
            c_processor.processor((yyvsp[-1].String_P)->getVal(),(yyvsp[0].String_P)->getVal());
            delete (yyvsp[-1].String_P);
            delete (yyvsp[0].String_P);
          }
#line 2415 "parse.cc"
    break;

  case 93: /* quit_cmd: QUIT  */
#line 688 "parse.yy"
          {
            quit_parse = 1;
	    YYABORT;
          }
#line 2424 "parse.cc"
    break;

  case 94: /* quit_cmd: QUIT expr  */
#line 693 "parse.yy"
          {
            quit_parse = 1;
	    //quit_state = $2;  // FIXME need to evaluate expr
	    YYABORT;
	  }
#line 2434 "parse.cc"
    break;

  case 95: /* reset_cmd: RESET  */
#line 701 "parse.yy"
                                        { reset.reset(); }
#line 2440 "parse.cc"
    break;

  case 96: /* run_cmd: RUN  */
#line 705 "parse.yy"
                                        { c_run.run();}
#line 2446 "parse.cc"
    break;

  case 97: /* set_cmd: SET  */
#line 709 "parse.yy"
                                        {c_set.set();}
#line 2452 "parse.cc"
    break;

  case 98: /* set_cmd: SET bit_flag  */
#line 710 "parse.yy"
                                        {c_set.set((yyvsp[0].co)->value,0);}
#line 2458 "parse.cc"
    break;

  case 99: /* set_cmd: SET bit_flag expr  */
#line 711 "parse.yy"
                                        {c_set.set((yyvsp[-1].co)->value,(yyvsp[0].Expression_P));}
#line 2464 "parse.cc"
    break;

  case 100: /* step_cmd: STEP  */
#line 715 "parse.yy"
                                        {step.step(1);}
#line 2470 "parse.cc"
    break;

  case 101: /* step_cmd: STEP expr  */
#line 716 "parse.yy"
                                        {
					    if ((yyvsp[0].Expression_P))
					    {
					    int i=toInt((yyvsp[0].Expression_P));
					    delete (yyvsp[0].Expression_P);
				            if (i >=1)
						step.step(i);
					    else
						yyerror("Invalid value");
					    }
					}
#line 2486 "parse.cc"
    break;

  case 102: /* step_cmd: STEP bit_flag  */
#line 727 "parse.yy"
                                        {step.over();}
#line 2492 "parse.cc"
    break;

  case 103: /* shell_cmd: SHELL  */
#line 731 "parse.yy"
                                        {c_shell.shell((yyvsp[0].String_P)); delete (yyvsp[0].String_P);}
#line 2498 "parse.cc"
    break;

  case 104: /* stimulus_cmd: STIMULUS  */
#line 735 "parse.yy"
          {
          c_stimulus.stimulus();
          }
#line 2506 "parse.cc"
    break;

  case 105: /* stimulus_cmd: STIMULUS cmd_subtype  */
#line 739 "parse.yy"
          {
          c_stimulus.stimulus((yyvsp[0].co)->value);
          }
#line 2514 "parse.cc"
    break;

  case 106: /* stimulus_cmd: stimulus_cmd stimulus_opt  */
#line 743 "parse.yy"
          {
          /* do nothing */
          }
#line 2522 "parse.cc"
    break;

  case 107: /* stimulus_cmd: stimulus_cmd END_OF_COMMAND  */
#line 747 "parse.yy"
          {
            if(verbose)
              std::cout << " end of stimulus command\n";
            c_stimulus.end();
          }
#line 2532 "parse.cc"
    break;

  case 108: /* stimulus_opt: expression_option  */
#line 757 "parse.yy"
          {
            if(verbose)
              std::cout << "parser sees stimulus with numeric option\n";
            c_stimulus.stimulus((yyvsp[0].coe));
          }
#line 2542 "parse.cc"
    break;

  case 109: /* stimulus_opt: stimulus_opt bit_flag  */
#line 763 "parse.yy"
          {
            if(verbose)
              std::cout << "parser sees stimulus with bit flag: " << (yyvsp[0].co)->value << '\n';
            c_stimulus.stimulus((yyvsp[0].co)->value);
          }
#line 2552 "parse.cc"
    break;

  case 110: /* stimulus_opt: stimulus_opt string_option  */
#line 769 "parse.yy"
          {
            if(verbose)
              std::cout << "parser sees stimulus with string option\n";
            c_stimulus.stimulus((yyvsp[0].cos));
          }
#line 2562 "parse.cc"
    break;

  case 111: /* stimulus_opt: stimulus_opt array  */
#line 775 "parse.yy"
          {
            if(verbose)
              std::cout << "parser sees stimulus with an array\n";
            c_stimulus.stimulus((yyvsp[0].ExprList_P));
          }
#line 2572 "parse.cc"
    break;

  case 112: /* symbol_cmd: SYMBOL  */
#line 784 "parse.yy"
                                        {c_symbol.dump_all();}
#line 2578 "parse.cc"
    break;

  case 113: /* symbol_cmd: SYMBOL LITERAL_STRING_T EQU_T literal  */
#line 786 "parse.yy"
          {
            c_symbol.add_one((yyvsp[-2].String_P)->getVal(), (yyvsp[0].Expression_P));
            delete (yyvsp[-2].String_P);
            delete (yyvsp[0].Expression_P);
          }
#line 2588 "parse.cc"
    break;

  case 114: /* symbol_cmd: SYMBOL LITERAL_STRING_T  */
#line 792 "parse.yy"
          {
		c_symbol.dump_one((yyvsp[0].String_P)->getVal()); 
		delete (yyvsp[0].String_P);
	  }
#line 2597 "parse.cc"
    break;

  case 115: /* symbol_cmd: SYMBOL SYMBOL_T  */
#line 797 "parse.yy"
          {
		c_symbol.dump_one((yyvsp[0].Symbol_P));
	  }
#line 2605 "parse.cc"
    break;

  case 116: /* trace_cmd: TRACE  */
#line 804 "parse.yy"
                                        { c_trace.trace(); }
#line 2611 "parse.cc"
    break;

  case 117: /* trace_cmd: TRACE expr  */
#line 805 "parse.yy"
                                        { c_trace.trace((yyvsp[0].Expression_P)); }
#line 2617 "parse.cc"
    break;

  case 118: /* trace_cmd: TRACE numeric_option  */
#line 806 "parse.yy"
                                        { c_trace.trace((yyvsp[0].con)); }
#line 2623 "parse.cc"
    break;

  case 119: /* trace_cmd: TRACE string_option  */
#line 807 "parse.yy"
                                        { c_trace.trace((yyvsp[0].cos)); }
#line 2629 "parse.cc"
    break;

  case 120: /* trace_cmd: TRACE bit_flag  */
#line 808 "parse.yy"
                                        { c_trace.trace((yyvsp[0].co)); }
#line 2635 "parse.cc"
    break;

  case 121: /* trace_cmd: TRACE expression_option  */
#line 809 "parse.yy"
                                        { c_trace.trace((yyvsp[0].coe)); }
#line 2641 "parse.cc"
    break;

  case 122: /* version_cmd: gpsim_VERSION  */
#line 812 "parse.yy"
                                        {version.version();}
#line 2647 "parse.cc"
    break;

  case 123: /* x_cmd: X  */
#line 815 "parse.yy"
                                        { c_x.x();}
#line 2653 "parse.cc"
    break;

  case 124: /* x_cmd: X expr  */
#line 816 "parse.yy"
                                        { c_x.x((yyvsp[0].Expression_P)); }
#line 2659 "parse.cc"
    break;

  case 125: /* icd_cmd: ICD  */
#line 820 "parse.yy"
                                        { c_icd.icd(); }
#line 2665 "parse.cc"
    break;

  case 126: /* icd_cmd: ICD string_option  */
#line 821 "parse.yy"
                                        { c_icd.icd((yyvsp[0].cos)); }
#line 2671 "parse.cc"
    break;

  case 127: /* macro_cmd: MACRO  */
#line 842 "parse.yy"
                                        { c_macro.list();}
#line 2677 "parse.cc"
    break;

  case 128: /* macro_cmd: macrodef_directive  */
#line 843 "parse.yy"
                                        { }
#line 2683 "parse.cc"
    break;

  case 129: /* macro_cmd: MACROINVOCATION_T  */
#line 844 "parse.yy"
                                        { lexer_InvokeMacro((yyvsp[0].Macro_P)); }
#line 2689 "parse.cc"
    break;

  case 130: /* $@1: %empty  */
#line 850 "parse.yy"
                                        {c_macro.define((yyvsp[-1].String_P)->getVal()); delete (yyvsp[-1].String_P);}
#line 2695 "parse.cc"
    break;

  case 131: /* $@2: %empty  */
#line 852 "parse.yy"
                                        {lexer_setMacroBodyMode();}
#line 2701 "parse.cc"
    break;

  case 134: /* opt_mdef_arglist: LITERAL_STRING_T  */
#line 860 "parse.yy"
          {
            c_macro.add_parameter((yyvsp[0].String_P)->getVal());
	    delete (yyvsp[0].String_P);
	  }
#line 2710 "parse.cc"
    break;

  case 135: /* opt_mdef_arglist: opt_mdef_arglist ',' LITERAL_STRING_T  */
#line 865 "parse.yy"
          {
	    c_macro.add_parameter((yyvsp[0].String_P)->getVal());
	    delete (yyvsp[0].String_P);
	  }
#line 2719 "parse.cc"
    break;

  case 137: /* mdef_body: mdef_body_  */
#line 874 "parse.yy"
                                        {; }
#line 2725 "parse.cc"
    break;

  case 138: /* mdef_body_: MACROBODY_T  */
#line 878 "parse.yy"
                                        {c_macro.add_body((yyvsp[0].s));}
#line 2731 "parse.cc"
    break;

  case 139: /* mdef_body_: mdef_body_ MACROBODY_T  */
#line 879 "parse.yy"
                                        {c_macro.add_body((yyvsp[0].s));}
#line 2737 "parse.cc"
    break;

  case 140: /* mdef_end: ENDM  */
#line 883 "parse.yy"
                                        {c_macro.end_define();}
#line 2743 "parse.cc"
    break;

  case 141: /* mdef_end: LITERAL_STRING_T ENDM  */
#line 884 "parse.yy"
                                        {c_macro.end_define((yyvsp[-1].String_P)->getVal()); delete (yyvsp[-1].String_P); }
#line 2749 "parse.cc"
    break;

  case 142: /* $@3: %empty  */
#line 905 "parse.yy"
                     {
		       std::cout << "declaration\n";
		       lexer_setDeclarationMode();
		     }
#line 2758 "parse.cc"
    break;

  case 143: /* $@4: %empty  */
#line 910 "parse.yy"
                     {
		       std::cout << " type:" << (yyvsp[0].i) << '\n';
		     }
#line 2766 "parse.cc"
    break;

  case 144: /* declaration_cmd: '\\' $@3 opt_declaration_type $@4 LITERAL_STRING_T  */
#line 914 "parse.yy"
                     {
		       std::cout << "identifier: " << (yyvsp[0].String_P)->getVal() << '\n';  delete (yyvsp[0].String_P);
		     }
#line 2774 "parse.cc"
    break;

  case 145: /* opt_declaration_type: %empty  */
#line 921 "parse.yy"
                             { (yyval.i)=0; }
#line 2780 "parse.cc"
    break;

  case 146: /* opt_declaration_type: DECLARE_INT_T  */
#line 922 "parse.yy"
                          { (yyval.i) = 1; std::cout << "int type\n"; }
#line 2786 "parse.cc"
    break;

  case 147: /* opt_declaration_type: DECLARE_FLOAT_T  */
#line 923 "parse.yy"
                          { (yyval.i) = 2; std::cout << "float type\n"; }
#line 2792 "parse.cc"
    break;

  case 148: /* opt_declaration_type: DECLARE_BOOL_T  */
#line 924 "parse.yy"
                          { (yyval.i) = 3; std::cout << "bool type\n"; }
#line 2798 "parse.cc"
    break;

  case 149: /* opt_declaration_type: DECLARE_CHAR_T  */
#line 925 "parse.yy"
                          { (yyval.i) = 4; std::cout << "char type\n"; }
#line 2804 "parse.cc"
    break;

  case 150: /* bit_flag: BIT_FLAG  */
#line 950 "parse.yy"
      {
	 (yyval.co) = (yyvsp[0].co);
      }
#line 2812 "parse.cc"
    break;

  case 151: /* cmd_subtype: CMD_SUBTYPE  */
#line 956 "parse.yy"
      {
	 (yyval.co) = (yyvsp[0].co);
      }
#line 2820 "parse.cc"
    break;

  case 152: /* expression_option: EXPRESSION_OPTION expr  */
#line 961 "parse.yy"
                                          { (yyval.coe) = new cmd_options_expr((yyvsp[-1].co),(yyvsp[0].Expression_P)); }
#line 2826 "parse.cc"
    break;

  case 153: /* numeric_option: NUMERIC_OPTION expr  */
#line 965 "parse.yy"
        {

	        (yyval.con) = new cmd_options_num;
	        (yyval.con)->co = (yyvsp[-1].co);
	      }
#line 2836 "parse.cc"
    break;

  case 154: /* string_option: STRING_OPTION LITERAL_STRING_T  */
#line 974 "parse.yy"
        {
          (yyval.cos) = new cmd_options_str((yyvsp[0].String_P)->getVal());
          (yyval.cos)->co  = (yyvsp[-1].co);
          if(verbose&2)
            std::cout << " name " << (yyval.cos)->co->name << " value " << (yyval.cos)->str << " got a string option \n";
          delete (yyvsp[0].String_P);
        }
#line 2848 "parse.cc"
    break;

  case 155: /* string_option: STRING_OPTION SYMBOL_T  */
#line 982 "parse.yy"
        {
          String *pValue = dynamic_cast<String*>((yyvsp[0].Symbol_P));
          if(pValue != NULL) {
            (yyval.cos) = new cmd_options_str(pValue->getVal());
            (yyval.cos)->co  = (yyvsp[-1].co);
            if(verbose&2)
              std::cout << " name " << (yyval.cos)->co->name << " value " << (yyval.cos)->str << " got a symbol option \n";
          }
          else {
            std::cout << " symbol option '"
                 << (yyvsp[0].Symbol_P)->name()
                 << "' is not a string\n";
	    (yyval.cos) = NULL;
          }
          //delete $2;
        }
#line 2869 "parse.cc"
    break;

  case 156: /* string_list: LITERAL_STRING_T  */
#line 1001 "parse.yy"
                                                  {(yyval.StringList_P) = new StringList_t(); (yyval.StringList_P)->push_back((yyvsp[0].String_P)->getVal()); delete (yyvsp[0].String_P);}
#line 2875 "parse.cc"
    break;

  case 157: /* string_list: string_list LITERAL_STRING_T  */
#line 1002 "parse.yy"
                                                  {(yyvsp[-1].StringList_P)->push_back((yyvsp[0].String_P)->getVal()); delete (yyvsp[0].String_P);}
#line 2881 "parse.cc"
    break;

  case 158: /* expr: binary_expr  */
#line 1008 "parse.yy"
                                        {(yyval.Expression_P)=(yyvsp[0].BinaryOperator_P);}
#line 2887 "parse.cc"
    break;

  case 159: /* expr: unary_expr  */
#line 1009 "parse.yy"
                                        {(yyval.Expression_P)=(yyvsp[0].Expression_P);}
#line 2893 "parse.cc"
    break;

  case 160: /* expr: REG_T '(' expr ')'  */
#line 1010 "parse.yy"
                                                        {(yyval.Expression_P)=new RegisterExpression(toInt((yyvsp[-1].Expression_P)));
                                                         delete (yyvsp[-1].Expression_P); }
#line 2900 "parse.cc"
    break;

  case 161: /* array: '{' expr_list '}'  */
#line 1014 "parse.yy"
                                        {(yyval.ExprList_P)=(yyvsp[-1].ExprList_P);}
#line 2906 "parse.cc"
    break;

  case 162: /* gpsimObject: GPSIMOBJECT_T '(' SYMBOL_T ')'  */
#line 1018 "parse.yy"
          {
            // Ex: pin(MyVariable)  -- where MyVariable is the name of a symbol
            //  This allows one to programmatically select a particular pin number.

	    // If Symbol has an integer type, assume it is a CPU pin number
	    // otherwise assume it is a stimulus such as a pin name
	    if (typeid(*(yyvsp[-1].Symbol_P)) == typeid(Integer))
	    {
                (yyval.gpsimObject_P) = toStimulus((yyvsp[-1].Symbol_P));
   	    }
            else
	        (yyval.gpsimObject_P) = (yyvsp[-1].Symbol_P);

            //$$=new Pin_t(Pin_t::ePackageBased | Pin_t::eActiveProc, $3);
          }
#line 2926 "parse.cc"
    break;

  case 163: /* gpsimObject: GPSIMOBJECT_T '(' LITERAL_INT_T ')'  */
#line 1034 "parse.yy"
          {
            // Ex: pin(8)  -- select a particular pin in the package
            (yyval.gpsimObject_P) = toStimulus((yyvsp[-1].Integer_P)->getVal());
            delete (yyvsp[-1].Integer_P);
          }
#line 2936 "parse.cc"
    break;

  case 164: /* gpsimObject: SYMBOL_T  */
#line 1040 "parse.yy"
          {
            // The symbol should be a stimulus. This is for the attach command.
            // Ex:  attach Node1 portb0
            // The scanner will find portb0 and return it to us here as a SYMBOL_T
            (yyval.gpsimObject_P) = (yyvsp[0].Symbol_P); //dynamic_cast<stimulus *>($1);
          }
#line 2947 "parse.cc"
    break;

  case 165: /* gpsimObject_list: gpsimObject  */
#line 1060 "parse.yy"
                                           {(yyval.gpsimObjectList_P) = new gpsimObjectList_t(); (yyval.gpsimObjectList_P)->push_back((yyvsp[0].gpsimObject_P));}
#line 2953 "parse.cc"
    break;

  case 166: /* gpsimObject_list: gpsimObject_list gpsimObject  */
#line 1061 "parse.yy"
                                           {if ((yyvsp[0].gpsimObject_P)) (yyvsp[-1].gpsimObjectList_P)->push_back((yyvsp[0].gpsimObject_P));}
#line 2959 "parse.cc"
    break;

  case 167: /* expr_list: expr  */
#line 1065 "parse.yy"
                                        {(yyval.ExprList_P) = new ExprList_t(); (yyval.ExprList_P)->push_back((yyvsp[0].Expression_P));}
#line 2965 "parse.cc"
    break;

  case 168: /* expr_list: expr_list ',' expr  */
#line 1066 "parse.yy"
                                        {(yyvsp[-2].ExprList_P)->push_back((yyvsp[0].Expression_P)); }
#line 2971 "parse.cc"
    break;

  case 169: /* binary_expr: expr PLUS_T expr  */
#line 1070 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpAdd((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 2977 "parse.cc"
    break;

  case 170: /* binary_expr: expr MINUS_T expr  */
#line 1071 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpSub((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 2983 "parse.cc"
    break;

  case 171: /* binary_expr: expr MPY_T expr  */
#line 1072 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpMpy((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 2989 "parse.cc"
    break;

  case 172: /* binary_expr: expr DIV_T expr  */
#line 1073 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpDiv((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 2995 "parse.cc"
    break;

  case 173: /* binary_expr: expr AND_T expr  */
#line 1074 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpAnd((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3001 "parse.cc"
    break;

  case 174: /* binary_expr: expr OR_T expr  */
#line 1075 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpOr((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3007 "parse.cc"
    break;

  case 175: /* binary_expr: expr XOR_T expr  */
#line 1076 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpXor((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3013 "parse.cc"
    break;

  case 176: /* binary_expr: expr SHL_T expr  */
#line 1077 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpShl((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3019 "parse.cc"
    break;

  case 177: /* binary_expr: expr SHR_T expr  */
#line 1078 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpShr((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3025 "parse.cc"
    break;

  case 178: /* binary_expr: expr EQ_T expr  */
#line 1079 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpEq((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3031 "parse.cc"
    break;

  case 179: /* binary_expr: expr NE_T expr  */
#line 1080 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpNe((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3037 "parse.cc"
    break;

  case 180: /* binary_expr: expr LT_T expr  */
#line 1081 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpLt((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3043 "parse.cc"
    break;

  case 181: /* binary_expr: expr GT_T expr  */
#line 1082 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpGt((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3049 "parse.cc"
    break;

  case 182: /* binary_expr: expr LE_T expr  */
#line 1083 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpLe((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3055 "parse.cc"
    break;

  case 183: /* binary_expr: expr GE_T expr  */
#line 1084 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpGe((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3061 "parse.cc"
    break;

  case 184: /* binary_expr: expr LAND_T expr  */
#line 1085 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpLogicalAnd((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3067 "parse.cc"
    break;

  case 185: /* binary_expr: expr LOR_T expr  */
#line 1086 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpLogicalOr((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3073 "parse.cc"
    break;

  case 186: /* binary_expr: expr COLON_T expr  */
#line 1087 "parse.yy"
                                        {(yyval.BinaryOperator_P) = new OpAbstractRange((yyvsp[-2].Expression_P), (yyvsp[0].Expression_P));}
#line 3079 "parse.cc"
    break;

  case 187: /* unary_expr: literal  */
#line 1091 "parse.yy"
                                        {(yyval.Expression_P)=(yyvsp[0].Expression_P);}
#line 3085 "parse.cc"
    break;

  case 188: /* unary_expr: PLUS_T unary_expr  */
#line 1092 "parse.yy"
                                                        {(yyval.Expression_P) = new OpPlus((yyvsp[0].Expression_P));}
#line 3091 "parse.cc"
    break;

  case 189: /* unary_expr: MINUS_T unary_expr  */
#line 1093 "parse.yy"
                                                        {(yyval.Expression_P) = new OpNegate((yyvsp[0].Expression_P));}
#line 3097 "parse.cc"
    break;

  case 190: /* unary_expr: ONESCOMP_T unary_expr  */
#line 1094 "parse.yy"
                                                        {(yyval.Expression_P) = new OpOnescomp((yyvsp[0].Expression_P));}
#line 3103 "parse.cc"
    break;

  case 191: /* unary_expr: LNOT_T unary_expr  */
#line 1095 "parse.yy"
                                                        {(yyval.Expression_P) = new OpLogicalNot((yyvsp[0].Expression_P));}
#line 3109 "parse.cc"
    break;

  case 192: /* unary_expr: MPY_T unary_expr  */
#line 1096 "parse.yy"
                                                        {(yyval.Expression_P) = new OpIndirect((yyvsp[0].Expression_P));}
#line 3115 "parse.cc"
    break;

  case 193: /* unary_expr: AND_T unary_expr  */
#line 1097 "parse.yy"
                                                        {(yyval.Expression_P) = new OpAddressOf((yyvsp[0].Expression_P));}
#line 3121 "parse.cc"
    break;

  case 194: /* unary_expr: '(' expr ')'  */
#line 1098 "parse.yy"
                                                        {(yyval.Expression_P)=(yyvsp[-1].Expression_P);}
#line 3127 "parse.cc"
    break;

  case 195: /* literal: LITERAL_INT_T  */
#line 1101 "parse.yy"
                                        {(yyval.Expression_P) = new LiteralInteger((yyvsp[0].Integer_P));}
#line 3133 "parse.cc"
    break;

  case 196: /* literal: LITERAL_BOOL_T  */
#line 1102 "parse.yy"
                                        {(yyval.Expression_P) = new LiteralBoolean((yyvsp[0].Boolean_P));}
#line 3139 "parse.cc"
    break;

  case 197: /* literal: LITERAL_STRING_T  */
#line 1103 "parse.yy"
                                        {(yyval.Expression_P) = new LiteralString((yyvsp[0].String_P));}
#line 3145 "parse.cc"
    break;

  case 198: /* literal: LITERAL_FLOAT_T  */
#line 1104 "parse.yy"
                                        {(yyval.Expression_P) = new LiteralFloat((yyvsp[0].Float_P));}
#line 3151 "parse.cc"
    break;

  case 199: /* literal: SYMBOL_T  */
#line 1105 "parse.yy"
                                        {
					  try {
					  (yyval.Expression_P) = new LiteralSymbol((yyvsp[0].Symbol_P));
					  }
  					  catch (Error const &err) {
					     yyerror(err.what());
				    	     delete (yyvsp[0].Symbol_P);
					     YYERROR;
  					   }
					}
#line 3166 "parse.cc"
    break;

  case 200: /* literal: SYMBOL_T INDEXERLEFT_T expr_list INDEXERRIGHT_T  */
#line 1115 "parse.yy"
                                                            {(yyval.Expression_P) = new IndexedSymbol((yyvsp[-3].Symbol_P),(yyvsp[-1].ExprList_P));}
#line 3172 "parse.cc"
    break;

  case 201: /* literal: LITERAL_ARRAY_T  */
#line 1116 "parse.yy"
                                        {(yyval.Expression_P) = new LiteralArray((yyvsp[0].ExprList_P)); }
#line 3178 "parse.cc"
    break;


#line 3182 "parse.cc"

      default: break;
    }
  /* User semantic actions sometimes alter yychar, and that requires
     that yytoken be updated with the new translation.  We take the
     approach of translating immediately before every use of yytoken.
     One alternative is translating here after every semantic action,
     but that translation would be missed if the semantic action invokes
     YYABORT, YYACCEPT, or YYERROR immediately after altering yychar or
     if it invokes YYBACKUP.  In the case of YYABORT or YYACCEPT, an
     incorrect destructor might then be invoked immediately.  In the
     case of YYERROR or YYBACKUP, subsequent parser actions might lead
     to an incorrect destructor call or verbose syntax error message
     before the lookahead is translated.  */
  YY_SYMBOL_PRINT ("-> $$ =", YY_CAST (yysymbol_kind_t, yyr1[yyn]), &yyval, &yyloc);

  YYPOPSTACK (yylen);
  yylen = 0;

  *++yyvsp = yyval;

  /* Now 'shift' the result of the reduction.  Determine what state
     that goes to, based on the state we popped back to and the rule
     number reduced by.  */
  {
    const int yylhs = yyr1[yyn] - YYNTOKENS;
    const int yyi = yypgoto[yylhs] + *yyssp;
    yystate = (0 <= yyi && yyi <= YYLAST && yycheck[yyi] == *yyssp
               ? yytable[yyi]
               : yydefgoto[yylhs]);
  }

  goto yynewstate;


/*--------------------------------------.
| yyerrlab -- here on detecting error.  |
`--------------------------------------*/
yyerrlab:
  /* Make sure we have latest lookahead translation.  See comments at
     user semantic actions for why this is necessary.  */
  yytoken = yychar == YYEMPTY ? YYSYMBOL_YYEMPTY : YYTRANSLATE (yychar);
  /* If not already recovering from an error, report this error.  */
  if (!yyerrstatus)
    {
      ++yynerrs;
      yyerror (YY_("syntax error"));
    }

  if (yyerrstatus == 3)
    {
      /* If just tried and failed to reuse lookahead token after an
         error, discard it.  */

      if (yychar <= YYEOF)
        {
          /* Return failure if at end of input.  */
          if (yychar == YYEOF)
            YYABORT;
        }
      else
        {
          yydestruct ("Error: discarding",
                      yytoken, &yylval);
          yychar = YYEMPTY;
        }
    }

  /* Else will try to reuse lookahead token after shifting the error
     token.  */
  goto yyerrlab1;


/*---------------------------------------------------.
| yyerrorlab -- error raised explicitly by YYERROR.  |
`---------------------------------------------------*/
yyerrorlab:
  /* Pacify compilers when the user code never invokes YYERROR and the
     label yyerrorlab therefore never appears in user code.  */
  if (0)
    YYERROR;

  /* Do not reclaim the symbols of the rule whose action triggered
     this YYERROR.  */
  YYPOPSTACK (yylen);
  yylen = 0;
  YY_STACK_PRINT (yyss, yyssp);
  yystate = *yyssp;
  goto yyerrlab1;


/*-------------------------------------------------------------.
| yyerrlab1 -- common code for both syntax error and YYERROR.  |
`-------------------------------------------------------------*/
yyerrlab1:
  yyerrstatus = 3;      /* Each real token shifted decrements this.  */

  /* Pop stack until we find a state that shifts the error token.  */
  for (;;)
    {
      yyn = yypact[yystate];
      if (!yypact_value_is_default (yyn))
        {
          yyn += YYSYMBOL_YYerror;
          if (0 <= yyn && yyn <= YYLAST && yycheck[yyn] == YYSYMBOL_YYerror)
            {
              yyn = yytable[yyn];
              if (0 < yyn)
                break;
            }
        }

      /* Pop the current state because it cannot handle the error token.  */
      if (yyssp == yyss)
        YYABORT;


      yydestruct ("Error: popping",
                  YY_ACCESSING_SYMBOL (yystate), yyvsp);
      YYPOPSTACK (1);
      yystate = *yyssp;
      YY_STACK_PRINT (yyss, yyssp);
    }

  YY_IGNORE_MAYBE_UNINITIALIZED_BEGIN
  *++yyvsp = yylval;
  YY_IGNORE_MAYBE_UNINITIALIZED_END


  /* Shift the error token.  */
  YY_SYMBOL_PRINT ("Shifting", YY_ACCESSING_SYMBOL (yyn), yyvsp, yylsp);

  yystate = yyn;
  goto yynewstate;


/*-------------------------------------.
| yyacceptlab -- YYACCEPT comes here.  |
`-------------------------------------*/
yyacceptlab:
  yyresult = 0;
  goto yyreturn;


/*-----------------------------------.
| yyabortlab -- YYABORT comes here.  |
`-----------------------------------*/
yyabortlab:
  yyresult = 1;
  goto yyreturn;


#if !defined yyoverflow
/*-------------------------------------------------.
| yyexhaustedlab -- memory exhaustion comes here.  |
`-------------------------------------------------*/
yyexhaustedlab:
  yyerror (YY_("memory exhausted"));
  yyresult = 2;
  goto yyreturn;
#endif


/*-------------------------------------------------------.
| yyreturn -- parsing is finished, clean up and return.  |
`-------------------------------------------------------*/
yyreturn:
  if (yychar != YYEMPTY)
    {
      /* Make sure we have latest lookahead translation.  See comments at
         user semantic actions for why this is necessary.  */
      yytoken = YYTRANSLATE (yychar);
      yydestruct ("Cleanup: discarding lookahead",
                  yytoken, &yylval);
    }
  /* Do not reclaim the symbols of the rule whose action triggered
     this YYABORT or YYACCEPT.  */
  YYPOPSTACK (yylen);
  YY_STACK_PRINT (yyss, yyssp);
  while (yyssp != yyss)
    {
      yydestruct ("Cleanup: popping",
                  YY_ACCESSING_SYMBOL (+*yyssp), yyvsp);
      YYPOPSTACK (1);
    }
#ifndef yyoverflow
  if (yyss != yyssa)
    YYSTACK_FREE (yyss);
#endif

  return yyresult;
}

#line 1119 "parse.yy"


       // parsing is over

//--------------------------
// This initialization could be done by the compiler. However
// it requires two passes through because the token values are
// defined by the parser output (eg. y.tab.h) while at the same
// time the parser depends on the .h files in which these classes
// are defined.

void initialize_commands(void)
{
  static bool initialized = 0;

  if(initialized)
    return;

  if(verbose)
    std::cout << __FUNCTION__ << "()\n";

  attach.token_value = ATTACH;
  c_break.token_value = BREAK;
  // c_bus.token_value = BUS;
  clear.token_value = CLEAR;
  disassemble.token_value = DISASSEMBLE;
  dump.token_value = DUMP;
  frequency.token_value = FREQUENCY;
  help.token_value = HELP;
  c_list.token_value = LIST;
  c_load.token_value = LOAD;
  c_log.token_value = LOG;
  c_macro.token_value = MACRO;
  c_module.token_value = MODULE;
  c_node.token_value = NODE;
  c_processor.token_value = PROCESSOR;
  quit.token_value = QUIT;
  reset.token_value = RESET;
  c_run.token_value = RUN;
  c_set.token_value = SET;
  step.token_value = STEP;
  c_stimulus.token_value = STIMULUS;
  c_symbol.token_value = SYMBOL;
  c_trace.token_value = TRACE;
  version.token_value = gpsim_VERSION;
  c_x.token_value = X;
  c_icd.token_value = ICD;
  c_shell.token_value = SHELL;

  initialized = 1;

  parser_spanning_lines = 0;
  parser_warnings = 1; // display parser warnings.
}
