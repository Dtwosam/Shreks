# FL1 Fast Lane Production Acceptance

This is the physical-host acceptance workflow for FL1/FL1.5 direct Pump and PumpSwap ingestion. Repository CI proves the reporter and ingestion code; **CI is necessary but insufficient** for the production exit gate. The gate passes only with evidence captured from the real dedicated host while the observer is running its verified immutable release.

**LIVE TRADING: DISABLED**

The routine workflow is read-only with respect to Shreks runtime state. It does not start, stop, kill, mutate, migrate, trade, sign, submit, or change PAPER/LIVE authority. The only files created by these commands are operator-owned acceptance evidence files outside the SQLite database.

## 1. Preconditions and immutable release identity

Use the existing verified GitHub-to-VPS release path. `/opt/shreks/current` must resolve to `/opt/shreks/releases/<40-character-sha>` and that directory must contain its verified `RELEASE_MANIFEST.json`.

Create a private operator-owned evidence directory first so every precondition and measurement can be retained without changing runtime ownership:

```bash
umask 077
EVIDENCE_DIR="$HOME/shreks-fast-lane-acceptance-$(date +%Y%m%dT%H%M%S)"
mkdir -p "$EVIDENCE_DIR"
readlink -f /opt/shreks/current | tee "$EVIDENCE_DIR/current-release.txt"
cat /opt/shreks/current/RELEASE_MANIFEST.json | tee "$EVIDENCE_DIR/RELEASE_MANIFEST.json"
systemctl is-active shreks.target | tee "$EVIDENCE_DIR/target-precondition.txt"
systemctl is-active shreks-observe.service | tee "$EVIDENCE_DIR/observer-precondition.txt"
```

The resolved release SHA and the manifest `source_sha` must match exactly. The release manifest must include `target/release/shreks-observe`; FL1.5 acceptance must run through that already-allowlisted immutable payload as the `fast-lane-acceptance` subcommand. A locally compiled, copied, edited, or unmanifested observer is not valid production evidence.

Use the authoritative persistent observer database:

```text
/var/lib/shreks/shreks.db
```

The current FL1 broad-capture contract is **official public Solana only**. Pump-wide realtime capture and read-only lifecycle/transaction verification use the official public Solana RPC/WSS endpoints and must retain truthful `solana_public` provenance. Paid provider credentials such as Helius, Chainstack, or Alchemy may remain in protected host configuration for other isolated services, but the production observer's broad FL1 lane must not consult them, silently fall back to them, or relabel public traffic as a paid source.

PumpSwap remains bounded. Whenever FL1 realtime is enabled, the deployed observer must have positive host-side `SHREKS_PUMPSWAP_TRACKING_MAX_AGE_SECONDS` and `SHREKS_PUMPSWAP_MAX_TRACKED_POOLS` values. The accepted topology is Pump-wide public-Solana logs plus only the bounded set of verified recent PumpSwap pool addresses. A global PumpSwap AMM subscription is not acceptable.

Paper-evidence is a separate service and has separate provider economics. Its Helius/Jupiter requirements, `SHREKS_PAPER_HELIUS_MAX_REQUESTS_PER_PROCESS`, and `SHREKS_PAPER_HOLDER_REFRESH_SECONDS` must not be presented as observer FL1 provider usage. Likewise, a paper-evidence Helius counter or quota event does not prove anything about the observer's public-Solana broad lane.

Public Solana has no Shreks paid-provider request budget to reset. Operational acceptance therefore focuses on stable public endpoint progress, bounded PumpSwap scope, truthful `solana_public` provenance, restart stability, and proof that the broad observer lane does not create paid provider consumption. If the public endpoint cannot sustain representative traffic, FL1.5 is a HOLD; do not make the gate pass by silently enabling a metered provider.

Do not copy provider credentials, environment secrets, wallet material, dashboard credentials, Telegram tokens, signing material, provider account identifiers, or raw provider portal pages containing secret/account data into the evidence directory. If a paid-provider portal exposes useful counters, retain only non-secret numeric totals/time windows needed to demonstrate that broad observer usage did not increase them.

