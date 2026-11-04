" Vim syntax file for Powang
if exists("b:current_syntax")
  finish
endif

syn keyword powangKeyword if else for fun return use type extern try catch finally spawn export
syn keyword powangBuiltin output format printf error fail input typeof size open write read close system spawn wait cancel task_status
syn keyword powangConstant nova true false this

syn match powangComment "##.*$"
syn region powangString start='"' end='"' skip='\\"' contains=powangStringEscape
syn match powangStringEscape contained '\\[ntr0\\"]'

syn match powangNumber '\d\+\.\d\+\([eE][+-]\?\d\+\)\?'
syn match powangNumber '\d\+[eE][+-]\?\d\+'
syn match powangNumber '\d\+'

syn match powangOperator '&&\|||\|::|!:'
syn match powangOperator '==\|!=\|<=\|>=\|<\|>'
syn match powangOperator '+=\|-=\|\*=\|/=\|='
syn match powangOperator '+\|-\|\*\|/\|%'
syn match powangOperator '\[\+\]\|\[\-\]'
syn match powangOperator '\?\|>>\|@\|!\|&'

hi link powangKeyword Keyword
hi link powangBuiltin Function
hi link powangConstant Constant
hi link powangComment Comment
hi link powangString String
hi link powangStringEscape Special
hi link powangNumber Number
hi link powangOperator Operator

let b:current_syntax = "powang"