# KaTeX local assets

KaTeX 0.19.0 from the official npm package, MIT license in `LICENSE`.
Package integrity: `sha512-v6Tznz3zJ7u3niRCoDTsumM2+HA2XXcCu+WAacCeHD2z3p9A9Ks987o5FzfTGBN0e8A0vjEgIDvLbICrXpdw/Q==`.

The original `dist/katex.min.js`, CSS and twenty WOFF2 fonts are vendored so
runtime rendering requires no CDN. CSS fallback references to WOFF/TTF were
removed; all referenced WOFF2 files are included. These redistributable KaTeX
font assets are distinct from the operating-system fonts used for report text.
Runtime options disable trust, bound expansion/size and expose MathML.
Upstream: https://katex.org/ and https://github.com/KaTeX/KaTeX .
