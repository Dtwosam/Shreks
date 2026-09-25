use std::{
    fs::{self, OpenOptions},
    io::{self, Write},
    os::unix::fs::OpenOptionsExt,
    path::Path,
    process,
};

use serde_json::json;

pub const PAPER_EVIDENCE_RUNTIME_STATUS_PATH: &str =
    "/var/lib/shreks/telemetry/paper-evidence-status.json";
pub const PAPER_EVIDENCE_RUNTIME_STATUS_SCHEMA_NAME: &str =
    "shreks.paper_evidence_runtime_status";
pub const PAPER_EVIDENCE_RUNTIME_STATUS_SCHEMA_VERSION: u64 = 1;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PaperEvidenceRuntimeStatus {
    process_started_at_unix_ms: i64,
    generated_at_unix_ms: i64,
    completed_cycle_count: u64,
    cycle_as_of_unix_ms: Option<i64>,
    evidence_cycle_interval_ms: i64,
    mint_state_max_age_ms: i64,
    mint_state_refresh_age_ms: i64,
    provider_failures_last_cycle: u64,
    helius_requests_attempted: u64,
    helius_requests_limit: u64,
    helius_requests_remaining: u64,
    helius_budget_exhausted: bool,
    candidates_selected_last_cycle: u64,
    mint_states_stored_last_cycle: u64,
}

impl PaperEvidenceRuntimeStatus {
    pub fn started(
        process_started_at_unix_ms: i64,
        evidence_cycle_interval_ms: i64,
        mint_state_max_age_ms: i64,
        mint_state_refresh_age_ms: i64,
        helius_requests_limit: u64,
    ) -> io::Result<Self> {
        require_non_negative_i64(
            process_started_at_unix_ms,
            "process_started_at_unix_ms",
        )?;
        if evidence_cycle_interval_ms <= 0 {
            return Err(invalid_input(
                "evidence_cycle_interval_ms must be positive",
            ));
        }
        require_non_negative_i64(mint_state_max_age_ms, "mint_state_max_age_ms")?;
        require_non_negative_i64(
            mint_state_refresh_age_ms,
            "mint_state_refresh_age_ms",
        )?;
        if mint_state_refresh_age_ms > mint_state_max_age_ms {
            return Err(invalid_input(
                "mint_state_refresh_age_ms cannot exceed mint_state_max_age_ms",
            ));
        }
        if helius_requests_limit == 0 {
            return Err(invalid_input("helius_requests_limit must be positive"));
        }

        Ok(Self {
            process_started_at_unix_ms,
            generated_at_unix_ms: process_started_at_unix_ms,
            completed_cycle_count: 0,
            cycle_as_of_unix_ms: None,
            evidence_cycle_interval_ms,
            mint_state_max_age_ms,
            mint_state_refresh_age_ms,
            provider_failures_last_cycle: 0,
            helius_requests_attempted: 0,
            helius_requests_limit,
            helius_requests_remaining: helius_requests_limit,
            helius_budget_exhausted: false,
            candidates_selected_last_cycle: 0,
            mint_states_stored_last_cycle: 0,
        })
    }

