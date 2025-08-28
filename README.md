# Katla location helper

Katla helper for generating LaTeX macros based on source locations in Idris
files


## Usage

Display style:


```hs
-- <fact>
fact : Nat -> Nat
fact Z = S Z
fact (S n) = n * fact n
-- </fact>
```

Inline style:

```hs
fact : {- <nat> -} Nat {- </nat> -} -> Nat
fact Z = S Z
fact (S n) = n * fact n
```

Use `--help` to show options.