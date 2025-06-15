# Arithmetics
This is a helpful file that list the interaction between native types using the __+, -, * and /__ operators:
  
## NOV
Throws an ERROR in any arithmetic operation.
  
## Number
  
`(+ number number) => number = (number data) + (number data)`  
`(- number number) => number = (number data) - (number data)`  
`(* number number) => number = (number data) * (number data)`  
`(/ number number) => number = (number data) / (number data)`  
  
### Addition
`(+ number string) => number = (number data) + (string length)`  
`(+ number list) => number = (number data) + (list length)`  
  
### Substraction
`(- number string) => string = pops from the left the number amount of chars`  
`(- number list) => list = pops from the left the number amount of items`  
  
### Multiplication
`(* number string) = (* string number)`  
`(* number list) = (* list number)`  
  
### Division
`(/ number string) => list of strings = splits the string by the number amount of steps | ej. (/ 2 'hello') = ['he' 'll' 'o']`  
`(/ number list) => list = splits the list by the number amount of steps | ej. (/ 2 [1 2 3 4 5]) = [ [1 2] [3 4] [5] ]`  
  
## String
  
`(+ string string) => string = appends the second string at the end of the first string`  
`(+ string number) => string = converts number into string and perform (+ string string)`  
`(+ string list) => string = appends all the elements from the list into the string`  