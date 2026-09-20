
    for required in (
        'DEPLOY_RC=$?',
        "release manager failed; collecting read-only host diagnostics",
        "readlink -f /opt/shreks/current",
        "candidate_release_present=",
        "systemctl is-active shreks.target",
        "systemctl show shreks-observe.service",
        "-p ActiveState",
        "-p SubState",
        "-p NRestarts",
        "-p MainPID",
        "-p ExecMainStatus",
        'exit "$DEPLOY_RC"',
    ):
        assert required in workflow

    assert "sudo systemctl" not in workflow
    assert "journalctl" not in workflow


def test_deploy_workflow_pre_stages_release_bound_protected_discovery_control() -> None:
    workflow = _read(_DEPLOY_WORKFLOW)

    for required in (
        'DISCOVERY_REQUEST_ID="gha-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"',
        'REMOTE_DISCOVERY_REQUEST="/var/tmp/shreks-fl9-v2-discovery.${DISCOVERY_REQUEST_ID}.request"',
        'REMOTE_DISCOVERY_RESULT_DIR="/dev/shm/shreks-fl9-v2-discovery.${DISCOVERY_REQUEST_ID}.result.d"',
        "shreks.fl9_v2_discovery_control_request",
        '"created_at_unix_ms": time.time_ns() // 1_000_000',
        'install -d -m 0733 "$RESULT_DIR"',
        "O_NOFOLLOW",
        'sudo /usr/local/sbin/shreks-release-manager install',
        'discovery_request_id: gha-${{ github.run_id }}-${{ github.run_attempt }}',
    ):
        assert required in workflow

    for forbidden in (
        "steps.deploy_host.outputs.discovery_request_id",
        "needs.deploy.outputs.discovery_request_id",
        'printf \'discovery_request_id=%s\\n\' "$DISCOVERY_REQUEST_ID" >> "$GITHUB_OUTPUT"',
    ):
        assert forbidden not in workflow

    stage_index = workflow.index("shreks.fl9_v2_discovery_control_request")
    manager_index = workflow.index(
        "sudo /usr/local/sbin/shreks-release-manager install",
        stage_index,
    )
    assert stage_index < manager_index

    for forbidden in (
        "sudo chmod /var/lib/shreks",
        "sudo chown /var/lib/shreks",
        "setfacl",
        "cat /var/lib/shreks",
        "cat /etc/shreks",
    ):
        assert forbidden not in workflow


def test_deploy_reusable_verifier_binding_does_not_depend_on_job_output_transport() -> None:
    workflow = _read(_DEPLOY_WORKFLOW)

    assert 'DISCOVERY_REQUEST_ID="gha-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"' in workflow
    assert 'discovery_request_id: gha-${{ github.run_id }}-${{ github.run_attempt }}' in workflow
    assert "steps.deploy_host.outputs.discovery_request_id" not in workflow
    assert "needs.deploy.outputs.discovery_request_id" not in workflow
    assert 'printf \'discovery_request_id=%s\\n\' "$DISCOVERY_REQUEST_ID" >> "$GITHUB_OUTPUT"' not in workflow


def test_production_verifier_can_reuse_exact_pre_staged_discovery_exchange() -> None:
    workflow = _read(_VERIFY_PRODUCTION_WORKFLOW)

    for required in (
        "discovery_request_id:",
        "PRESTAGED_DISCOVERY_REQUEST_ID",
        'DISCOVERY_PRESTAGED=1',
        'DISCOVERY_PRESTAGED=0',
        'test -d "$DISCOVERY_RESULT_DIR"',
        'test "$(stat -c %u "$DISCOVERY_RESULT_DIR")" = "$(id -u)"',
        'test "$(stat -c %a "$DISCOVERY_RESULT_DIR")" = 733',
    ):
        assert required in workflow

    assert 'if [[ -n "$PRESTAGED_DISCOVERY_REQUEST_ID" ]]' in workflow

def test_production_verifier_is_manual_and_reusable_read_only_transport_boundary():
    workflow = _read(_VERIFY_PRODUCTION_WORKFLOW)

    assert "workflow_dispatch:" in workflow
    assert "workflow_call:" in workflow
    assert "expected_release_sha:" in workflow
    assert "journal_minutes:" in workflow
    assert 'default: "30"' in workflow
    assert "environment: production-paper" in workflow
    assert re.search(r"permissions:\s*\n\s+contents: read", workflow)
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", workflow)) == _DEPLOY_SECRET_NAMES

    for required in (
