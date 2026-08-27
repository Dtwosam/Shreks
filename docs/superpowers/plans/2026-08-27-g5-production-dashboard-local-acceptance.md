# G5 production dashboard local acceptance

Date: 2026-08-27

## Scope

This record captures physical VPS acceptance for the private operator dashboard's local, authenticated, read-side deployment boundary on the sealed production release `cb72f76b901bd170b565a53a7269a20247c27908`.

This acceptance does not claim remote browser/phone access, TLS/private-overlay exposure, G6 alert delivery, or G7 operator control propagation. No HALT or EMERGENCY KILL command was exercised during this acceptance.

**LIVE TRADING: DISABLED.**

## Host evidence

The sealed dashboard unit was installed from the exact deployed release source and its checksum verified before installation.

Persistent G7 operator risk state already existed at `/var/lib/shreks/risk/operator-control.json` with:

- mode `0600`;
- owner `shreks`;
- group `shreks`;
- size `252` bytes.

Its SHA-256 before dashboard exercise was:

`4e4b02f6756d420a3b98ef6c0d6d1463889199745a789e7a29b4f5a05fd01c15`

A new dashboard password was generated only on the host and stored at `/etc/shreks/dashboard-password` with:

- owner `root`;
- group `shreks`;
- mode `0640`;
- size `65` bytes.

No password value was printed or committed.

Dashboard runtime configuration was set to:

- loopback bind `127.0.0.1`;
- port `8787`;
- username `shreks-operator`;
- password file `/etc/shreks/dashboard-password`;
- telemetry path `/var/lib/shreks/telemetry/current.json`;
- maximum recent trades `100`.

## Local service acceptance

Core runtime process identities before dashboard startup:

- observer PID `23800`;
- paper-evidence PID `23277`;
- paper-campaign PID `23733`.

`shreks-dashboard.service` was enabled and started successfully and reported `active`.

Socket inspection proved the service was listening only on:

`127.0.0.1:8787`

No wildcard/public listener on `0.0.0.0`, `*`, or `[::]` was accepted.

Authentication behavior:

- unauthenticated `GET /` -> HTTP `401`;
- authenticated `GET /` -> HTTP `200`;
- authenticated `GET /api/v1/snapshot` -> HTTP `200`;
- rendered page contained `LIVE TRADING: DISABLED`.

## Read-side immutability

The operator risk-control file SHA-256 after authenticated dashboard reads remained exactly:

`4e4b02f6756d420a3b98ef6c0d6d1463889199745a789e7a29b4f5a05fd01c15`

Therefore the authenticated read-side acceptance did not mutate the authoritative operator risk-control state.

## Restart isolation

`shreks-dashboard.service` was restarted directly.

Core process identities after the dashboard restart remained:

- observer PID `23800`;
- paper-evidence PID `23277`;
- paper-campaign PID `23733`.

The core PAPER target lifecycle timestamp was also required to remain unchanged by the acceptance script.

Final active state:

- `shreks-dashboard.service=active`;
- `shreks-observe.service=active`;
- `shreks-paper-evidence.service=active`;
- `shreks-paper-campaign.service=active`;
- `shreks.target=active`;
- `shreks-telemetry.timer=active`.

Host conclusion:

`PRIVATE DASHBOARD LOCAL ACCEPTANCE PASSED`

## Remaining G5 physical boundary

Local dashboard deployment is proven. Remote operator access remains intentionally unproven and must not be implemented by exposing port `8787` directly to the public internet. Any future remote/browser access must preserve the loopback listener and use a same-host TLS reverse proxy or authenticated private overlay/tunnel as already required by the sealed design.

No claim is made here that browser HALT/KILL controls have been physically exercised. That belongs to the separate G7 host-control acceptance boundary.

**LIVE TRADING: DISABLED.**
