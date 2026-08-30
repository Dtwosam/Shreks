use shreks_core::ProviderId;
use tokio::sync::watch;

use crate::{
    bounded_pump_realtime::{
        BoundedPumpRealtimeLogStream, BoundedPumpRealtimeLogStreamConfig,
    },
    pump_realtime::PumpRealtimeNotification,
    ProviderError, ProviderErrorKind,
};

/// Ordered bounded Pump realtime sources. The currently working source is
/// sticky; retryable provider exhaustion rotates to the next configured
/// provider. Each source owns a clone of the same target watch receiver, so a
/// provider switch reconstructs subscriptions from the latest verified pool
/// set rather than from an earlier snapshot.
pub struct BoundedPumpRealtimeFailoverStream {
    streams: Vec<BoundedPumpRealtimeLogStream>,
    active_index: usize,
}

impl BoundedPumpRealtimeFailoverStream {
    pub fn new(
        configs: Vec<BoundedPumpRealtimeLogStreamConfig>,
        targets: watch::Receiver<Vec<String>>,
    ) -> Result<Self, ProviderError> {
        if configs.is_empty() {
            return Err(ProviderError::new(
                ProviderId::Helius,
                ProviderErrorKind::InvalidRequest,
                "bounded Pump realtime failover requires at least one provider",
            ));
        }

        let streams = configs
            .into_iter()
            .map(|config| BoundedPumpRealtimeLogStream::new(config, targets.clone()))
            .collect::<Result<Vec<_>, _>>()?;

        Ok(Self {
            streams,
            active_index: 0,
        })
    }

    pub async fn next_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError> {
        let stream_count = self.streams.len();
        let start = self.active_index;
        let mut last_retryable_error = None;
        let mut attempts = Vec::with_capacity(stream_count);

        for offset in 0..stream_count {
            let index = (start + offset) % stream_count;
            match self.streams[index].next_realtime_notification().await {
                Ok(notification) => {
                    self.active_index = index;
                    return Ok(notification);
                }
                Err(error) if error.is_retryable() => {
                    attempts.push(format!("{}:{:?}", error.provider, error.kind));
                    self.active_index = (index + 1) % stream_count;
                    last_retryable_error = Some(error);
                }
                Err(error) => {
                    attempts.push(format!("{}:{:?}", error.provider, error.kind));
                    return Err(with_failover_attempt_trace(error, &attempts));
                }
            }
        }

        let error = last_retryable_error
            .expect("non-empty bounded realtime provider set produced a retryable error");
        Err(with_failover_attempt_trace(error, &attempts))
    }
}

fn with_failover_attempt_trace(mut error: ProviderError, attempts: &[String]) -> ProviderError {
    if !attempts.is_empty() {
        error.message = format!(
            "{}; failover_attempts={}",
            error.message,
            attempts.join(",")
        );
    }
    error
}