    #[allow(clippy::too_many_arguments)]
    pub fn completed_cycle(
        &self,
        generated_at_unix_ms: i64,
        completed_cycle_count: u64,
        cycle_as_of_unix_ms: i64,
        provider_failures_last_cycle: usize,
        helius_requests_attempted: u64,
        helius_requests_limit: u64,
        helius_requests_remaining: u64,
        helius_budget_exhausted: bool,
        candidates_selected_last_cycle: usize,
        mint_states_stored_last_cycle: usize,
    ) -> io::Result<Self> {
        require_non_negative_i64(generated_at_unix_ms, "generated_at_unix_ms")?;
        require_non_negative_i64(cycle_as_of_unix_ms, "cycle_as_of_unix_ms")?;
        if generated_at_unix_ms < self.process_started_at_unix_ms {
            return Err(invalid_input(
                "generated_at_unix_ms cannot precede process start",
            ));
        }
        if cycle_as_of_unix_ms < self.process_started_at_unix_ms
            || cycle_as_of_unix_ms > generated_at_unix_ms
        {
            return Err(invalid_input(
                "cycle_as_of_unix_ms must be between process start and generation time",
            ));
        }
        if completed_cycle_count == 0 {
            return Err(invalid_input("completed_cycle_count must be positive"));
        }
        if completed_cycle_count < self.completed_cycle_count {
            return Err(invalid_input(
                "completed_cycle_count cannot move backwards",
            ));
        }
        if helius_requests_limit != self.helius_requests_limit {
            return Err(invalid_input(
                "helius_requests_limit cannot change within one process",
            ));
        }
        if helius_requests_attempted > helius_requests_limit {
            return Err(invalid_input(
                "helius_requests_attempted cannot exceed limit",
            ));
        }
        if helius_requests_remaining
            != helius_requests_limit.saturating_sub(helius_requests_attempted)
        {
            return Err(invalid_input(
                "Helius request budget remaining count is inconsistent",
            ));
        }
        if helius_budget_exhausted != (helius_requests_attempted >= helius_requests_limit) {
            return Err(invalid_input(
                "Helius request budget exhausted flag is inconsistent",
            ));
        }

        Ok(Self {
            process_started_at_unix_ms: self.process_started_at_unix_ms,
            generated_at_unix_ms,
            completed_cycle_count,
            cycle_as_of_unix_ms: Some(cycle_as_of_unix_ms),
            evidence_cycle_interval_ms: self.evidence_cycle_interval_ms,
            mint_state_max_age_ms: self.mint_state_max_age_ms,
            mint_state_refresh_age_ms: self.mint_state_refresh_age_ms,
            provider_failures_last_cycle: u64::try_from(provider_failures_last_cycle)
                .map_err(|_| invalid_input("provider failure count exceeds u64"))?,
            helius_requests_attempted,
            helius_requests_limit,
            helius_requests_remaining,
            helius_budget_exhausted,
            candidates_selected_last_cycle: u64::try_from(candidates_selected_last_cycle)
                .map_err(|_| invalid_input("candidate count exceeds u64"))?,
            mint_states_stored_last_cycle: u64::try_from(mint_states_stored_last_cycle)
                .map_err(|_| invalid_input("mint-state stored count exceeds u64"))?,
        })
    }

    fn document(&self) -> serde_json::Value {
        json!({
            "schema_name": PAPER_EVIDENCE_RUNTIME_STATUS_SCHEMA_NAME,
            "schema_version": PAPER_EVIDENCE_RUNTIME_STATUS_SCHEMA_VERSION,
            "state": if self.completed_cycle_count == 0 {
                "STARTED"
            } else {
                "CYCLE_COMPLETE"
            },
            "process_started_at_unix_ms": self.process_started_at_unix_ms,
            "generated_at_unix_ms": self.generated_at_unix_ms,
            "completed_cycle_count": self.completed_cycle_count,
            "cycle_as_of_unix_ms": self.cycle_as_of_unix_ms,
            "evidence_cycle_interval_ms": self.evidence_cycle_interval_ms,
            "mint_state_max_age_ms": self.mint_state_max_age_ms,
            "mint_state_refresh_age_ms": self.mint_state_refresh_age_ms,
            "provider_failures_last_cycle": self.provider_failures_last_cycle,
            "helius_requests_attempted": self.helius_requests_attempted,
            "helius_requests_limit": self.helius_requests_limit,
            "helius_requests_remaining": self.helius_requests_remaining,
            "helius_budget_exhausted": self.helius_budget_exhausted,
            "candidates_selected_last_cycle": self.candidates_selected_last_cycle,
            "mint_states_stored_last_cycle": self.mint_states_stored_last_cycle,
            "observation_authority": "DERIVED_OPERATIONAL",
            "paper_promotion_authority": "BLOCKED",
            "live_authority": "DISABLED",
        })
    }
}

pub fn write_paper_evidence_runtime_status(
    path: &Path,
    status: &PaperEvidenceRuntimeStatus,
) -> io::Result<()> {
    let parent = path
        .parent()
        .filter(|value| !value.as_os_str().is_empty())
        .ok_or_else(|| invalid_input("runtime status path must have a parent"))?;
    if !parent.is_dir() {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            "runtime status parent directory is unavailable",
        ));
    }

    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| invalid_input("runtime status path must name a file"))?;
    let temporary = parent.join(format!(
        ".{file_name}.{}.{}.tmp",
        process::id(),
        status.generated_at_unix_ms,
    ));

    let mut payload = serde_json::to_vec(&status.document())
        .map_err(|_| io::Error::other("runtime status serialization failed"))?;
    payload.push(b'\n');

    let result = (|| -> io::Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)?;
        file.write_all(&payload)?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, path)?;
        fs::File::open(parent)?.sync_all()?;
        Ok(())
    })();

    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn require_non_negative_i64(value: i64, name: &str) -> io::Result<()> {
    if value < 0 {
        return Err(invalid_input(format!("{name} must be non-negative")));
    }
    Ok(())
}

fn invalid_input(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message.into())
}