## 2. Evidence boundary

### Database-backed evidence

`shreks-observe fast-lane-acceptance` opens SQLite with `SQLITE_OPEN_READ_ONLY` and reports only evidence already present in the durable FL1 tables plus filesystem size metadata. The subcommand dispatches before normal observer runtime/provider configuration, so acceptance does not require provider credentials or initialize market-data providers.

It reports:

- raw Pump event count for the selected window;
- raw PumpSwap event count for the selected window;
- canonical FastEvent count for the selected window;
- `pump_conflict_quarantine_total`, the total durable Pump conflicting variants retained for forensics;
- `pumpswap_conflict_quarantine_total`, the total durable PumpSwap conflicting variants retained for forensics;
- `pump_conflict_quarantine_events`, the Pump conflicting variants observed inside the selected acceptance window;
- `pumpswap_conflict_quarantine_events`, the PumpSwap conflicting variants observed inside the selected acceptance window;
- `canonical_conflict_quarantine_violations`, the count of canonical identities that also have a venue-specific quarantined conflicting variant;
- current pending Pump backlog;
- current pending PumpSwap backlog;
- canonical sequence-integrity violations;
- chain occurrence -> source observation latency;
- source observation -> canonical acceptance latency;
- chain occurrence -> canonical acceptance latency;
- database and WAL bytes at report time.

The reporter does not perform provider calls and cannot measure an attempted duplicate delivery that was rejected before it became a second durable row. Do not invent a duplicate-attempt count from SQLite. Quarantine counts are durable evidence of conflicting economic variants, not a count of all network replay attempts.

### Provider-provenance evidence

FL1 raw and canonical rows retain the actual realtime provider ID. Capture a read-only provider breakdown for the same half-open interval `[START_MS, END_MS)` without exposing credentials:

```bash
sudo -u shreks python3 - "$DB" "$START_MS" "$END_MS" > "$EVIDENCE_DIR/provider-counts.txt" <<'PY'
import sqlite3
import sys

path, start_ms, end_ms = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
queries = [
    ("pump_raw", "pump_trade_evidence", "observed_at_unix_ms"),
    ("pumpswap_raw", "pump_swap_trade_evidence", "observed_at_unix_ms"),
    ("canonical", "fast_events", "observed_at_unix_ms"),
]
for label, table, time_column in queries:
    print(f"[{label}]")
    rows = connection.execute(
        f"SELECT provider, COUNT(*) FROM {table} "
        f"WHERE {time_column} >= ? AND {time_column} < ? "
        "GROUP BY provider ORDER BY provider",
        (start_ms, end_ms),
    ).fetchall()
    for provider, count in rows:
        print(f"{provider}={count}")
connection.close()
PY
```

This query is evidence-only and must remain `mode=ro`. For a post-deploy interval on the current release, FL1 Pump/PumpSwap raw rows and their canonical descendants must show `solana_public` provenance consistent with the report's activity counts. Any `helius`, `chainstack`, or `alchemy` FL1 provenance inside that new interval is a HOLD until explained because the current broad observer lane has no paid-provider fallback. Never relabel an unexpected source to make the evidence fit.

### Provider-consumption evidence

Provider consumption is operational evidence, not a SQLite fact. Retain all non-secret evidence available for the same interval, including:

- the exact immutable release SHA and its public-Solana realtime topology;
- observer journal lines showing public-RPC/WSS connection, rate-limit, disconnect, reconnect, or supervision failures, if any;
- service restart count so instability cannot be hidden by process churn;
- non-secret Helius/Chainstack/Alchemy numeric counter totals before and after the interval when they are available, strictly as corroboration that broad observer activity did not increase paid usage;
- an explicit statement when reliable paid-provider counter data is unavailable rather than inventing a number.

The production observer's public-Solana broad lane has no paid-provider process budget. Paper-evidence Helius request ceilings and holder-refresh controls remain independent and must not be attributed to observer FL1. A bounded public-Solana topology plus `solana_public` provenance is architectural evidence of the zero-paid-provider lane; paid-provider counter deltas, when available, are additional operational corroboration.

