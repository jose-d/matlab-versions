# matlab-versions

Translate between the identifiers of a MATLAB release. Every release has
several, and they are easy to mix up:

| Release | MATLAB version | Runtime version | Runtime folder | FlexLM licence (lmstat) |
|---|---|---|---|---|
| R2015b | 8.6 | **9.0** | v90 | v34 |
| R2016a | **9.0** | 9.0.1 | v901 | v35 |
| R2021a | 9.10 | 9.10 | v910 | v45 |
| R2023a | 9.14 | 9.14 | R2023a | v49 |
| R2024a | 24.1 | 24.1 | R2024a | v51 |

- **MATLAB version:** what `version()` and `VersionInfo.xml` report. It used
  the 7.x, 8.x and 9.x scheme up to R2023a, then switched to year.half (23.2,
  24.1, …).
- **MATLAB Runtime version:** what a compiled application needs. It is usually
  the same as the MATLAB version, but not always (R2012a = 7.17, R2015b = 9.0,
  R2016a = 9.0.1). The Runtime installs under a folder named `v910` up to
  R2022a and under the release name (`R2022b`) from R2022b.
- **Licence version:** what a client checks out from a FlexLM licence server.
  `lmutil lmstat -a` prints it on every checkout line, so a licence server
  admin can see which release each client runs:

  ```
      bob host2 /dev/tty (v51) (lic.example.org/27000 3423), start Tue 11/10 10:15
                         ^^^^^ R2024a
  ```

The table covers R2006a to R2026b, with evidence and sources for each value.
It has no dependencies and needs Python 3.9 or newer.

## Install

```bash
pip install matlab-versions
```

## Python

```python
>>> import matlab_versions as mv
>>> mv.release("R2024a")                       # also "2024a"
Release(name='R2024a', matlab='24.1', runtime='24.1', license=51, evidence={...}, sources={...})
>>> mv.from_matlab("9.10.0.1739362 (R2021a)")  # full version() strings work
Release(name='R2021a', matlab='9.10', runtime='9.10', license=45, ...)
>>> mv.from_runtime("v901").name               # version or install folder
'R2016a'
>>> mv.from_license("v51").name                # also 51, "v51.0"
'R2024a'
>>> mv.release("R2016a").runtime_folder
'v901'
>>> mv.release("R2030a")                       # newer than the table: computed from the rules
Release(name='R2030a', matlab='30.1', runtime='30.1', license=63, evidence={'matlab': 'extrapolated', ...})
```

Some numbers mean different releases depending on what they are: `9.0` is
the MATLAB version of R2016a but the Runtime version of R2015b. So each
`from_*` function reads its input one way only. `lookup()` returns every
possible reading:

```python
>>> [(kind, r.name) for kind, r in mv.lookup("9.0")]
[('matlab', 'R2016a'), ('runtime', 'R2015b')]
```

### lmstat output

```python
>>> for c in mv.parse_lmstat(text):            # full `lmutil lmstat -a` output
...     print(c.feature, c.user, c.host, c.release)
MATLAB bob host2 R2024a
```

`parse_checkout(line)` parses a single checkout line and returns a `Checkout`
with `user`, `host`, `display`, `version`, `server`, `port`, `handle`, `start`,
`pid` and `release`. It returns `None` for any other line.

## Command line

```
$ matlab-versions 9.14 9.0 v51
9.14 (MATLAB version, Runtime)  R2023a  matlab 9.14  runtime 9.14 (R2023a)  license v49
9.0 (MATLAB version)            R2016a  matlab 9.0   runtime 9.0.1 (v901)   license v35
9.0 (Runtime)                   R2015b  matlab 8.6   runtime 9.0 (v90)      license v34
v51 (licence version)           R2024a  matlab 24.1  runtime 24.1 (R2024a)  license v51

$ lmutil lmstat -a -c 27000@licserver | matlab-versions            # one line per checkout
MATLAB  bob     host2   v51     R2024a

$ lmutil lmstat -a -c 27000@licserver | matlab-versions --summary  # count per feature and release
MATLAB  R2024a  1

$ matlab-versions --table    # every release (* = extrapolated)
$ matlab-versions --json     # the full table with rules, sources and caveats
```

## Evidence

Each value in the table has its own evidence level:

- **observed:** seen side by side with its release in a primary artefact. That
  means an installation's `VersionInfo.xml`, a licence file with a `# Rxxxx`
  header above its `INCREMENT` lines, an lmstat checkout from a client of a
  known release, or a MathWorks documentation example.
- **documented:** listed in a published table (MathWorks or an independent
  compilation), but not checked against an artefact.
- **extrapolated:** follows from the rule, but no source was found.

Sources:

- MATLAB versions: [Wikipedia's release table](https://en.wikipedia.org/wiki/MATLAB#Release_history),
  checked against four installations.
- Runtime versions: [MathWorks' MATLAB Runtime page](https://www.mathworks.com/products/compiler/matlab-runtime.html).
- Runtime folder names: [MathWorks Answers 438125](https://www.mathworks.com/matlabcentral/answers/438125-how-can-i-determine-if-matlab-or-matlab-runtime-are-installed).
- Licence versions: MathWorks publishes no official table. They come from
  public licence files, the
  [MathWorks licence file example](https://www.mathworks.com/help/install/ug/network-license-files.html),
  [MATLAB Answers 277493](https://www.mathworks.com/matlabcentral/answers/277493-what-does-version-v35-with-lmutil-mean)
  and own observations.

`matlab-versions --json` lists the sources for every value.

## Rules for new releases

MathWorks ships two releases a year. Releases newer than the table resolve
automatically and are marked `extrapolated`:

- MATLAB and Runtime version: two-digit year, then `.1` for "a" and `.2` for
  "b" (R2027a = 27.1).
- Licence version: from R2007a, exactly +1 per release:
  `2 * (year - 2008) + 19 + (1 if b else 0)`.

To confirm a value, open an issue or pull request with the evidence: a
`VersionInfo.xml` line, an lmstat checkout line or a licence file header.
Leave out keys, since only the version field is needed.

## Caveats

- The version on a licence file's `INCREMENT` lines, and on lmstat's
  `"MATLAB" vNN` feature header, is the **newest release the licence allows**,
  not what clients run. Only the `(vNN)` on a checkout line identifies the
  client.
- Toolboxes share MATLAB's licence version within a release. The exception is
  discontinued or frozen products, which keep the number of their last
  release. For example, Stateflow_Coder stays at 24. Use MATLAB checkouts when
  you count clients by release.
- Toolbox product versions (e.g. Statistics and Machine Learning Toolbox 24.1)
  are not covered.

## Disclaimer

Not affiliated with or endorsed by The MathWorks, Inc. MATLAB and Simulink are
registered trademarks of The MathWorks, Inc. FlexLM and FlexNet are trademarks
of Flexera.

## License

MIT
