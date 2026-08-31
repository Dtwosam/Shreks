use std::time::Duration;

use async_trait::async_trait;
use shreks_core::ProviderId;
use tokio::{sync::watch, time::sleep};

use crate::{
    bounded_pump_realtime::{
        BoundedPumpRealtimeLogStream, BoundedPumpRealtimeLogStreamConfig,
    },
    pump_realtime::{PumpRealtimeNotification, PumpRealtimeSignalSource},
    ProviderError, ProviderErrorKind,
};

const DEFAULT_MAX_PUBLIC_INVALID_RESPONSE_RECONNECTS: u32 = 5;
const DEFAULT_PUBLIC_INVALID_RESPONSE_RECONNECT_DELAY: Duration = Duration::from_secs(1);

/// Ordered bounded Pump realtime sources. The currently working source is
/// sticky; retryable provider exhaustion rotates to the next configured
/// provider. Each source owns a clone of the same target watch receiver, so a
/// provider switch reconstructs subscriptions from the latest verified pool
/// set rather than from an earlier snapshot.
pub struct BoundedPumpRealtimeFailoverStream {
    configs: Vec<BoundedPumpRealtimeLogStreamConfig>,
    targets: watch::Receiver<Vec<String>>,
    streams: Vec<BoundedPumpRealtimeLogStream>,
    active_index: usize,
    public_invalid_response_reconnects: u32,
    max_public_invalid_response_reconnects: u32,
    public_invalid_response_reconnect_delay: Duration,
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
            .iter()
            .cloned()
            .map(|config| BoundedPumpRealtimeLogStream::new(config, targets.clone()))
            .collect::<Result<Vec<_>, _>>()?;

        Ok(Self {
            configs,
            targets,
            streams,
            active_index: 0,
            public_invalid_response_reconnects: 0,
            max_public_invalid_response_reconnects:
                DEFAULT_MAX_PUBLIC_INVALID_RESPONSE_RECONNECTS,
            public_invalid_response_reconnect_delay:
                DEFAULT_PUBLIC_INVALID_RESPONSE_RECONNECT_DELAY,
        })
    }

    /// Override the bounded public-Solana malformed-response reconnect policy.
    /// Production uses the conservative defaults; this hook also makes the
    /// bound deterministic in local regression tests.
    pub fn with_public_invalid_response_reconnect_policy(
        mut self,
        max_reconnects: u32,
        delay: Duration,
    ) -> Self {
        self.max_public_invalid_response_reconnects = max_reconnects.max(1);
        self.public_invalid_response_reconnect_delay = delay;
        self
    }

    pub async fn next_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError> {
        loop {
            match self.next_failover_round().await {
                Ok(notification) => {
                    self.public_invalid_response_reconnects = 0;
                    return Ok(notification);
                }
                Err(error) if is_public_invalid_response(&error) => {
                    self.public_invalid_response_reconnects =
                        self.public_invalid_response_reconnects.saturating_add(1);
                    if self.public_invalid_response_reconnects
                        >= self.max_public_invalid_response_reconnects
                    {
                        return Err(error);
                    }

                    // The raw stream intentionally treats malformed provider
                    // responses as terminal. Rebuild only the same public lane
                    // from the latest verified targets, then retry after a
                    // bounded delay. This adds no paid-provider fallback and
                    // persistent corruption still fails closed at the bound.
                    self.rebuild_stream(self.active_index)?;
                    sleep(self.public_invalid_response_reconnect_delay).await;
                }
                Err(error) => {
                    self.public_invalid_response_reconnects = 0;
                    return Err(error);
                }
            }
        }
    }

    async fn next_failover_round(
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
                    self.active_index = index;
                    attempts.push(format!("{}:{:?}", error.provider, error.kind));
                    return Err(with_failover_attempt_trace(error, &attempts));
                }
            }
        }

        let error = last_retryable_error
            .expect("non-empty bounded realtime provider set produced a retryable error");
        Err(with_failover_attempt_trace(error, &attempts))
    }

    fn rebuild_stream(&mut self, index: usize) -> Result<(), ProviderError> {
        self.streams[index] = BoundedPumpRealtimeLogStream::new(
            self.configs[index].clone(),
            self.targets.clone(),
        )?;
        Ok(())
    }
}

#[async_trait]
impl PumpRealtimeSignalSource for BoundedPumpRealtimeFailoverStream {
    async fn next_pump_realtime_notification(
        &mut self,
    ) -> Result<PumpRealtimeNotification, ProviderError> {
        self.next_realtime_notification().await
    }
}

fn is_public_invalid_response(error: &ProviderError) -> bool {
    error.provider == ProviderId::SolanaPublic && error.kind == ProviderErrorKind::InvalidResponse
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