If public endpoint reliability is poor, record the failure literally. Do not enable Helius, Chainstack, Alchemy, a paid PumpPortal feed, or another metered source as an unreviewed fallback. A still-global PumpSwap AMM subscription, any hidden paid fallback, or unexplained paid-provider counter growth is incompatible with this acceptance contract.

### Host-only evidence

Capture these separately over the same physical-host interval:

- observer service state and `NRestarts`;
- observer PID, CPU, and RSS;
- host memory and filesystem headroom;
- database/WAL size before and after the interval for DB/WAL growth;
- observer public-RPC/reconnect journal lines, including persistent rate-limit/disconnect instability or unexpected paid-provider activity;
- exact release SHA and exact interval timestamps.

Provider/reconnect logs are the source for reconnect behavior and any visible attempted duplicate/replay overlap. If the logs do not expose a trustworthy attempted duplicate count, record that metric as unavailable rather than fabricating it.

## 3. Start one representative interval

Choose a window long enough to observe both Pump bonding-curve and PumpSwap traffic. Zero traffic from either lane does not prove that lane on the production host; extend the window instead of treating silence as success.

Capture the starting wall clock and database/WAL sizes. The database directory is intentionally protected; read metadata as the `shreks` service identity rather than changing ownership/permissions or running the checks as the operator account:

```bash
DB=/var/lib/shreks/shreks.db
START_MS="$(date +%s%3N)"
START_ISO="$(date --iso-8601=seconds)"
printf '%s\n' "$START_MS" > "$EVIDENCE_DIR/window-start-ms.txt"
printf '%s\n' "$START_ISO" > "$EVIDENCE_DIR/window-start-iso.txt"
sudo -u shreks test -r "$DB"
{
  sudo -u shreks stat -c '%n %s' "$DB"
  if sudo -u shreks test -e "$DB-wal"; then
    sudo -u shreks stat -c '%n %s' "$DB-wal"
  else
    printf '%s\n' "$DB-wal absent"
  fi
} | tee "$EVIDENCE_DIR/storage-before.txt"
systemctl show shreks-observe.service -p ActiveState -p SubState -p NRestarts -p MainPID -p ExecMainStatus | tee "$EVIDENCE_DIR/observer-before.txt"
```

The absence of a WAL file at one instant is not by itself a failure; retain that fact literally and compare with the end state. A permission failure is also not a reason to `chmod`/`chown` production state—investigate service identity/ownership instead.

Let the normal production observer run without intervention for the chosen representative interval. Do not use this acceptance procedure to induce a restart, alter public-endpoint behavior, or mutate service state.

## 4. End the interval and run the read-only reporter

Capture the end timestamp and host state, again reading protected database metadata as `shreks`:

```bash
END_MS="$(date +%s%3N)"
END_ISO="$(date --iso-8601=seconds)"
printf '%s\n' "$END_MS" > "$EVIDENCE_DIR/window-end-ms.txt"
printf '%s\n' "$END_ISO" > "$EVIDENCE_DIR/window-end-iso.txt"
{
  sudo -u shreks stat -c '%n %s' "$DB"
  if sudo -u shreks test -e "$DB-wal"; then
    sudo -u shreks stat -c '%n %s' "$DB-wal"
  else
    printf '%s\n' "$DB-wal absent"
  fi
} | tee "$EVIDENCE_DIR/storage-after.txt"
systemctl show shreks-observe.service -p ActiveState -p SubState -p NRestarts -p MainPID -p ExecMainStatus | tee "$EVIDENCE_DIR/observer-after.txt"
```

Resolve the observer PID and capture process/host resource evidence without changing it:

```bash
OBSERVER_PID="$(systemctl show shreks-observe.service -p MainPID --value)"
ps -p "$OBSERVER_PID" -o pid=,etimes=,%cpu=,rss=,vsz=,stat=,cmd= | tee "$EVIDENCE_DIR/observer-process.txt"
free -h | tee "$EVIDENCE_DIR/memory.txt"
df -h /var/lib/shreks /opt/shreks | tee "$EVIDENCE_DIR/filesystem.txt"
```

