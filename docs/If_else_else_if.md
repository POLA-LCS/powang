# Control flow: If | Powang Documentation
This is a helpful file that explains the behaviour of the control flow: if.

## About
The if keyword it's powerful, and it's complemented with other keyword such as:
- `else` : Runs a block of code if the expression is false
- `ends` : Ends the code block of the actual statement (if or else)

Beyond that, else can act like an if too!  
This makes the "else" keyword an optional "else if".  

### Basic syntax (if)
```
if expression
    ## statement
ends
```

### Expanded syntax (if else):  
```
if expression
    ## true statement
else
    ## false statement
ends
```

### New feature! (else if)
```
if expression
    ## ...
else else_if_expression
    ## ...
else
    ## ...
ends
```

### Quick if
This quick if it's called like that because  
it's an if expression that evaluates into a special value.  
This is similar to the ternary operator in some languages but this goes further  
letting you to open an if scope and assign in a comfortable way.  
see [If example](../examples/if.po).  

```
var result (if expression true_value false_value)
    ## this scope can see "result"
ends
## this scope CAN'T see "result" (because it doesn't exists anymore)
```

The true_value evaluates when the expression is true, this means the false_value doesn't evaluates.  
The false_value evaluates when the experssion is false, this means the true_value doesn't evaluates.  

### Quick if quick ends
The quick ends is the last supported argument for the "if" keyword.  
If a quick if is detected you can quick end the scope by using the "ends" keyword.

```
var result (if expression true_value false_value ends)
## this scope CAN see "result" (because there's no scope that wraps the "var result")
```