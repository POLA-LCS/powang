# Arithmetics
This is a helpful file that list the interaction between native types using the __+, -, * and /__ operators:
  
## Nov
Throws an ERROR in any arithmetic operation.

## Bool
If the main operand it's a bool, the result will be always a bool. (see [Example logical](../examples/logical.po))

# Arithmetic Operation Behaviors (Operator OperandType1 OperandType2)

## Addition (+)
- `+ number number = number → number + number`
- `+ number string = string → number as string + string`
- `+ number list   = number → number + length of string`
- `+ string number = number → string + number as char`
- `+ string string = string → string concatenation`
- `+ string list   =        → repeat addition by each value from list`
- `+ list number   = list   → append number to list`
- `+ list string   = list   → append string to list`
- `+ list list     = list   → concatenate lists`

## Subtraction (-)
- `- number number = number → number - number`
- `- number string = string → string + number as string`
- `- number list   = list   → removes the first number elements from list`
- `- string number = string → number as char + string`
- `- string string = string → remove from "left" all the "right"s`
- `- string list   =        → repeat substraction by each value from list`
- `- list number   = list   → removes the last number elements`
- `- list string   = list   → remove elements corresponding to ord(char) for each char in string`
- `- list list     = list   → remove all occurrences of each element in right from left`

## Multiplication (*)
- `* number number = number → number * number`
- `* number string = string → repeat string by number`
- `* number list   = list   → repeat list by number`
- `* string number = string → repeat string by number`
- `* string string = number → count occurrences of right in left`
- `* string list   =        → repeat multiplication by each value from list`
- `* list number   = list   → repeat list by number`
- `* list string   = number → count occurrences of string in list`
- `* list list     = list   → repeat multiplication by each value from list`

## Division (/)
- `/ number number = number → number / number`
- `/ number string = list   → split string into substrings of length number, from start to end`
- `/ number list   = list   → split list into number amount of lists`
- `/ string number = list   → split string into substrings of length number, from end to start`
- `/ string string = list   → split string by right string`
- `/ string list   = list   → repeat division by each value from list`
- `/ list number   = list   → slice list with into steps of length number`
- `/ list string   = list   → divide list by the ascii representation for each char in string`
- `/ list list     = list   → repeat division by each value from list`

All other combinations return nov.