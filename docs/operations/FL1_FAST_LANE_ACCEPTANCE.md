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

The resolved release SHA and the manifest `source_sha` must match exactly. The release manifest must include `target/release/shreks-fast-lane-acceptance`; a locally compiled, copied, edited, or unmanifested reporter is not valid production evidence.

Use the authoritative persistent observer database:

```text
/var/lib/shreks/shreks.db
```

Do not copy provider credentials, environment secrets, wallet material, dashboard credentials, Telegram tokens, or any signing material into the evidence directory.

## 2. Evidence boundary

### Database-backed evidence

`shreks-fast-lane-acceptance` opens SQLite with `SQLITE_OPEN_READ_ONLY` and reports only evidence already present in the durable FL1 tables plus filesystem size metadata:

- raw Pump event count for the selected window;
- raw PumpSwap event count for the selected window;
- canonical FastEvent count for the selected window;
- current pending Pump backlog;
- current pending PumpSwap backlog;
- canonical sequence-integrity violations;
- chain occurrence -> source observation latency;
- source observation -> canonical acceptance latency;
- chain occurrence -> canonical acceptance latency;
- database and WAL bytes at report time.

The reporter does not perform provider calls and cannot measure an attempted duplicate delivery that was rejected before it became a second durable row. Do not invent a duplicate-attempt count from SQLite.

### Host-only evidence

Capture these separately over the same physical-host interval:

- observer service state and `NRestarts`;
- observer PID, CPU, and RSS;
- host memory and filesystem headroom;
- database/WAL size before and after the interval for DB/WAL growth;
- observer provider/reconnect journal lines, including any disconnect/reconnect instability;
- exact release SHA and exact interval timestamps.

Provider/reconnect logs are the source for reconnect behavior and any visible attempted duplicate/replay overlap. If the logs do not expose a trustworthy attempted duplicate count, record that metric as unavailable rather than fabricating it.

## 3. Start one representative interval

Choose a window long enough to observe both Pump bonding-curve and PumpSwap traffic. Zero traffic from either lane does not prove that lane on the production host; extend the window instead of treating silence as success.

Capture the starting wall clock and database/WAL sizes:

```bash
DB=/var/lib/shreks/shreks.db
START_MS="$(date +%s%3N)"
START_ISO="$(date --iso-8601=seconds)"
printf '%s\n' "$START_MS" > "$EVIDENCE_DIR/window-start-ms.txt"
printf '%s\n' "$START_ISO" > "$EVIDENCE_DIR/window-start-iso.txt"
stat -c '%n %s' "$DB" "$DB-wal" 2>&1 | tee "$EVIDENCE_DIR/storage-before.txt"
systemctl show shreks-observe.service -p ActiveState -p SubState -p NRestarts -p MainPID -p ExecMainStatus | tee "$EVIDENCE_DIR/observer-before.txt"
```

Let the normal production observer run without intervention for the chosen representative interval. Do not use this acceptance procedure to induce a restart or mutate service state.

## 4. End the interval and run the read-only reporter

Capture the end timestamp and host state:

```bash
END_MS="$(date +%s%3N)"
END_ISO="$(date --iso-8601=seconds)"
printf '%s\n' "$END_MS" > "$EVIDENCE_DIR/window-end-ms.txt"
printf '%s\n' "$END_ISO" > "$EVIDENCE_DIR/window-end-iso.txt"
stat -c '%n %s' "$DB" "$DB-wal" 2>&1 | tee "$EVIDENCE_DIR/storage-after.txt"
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

Run the reporter as the unprivileged runtime identity. The operator shell opens the private evidence file, while the reporter itself retains only the `shreks` user's database access:

```bash
sudo -u shreks /opt/shreks/current/target/release/shreks-fast-lane-acceptance \
  /var/lib/shreks/shreks.db \
  "$START_MS" \
  "$END_MS" \
  > "$EVIDENCE_DIR/fast-lane-report.txt"
```

The command must exit `0`. A nonzero exit means missing/incompatible schema, invalid timing, unreadable storage evidence, or another fail-closed condition; investigate it rather than overriding it.

## 5. Database-backed acceptance checks

Read the captured report. The minimum integrity requirements are:

```text
sequence_integrity_violations=0
pump_raw_events > 0
pumpswap_raw_events > 0
```

Also require:

- `canonical_events > 0`;
- source, normalization, and end-to-end latency summaries have nonzero sample counts when their source rows exist;
- no reported latency is negative or invalid;
- pending Pump/PumpSwap rows are explainable by known metadata/lifecycle resolution and do not show an unexplained persistent or monotonically growing backlog across repeated representative windows;
- p50/p95/p99/max values are retained as measured evidence, not silently converted into a pass threshold that was never specified.

A single pending row is not automatically a failure: delayed mint decimals or verified PumpSwap lifecycle mapping can be legitimate. The failure condition is unexplained persistence/growth, integrity errors, or evidence that normalization cannot catch up under real load.

## 6. Host-only acceptance checks

Compare `observer-before.txt` with `observer-after.txt` and inspect `observer-window.log`.

Require:

- `ActiveState=active` and a healthy observer substate at both ends;
- no unexplained increase in `NRestarts`;
- no crash loop or persistent provider/reconnect churn;
- reconnects, if they occur naturally, recover without evidence loss or sequence corruption;
- CPU and RSS remain stable enough for continuous operation with meaningful headroom;
- `free -h` shows memory headroom rather than sustained exhaustion/swap pressure;
- `df -h` shows enough free space for continued database/WAL growth;
- `storage-before.txt` and `storage-after.txt` show DB/WAL growth compatible with the measured event rate and available disk headroom.

Do not turn one quiet snapshot into a resource-capacity claim. If CPU/RSS or DB/WAL growth is uncertain, repeat the acceptance interval under representative load and retain both evidence sets.

## 7. Duplicate/reconnect interpretation

The FL1 journal is idempotent by durable event identity. That means an attempted duplicate arriving during websocket replay can be rejected before it creates another raw/canonical row. SQLite therefore proves the absence of duplicated durable economic identities, not the number of duplicate attempts received from the network.

Use provider/reconnect journal evidence to assess whether reconnect behavior is stable. If a reconnect occurred, verify the database report still has `sequence_integrity_violations=0`, no unexplained backlog jump, and continued canonical event progress after recovery. If no reconnect occurred naturally, record that fact; do not manufacture a destructive restart drill for this FL1.5 routine acceptance.

## 8. FL1.5 hold / exit rule

**Do not advance to FL2** if any of the following is true:

- the reporter is not part of the exact verified immutable release;
- the database is not the production observer database;
- `sequence_integrity_violations` is nonzero;
- the reporter rejects a timing invariant or schema invariant;
- Pump or PumpSwap representative traffic is absent from the chosen window;
- canonical progress stalls or pending backlog is persistently unexplained/growing;
- the observer crashes/restarts unexpectedly or provider/reconnect behavior is unstable;
- CPU/RSS, memory, disk, or DB/WAL growth leaves inadequate production headroom;
- the evidence interval, release SHA, or host-only records are missing;
- any command or code path introduces trading, signing, submission, or LIVE authority.

FL1.5 may be marked production-accepted only after the real dedicated host has produced and retained one or more representative evidence sets satisfying both the database-backed and host-only checks above. CI, fixtures, localhost tests, and synthetic traffic alone cannot satisfy this exit rule.

**LIVE TRADING: DISABLED**
