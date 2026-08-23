use async_trait::async_trait;
use shreks_core::ProviderId;
use shreks_observer::forward_pump_signals;
use shreks_providers::{
    pump::PumpCreationSignal, ProviderError, ProviderErrorKind, PumpSignalSource,
};
use tokio::sync::mpsc;

struct TwoSignalSource {
    next: usize,
}

#[async_trait]
impl PumpSignalSource for TwoSignalSource {
    async fn next_pump_signal(&mut self) -> Result<PumpCreationSignal, ProviderError> {
        self.next += 1;
        Ok(PumpCreationSignal {
            signature: format!("stream-sig-{}", self.next),
            slot: self.next as u64,
        })
    }
}

struct FailingSource;

#[async_trait]
impl PumpSignalSource for FailingSource {
    async fn next_pump_signal(&mut self) -> Result<PumpCreationSignal, ProviderError> {
        Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            "safe fixture stream failure",
        ))
    }
}

#[tokio::test]
async fn forwarding_task_sends_signals_and_stops_when_observer_receiver_is_gone() {
    let source = TwoSignalSource { next: 0 };
    let (sender, mut receiver) = mpsc::channel(1);

    let forwarding = forward_pump_signals(source, sender);
    let consume = async {
        let first = receiver.recv().await.unwrap();
        drop(receiver);
        first
    };

    let (result, first) = tokio::join!(forwarding, consume);
    result.unwrap();
    assert_eq!(first.signature, "stream-sig-1");
    assert_eq!(first.slot, 1);
}

#[tokio::test]
async fn forwarding_task_propagates_terminal_source_error() {
    let (sender, _receiver) = mpsc::channel(1);
    let error = forward_pump_signals(FailingSource, sender)
        .await
        .unwrap_err();

    assert_eq!(error.provider, ProviderId::Helius);
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
    assert_eq!(error.message, "safe fixture stream failure");
}