Capture observer logs for the same interval:

```bash
sudo journalctl -u shreks-observe.service --since "$START_ISO" --until "$END_ISO" --no-pager | tee "$EVIDENCE_DIR/observer-window.log"
```

Run acceptance through the verified observer payload as the unprivileged runtime identity. The operator shell opens the private evidence file, while the subcommand itself retains only the `shreks` user's database access:

```bash
sudo -u shreks /opt/shreks/current/target/release/shreks-observe fast-lane-acceptance \
  /var/lib/shreks/shreks.db \
  "$START_MS" \
  "$END_MS" \
  > "$EVIDENCE_DIR/fast-lane-report.txt"
```

Then capture the provider-provenance breakdown from Section 2 using the same `DB`, `START_MS`, and `END_MS` values, plus any non-secret paid-provider counter evidence available for that exact interval.

The acceptance command must exit `0`. A nonzero exit means missing/incompatible schema, invalid timing, unreadable storage evidence, or another fail-closed condition; investigate it rather than overriding it.

## 5. Database-backed acceptance checks

Read the captured report. The minimum integrity requirements are:

```text
sequence_integrity_violations=0
canonical_conflict_quarantine_violations=0
pump_raw_events > 0
pumpswap_raw_events > 0
```

Also require:

- `canonical_events > 0`;
- source, normalization, and end-to-end latency summaries have nonzero sample counts when their source rows exist;
- no reported latency is negative or invalid;
- pending Pump/PumpSwap rows are explainable by known metadata/lifecycle resolution and do not show an unexplained persistent or monotonically growing backlog across repeated representative windows;
- p50/p95/p99/max values are retained as measured evidence, not silently converted into a pass threshold that was never specified;
- `provider-counts.txt` contains `solana_public` for the current post-deploy FL1 Pump/PumpSwap raw and canonical activity and is consistent with the report's counts;
- any current-window `helius`, `chainstack`, or `alchemy` FL1 provenance is treated as an unexpected paid-provider path and a HOLD until explained;
- Pump and PumpSwap both show natural representative traffic; do not manufacture trades or re-enable a global PumpSwap AMM subscription merely to produce counts.

The total and window quarantine counts must be retained as measured evidence. **isolated quarantined fork conflicts** do not by themselves fail FL1.5 when the disputed identities remain excluded from trusted canonical replay, `canonical_conflict_quarantine_violations=0`, the observer remains stable, and representative raw/canonical progress continues. A **persistent or growing quarantine** across representative windows is a HOLD until the ambiguity is explained and canonical progress is shown to remain trustworthy.

A single pending row is not automatically a failure: delayed mint decimals or verified PumpSwap lifecycle mapping can be legitimate. The failure condition is unexplained persistence/growth, integrity errors, or evidence that normalization cannot catch up under real load.

## 6. Host/provider acceptance checks

Compare `observer-before.txt` with `observer-after.txt` and inspect `observer-window.log` plus the provider-consumption evidence.

Require:

- `ActiveState=active` and a healthy observer substate at both ends;
- no unexplained increase in `NRestarts`;
- no crash loop or persistent public-RPC/WSS reconnect or rate-limit churn;
- a natural public endpoint disconnect/reconnect, if one occurs, recovers without evidence loss or sequence corruption;
- the observer does not silently rotate to Helius, Chainstack, Alchemy, or another paid source when public Solana is unavailable;
- the deployed realtime topology is Pump-wide public Solana plus only the bounded verified PumpSwap target set, never the superseded global PumpSwap AMM subscription;
- any available non-secret paid-provider counters are compatible with zero broad-observer paid usage over the interval;
- paper-evidence Helius activity, if that separate service is active, is accounted for separately and is not misattributed to the observer;
- if public Solana becomes unavailable or cannot sustain representative progress, the realtime lane fails closed rather than presenting a falsely healthy ingestion state;
- CPU and RSS remain stable enough for continuous operation with meaningful headroom;
- `free -h` shows memory headroom rather than sustained exhaustion/swap pressure;
- `df -h` shows enough free space for continued database/WAL growth;
- `storage-before.txt` and `storage-after.txt` show DB/WAL growth compatible with the measured event rate and available disk headroom.

