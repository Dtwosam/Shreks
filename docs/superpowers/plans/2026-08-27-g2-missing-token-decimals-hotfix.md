# G2 production hotfix — missing token decimals

Date: 2026-08-27

## Physical production evidence

The immutable ARM64 PAPER release `shreks-4bf1b8819803e11220c05ba8e6fb2b5fff9e9b3d` activated successfully on the dedicated VPS and completed five consecutive PAPER campaign cycles. The next cycle failed closed. A read-only replay against checkpoint sequence 6 reproduced the exact underlying exception:

`ObserverCampaignCoordinatorError: observer candidate 55 assembly failed: token decimals are required to reconstruct persisted paper quotes`

The replay state had zero open positions and no pending entry. The failure occurred during cycle assembly.

## Root cause

Persisted Jupiter ENTRY/EXIT quote evidence could exist before Observer V2 had persisted token decimals for the same candidate. E15 requires token decimals to reconstruct exact economic `PaperQuote` values, but absence of that reconstruction metadata is incomplete evidence rather than contradictory evidence. The assembler incorrectly terminated the whole PAPER campaign instead of preserving the raw evidence while withholding any reconstructable execution quote.

## TDD evidence

RED commit: `c1d55c39aab9dc49ce3bf57f6fa99e9acc61bf7b`.

RED CI run: `33081563871`.

The regression reproduced the physical failure exactly: `1 failed, 2618 passed`, failing only on `token decimals are required to reconstruct persisted paper quotes`.

GREEN implementation commit: `afbb8943d086b59923463924af3502edab2440e7`.

GREEN CI run: `33081941096`.

All gates passed:

- repository safety GREEN;
- Python GREEN, `2619 passed`;
- Rust GREEN;
- native ARM64 release-build verification GREEN.

Merged behavior commit: `e055d4f7761ae7fe70114ccd6d0a5e9de9850907` via PR #58.

## Preserved safety invariants

- Missing token decimals never synthesize token precision, price, quantity, notional, or a `PaperQuote`.
- Without a reconstructed ENTRY `PaperQuote`, a PAPER entry fill is impossible.
- Without a reconstructed EXIT `PaperQuote`, exit execution evidence is treated as unknown/unavailable for execution semantics rather than guessed.
- Raw persisted quote timestamps and fingerprints remain available for audit/safety provenance.
- Malformed or contradictory persisted evidence continues to fail closed through the existing quote/evidence validation paths.
- No strategy threshold, capital limit, manifest, secret, systemd unit, provider identity, or LIVE execution behavior changed.
- LIVE remains disabled.

This documentation-only commit is the production release seal for the second physical commissioning hotfix.
