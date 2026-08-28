# G2 Auto-Release `workflow_run` Security Note

GitHub documents that a workflow started by `workflow_run` can receive write tokens even when the upstream workflow is less privileged. The automatic Shreks release path therefore treats event provenance as part of the release authorization boundary, not merely as scheduling metadata.

The automatic release job is eligible only when all of these are true:

- the triggering workflow is exactly `CI`;
- the triggering workflow ran on `main`;
- the triggering workflow event is exactly `push`;
- the triggering workflow conclusion is exactly `success`;
- the triggering commit message begins with `seal:`;
- the release checks out exactly `workflow_run.head_sha`;
- the checked-out commit independently passes the existing `seal` subject check;
- repository safety, Rust, Python, release bundle build/verification, and duplicate-tag rejection all rerun before release creation.

The release workflow receives `contents: write` only for immutable GitHub Release/tag creation. It has no deployment environment, deployment secrets, SSH/SCP, VPS state access, provider credentials, wallet/signing authority, transaction-submission authority, or LIVE authority.

Production deployment remains manual-only in `.github/workflows/deploy.yml` and remains protected by the `production-paper` environment.

**LIVE TRADING: DISABLED. FL2 remains blocked pending real-host FL1.5 acceptance.**
