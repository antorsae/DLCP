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
