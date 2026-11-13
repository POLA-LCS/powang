# N6 native parity report

Status: in progress. This report records the N6 integration results. The
remaining gates are listed at the end.

## Environment

- Platform: Windows, `win32`
- Compiler: `g++` 16.1.0, C++17, `-O2`, static link
- Python oracle: the Python VM (`--engine=vm`) and the tree walker
  (`--engine=tree`)
- Native runtime: `build/native/libpwb_runtime.a` and the generated
  `temp.cpp` integrated executable

## Correctness results

| Gate | Result |
|---|---|
| Full Python VM suite | 650 tests, all pass |
| Full tree walker suite (`POWANG_ENGINE=tree`) | 650 tests, all pass |
| Native N1 corpus | 5 programs, zero mismatches |
| Native N2 corpus | 6 programs, zero mismatches |
| Native N3 corpus | 9 programs, zero mismatches |
| Native N4 corpus | 30 programs, zero mismatches |
| Native N5 corpus | 9 programs, zero mismatches |
| Examples corpus | 32 programs, zero mismatches |
| Seeded fuzz seed 7 | 1000 programs, zero mismatches |
| Seeded fuzz seed 2026 | 1000 programs, zero mismatches |
| Runtime access control and ambiguity | 13 cases, zero mismatches |
| Native C++ tests | 1 of 1 CTest target passes |

The differential comparison covers standard output, standard error and exit
code. Top-level language diagnostics are compared on standard output. Module
warnings are compared on standard error.

## Performance

The CPU bound benchmark is a 200,000 iteration integer accumulation loop. Each
engine ran three times and the median wall time is reported.

| Engine | Median wall time |
|---|---|
| Native | about 66 ms |
| Tree walker | about 7.8 s |
| Python VM | about 8.5 s |

The native runtime is about 117 times faster than the tree walker and about 128
times faster than the Python VM on this loop. The N6 target of at least three
times the tree walker is met on the CPU bound corpus without inline caches or
threaded dispatch.

Small program runs are dominated by the integrated `g++` compile. The warm
executable cache keys on the generated source and the runtime library
timestamp. A small program measured 1.12 seconds cold and 0.29 seconds warm,
against 0.24 seconds for the tree walker, a warm ratio of 1.23 times. The
`native clean` command removes the cache. A 50 KB source program with a 50,000
character string compiled in 1.12 seconds cold and 0.46 seconds warm, below the
ten second cold and five second warm compile gates.

## N6 features delivered

1. `--engine=native` file, project and check-only routing.
2. `src.vm.native.differential` with `--corpus`, `--examples`, `--json` and
   `--fail-fast`.
3. `powang vm native diff`, `bench`, `clean` and `pack`.
4. Casts, typed declaration coercion, field defaults, named user type
   constructors, match patterns, destructuring, typed arithmetic, spreads from
   all containers, generic overload filtering and `typedeep` for tuples and
   sets.
5. Structure and element lock enforcement, runtime private field and method
   access control, private static methods, and operator or trait method
   ambiguity error text.
6. The default scalar host bridge for `math`, `strings`, `json`, `url`,
   `crypto`, `time` and `env`.

## N3 closure

N3 is gate green. `tests/native/corpus/n3` has 8 differential programs.
`tests/test_native_access_control.py` checks 13 runtime cases against the
Python VM: private fields, private methods, private statics, failed-method
access reset, locked array and container methods, constant references, and
operator and trait method ambiguity. The native `--no-check` flag now skips
the Python checker before the native compile.

## Seeded fuzz status

The native differential runner accepts `--fuzz --seed N --count N` and
compares generated programs against the Python VM. Both gates pass with zero
mismatches:

| Seed | Programs | Passed | Failed |
|---|---|---|---|
| 7 | 1000 | 1000 | 0 |
| 2026 | 1000 | 1000 | 0 |

The fuzz pass covers weak `nova` ordering and error text, mixed bool and char
arithmetic, modulo cast rules, negative number reversal and checker warnings
emitted before a compile or check error. The generator, the runner, the cache
and the comparison path are implemented.

## Stress results

`tests/test_native_stress.py` starts the compiled native executable 100 times
and runs 200 task lifecycles, 100 lazy and 100 worker. Every startup returns
zero, every task settles, no process leaks and the expected task sums match.

## Remaining gates

1. Optional inline caches and threaded dispatch.
2. The default engine decision and the `0.25.0` release.
3. The full Python host module surface and true parallel worker execution.
