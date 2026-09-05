# Core j04 launch notes — accepted j03 producer input bound

These are implementation clarifications within the approved semantic contract. The producer gate is now fulfilled by `.ralph/receipts/sch073-j03.json`; core execution is authorized, while final protected merges remain held.

- Record the accepted full spec SHA and the SHA256 of the current index, full semantic corpus, complete case-ID inventory, and structured runtime obligations. Load an immutable clean spec clone and prove its Git HEAD and hashes; do not depend on a sibling checkout's name or an uncommitted correction tree.
- Keep the dual parity arms separate. Run the frozen legacy 32-kind spec/generator checks against the exact old core input. Run current 35-kind exported dataclass/field/alias and semantic-fixture checks against the real new core. Do not make the historical generator claim 35 kinds or rewrite frozen legacy documents to accommodate the new core.
- For every negative semantic fixture, first demonstrate support with a valid new-kind seed. Require its declared parse/validate phase and rule/diagnostic; an unsupported kind, generic exception, or missing file must not produce a false passing negative.
- The full corpus ID set and structured runtime obligation IDs cannot silently shrink. Map obligations to concrete executable node IDs, parameters, formats, counts and outcomes. Static producer integrity is not proof of runtime behavior.
- Explicitly set the accepted spec path and require fingerprint fixtures. Existing discovery fallbacks are not evidence of consuming the accepted spec; missing or mismatched required inputs fail the gate.
- Build and verify the new source, wheel and sdist in separate environments; launch installed-package tests outside source roots with package-origin proof. Retain artifacts and hashes for MCP j05's isolated local wheelhouse. Neither public publishing nor a sibling-source import is a dependency-resolution workaround.
- Preserve the real frozen old 0.7.2 artifact arm and its honest unsupported-new-kind behavior. The new library's legacy-profile diagnostic is a distinct arm.
- Required semantic/artifact cases have zero skips or xfails. Preserve the documented optional production-corpus absence as an explicit separate limitation, never fabricate production coverage from synthetic fixtures.
- No package release, shared main/stage/master movement, Cloud code, GUI restart, or shared environment install. Original run/POST/trace evidence is immutable; corrections receive new commits and separate measured receipts.

This note accompanies the approved core card. The separately recorded immutable receipt, not this explanatory note, establishes producer acceptance.
