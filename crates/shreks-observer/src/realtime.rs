use std::time::{SystemTime, UNIX_EPOCH};

use shreks_core::ProviderId;
use shreks_providers::{
    pump::PumpLifecycleSignal,
    pump_realtime::PumpRealtimeNotification,
};
use shreks_storage::{PumpTradeEvidenceWrite, ShreksDb, StorageError};
use tokio::sync::mpsc;

use crate::{Observer, ObserverError};

impl Observer {
    /// Drain confirmed Pump realtime envelopes into durable observe-only storage.
    ///
    /// This writer intentionally performs no provider requests and owns no
    /// strategy, signing, or execution authority. Lifecycle evidence enters the
    /// existing restart-safe inboxes immediately, while trade economics are
    /// stored immutably by `(signature, ordinal)` for later normalization.
    pub async fn run_pump_realtime_writer(
        db: ShreksDb,
        mut receiver: mpsc::Receiver<PumpRealtimeNotification>,
    ) -> Result<usize, ObserverError> {
        let mut trade_rows_inserted = 0_usize;

        while let Some(notification) = receiver.recv().await {
            validate_realtime_identity(&notification)?;
            let observed_at_unix_ms = realtime_observed_at_unix_ms()?;

            if let Some(lifecycle) = &notification.lifecycle {
                match lifecycle {
                    PumpLifecycleSignal::Creation(signal) => db.record_pump_launch_signal(
                        &signal.signature,
                        signal.slot,
                        observed_at_unix_ms,
                    )?,
                    PumpLifecycleSignal::Migration(signal) => db.record_pump_migration_signal(
                        &signal.signature,
                        signal.slot,
                        observed_at_unix_ms,
                    )?,
                }
            }

            for (index, trade) in notification.trades.iter().enumerate() {
                let ordinal = u32::try_from(index).map_err(|_| {
                    ObserverError::Storage(StorageError::InvalidData(
                        "Pump realtime notification contains more than u32::MAX trade events"
                            .to_owned(),
                    ))
                })?;

                let write = PumpTradeEvidenceWrite {
                    provider: ProviderId::Helius,
                    signature: notification.signature.clone(),
                    ordinal,
                    slot: notification.slot,
                    observed_at_unix_ms,
                    mint: trade.mint.clone(),
                    quote_mint: trade.quote_mint.clone(),
                    user: trade.user.clone(),
                    is_buy: trade.is_buy,
                    token_amount_raw: trade.token_amount_raw,
                    sol_amount_raw: trade.sol_amount_raw,
                    quote_amount_raw: trade.quote_amount_raw,
                    timestamp_unix_seconds: trade.timestamp_unix_seconds,
                    virtual_sol_reserves_raw: trade.virtual_sol_reserves_raw,
                    virtual_token_reserves_raw: trade.virtual_token_reserves_raw,
                    real_sol_reserves_raw: trade.real_sol_reserves_raw,
                    real_token_reserves_raw: trade.real_token_reserves_raw,
                    virtual_quote_reserves_raw: trade.virtual_quote_reserves_raw,
                    real_quote_reserves_raw: trade.real_quote_reserves_raw,
                    ix_name: trade.ix_name.clone(),
                };

                if db.record_pump_trade_evidence(&write)? {
                    trade_rows_inserted = trade_rows_inserted.checked_add(1).ok_or_else(|| {
                        ObserverError::Storage(StorageError::InvalidData(
                            "Pump realtime inserted-row count overflowed usize".to_owned(),
                        ))
                    })?;
                }
            }
        }

        Ok(trade_rows_inserted)
    }
}

fn validate_realtime_identity(notification: &PumpRealtimeNotification) -> Result<(), ObserverError> {
    if notification.signature.trim().is_empty() {
        return Err(ObserverError::Storage(StorageError::InvalidData(
            "Pump realtime notification signature must not be empty".to_owned(),
        )));
    }

    if let Some(lifecycle) = &notification.lifecycle {
        let (signature, slot) = match lifecycle {
            PumpLifecycleSignal::Creation(signal) => (&signal.signature, signal.slot),
            PumpLifecycleSignal::Migration(signal) => (&signal.signature, signal.slot),
        };
        if signature != &notification.signature || slot != notification.slot {
            return Err(ObserverError::Storage(StorageError::InvalidData(
                "Pump realtime lifecycle identity does not match envelope signature/slot"
                    .to_owned(),
            )));
        }
    }

    Ok(())
}

fn realtime_observed_at_unix_ms() -> Result<i64, ObserverError> {
    let elapsed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(ObserverError::Clock)?;
    i64::try_from(elapsed.as_millis()).map_err(|_| ObserverError::ClockOverflow)
}