A public endpoint rate-limit or disconnect is not automatically an FL1.5 failure when it is brief, recovery is natural, provenance remains `solana_public`, and representative raw/canonical progress continues with intact integrity. It is a HOLD if the observer stalls, enters persistent reconnect churn, hides the outage behind nominal service health, or activates a paid provider fallback.

Do not turn one quiet snapshot into a resource-capacity or provider-cost claim. If CPU/RSS, DB/WAL growth, event rate, public-endpoint stability, or paid-provider counter isolation is uncertain, repeat the acceptance interval under representative natural load and retain both evidence sets. Do not manufacture load, rate limits, outages, or restarts merely to make the evidence look complete.

## 7. Duplicate/reconnect interpretation

The FL1 journal is idempotent by durable event identity. That means an attempted duplicate arriving during websocket replay can be rejected before it creates another raw/canonical row. SQLite therefore proves the absence of duplicated durable economic identities, not the number of duplicate attempts received from the network.

A replay that carries a different economic payload for an already-stored `(signature, ordinal)` is not treated as an idempotent duplicate. It is durably quarantined as conflicting evidence. The quarantined variant must not overwrite the first raw row, enter canonical normalization, or remain trusted through canonical market replay if the ambiguity arrives after canonicalization.

Use public-RPC/reconnect journal evidence to assess whether reconnect behavior is stable. If a reconnect occurred, verify the database report still has `sequence_integrity_violations=0`, `canonical_conflict_quarantine_violations=0`, no unexplained backlog jump, truthful `solana_public` provenance, and continued canonical event progress after recovery. If no reconnect occurred naturally, record that fact; do not manufacture a destructive restart or network-failure drill for this FL1.5 routine acceptance.

Any acceptance interval containing an observer restart requires an explicit explanation because it interrupts the continuous evidence window. Repeated restarts to hide public-endpoint instability or provider usage are prohibited and cannot satisfy FL1.5.

## 8. FL1.5 hold / exit rule

**Do not advance to FL2** if any of the following is true:

- the acceptance subcommand is not available from the exact verified immutable `shreks-observe` release payload;
- the database is not the production observer database;
- `sequence_integrity_violations` is nonzero;
- `canonical_conflict_quarantine_violations` is nonzero;
- the reporter rejects a timing invariant or schema invariant;
- Pump or PumpSwap representative traffic is absent from the chosen window;
- canonical progress stalls or pending backlog is persistently unexplained/growing;
- quarantine is persistent or growing across representative windows without a bounded explanation, or fork ambiguity prevents representative canonical progress;
- current-window provider provenance is missing, contradictory, inconsistent with reported FL1 activity, or differs from the required `solana_public` broad-capture provenance;
- the observer activates or appears to activate a paid provider fallback for broad FL1 capture or lifecycle verification;
- the deployed realtime subscription includes the global PumpSwap AMM program rather than the bounded verified pool set;
- public Solana is persistently unavailable, rate-limited, or reconnecting such that representative raw/canonical progress is not sustained;
- available paid-provider evidence shows unexplained counter growth attributable to the broad observer lane;
- the observer remains nominally healthy while realtime raw/canonical progress has stopped;
- the observer crashes/restarts unexpectedly or public-RPC/reconnect behavior is unstable;
- CPU/RSS, memory, disk, or DB/WAL growth leaves inadequate production headroom;
- the evidence interval, release SHA, provider-provenance evidence, zero-paid-provider evidence, or host-only records are missing;
- any command or code path introduces trading, signing, submission, or LIVE authority.

FL1.5 may be marked production-accepted only after the real dedicated host has produced and retained one or more representative evidence sets satisfying the database-backed, host-only, public-Solana provenance, and zero-paid-provider checks above. CI, fixtures, localhost tests, and synthetic traffic alone cannot satisfy this exit rule.

**LIVE TRADING: DISABLED**
