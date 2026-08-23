use async_trait::async_trait;
use shreks_core::ProviderId;
use shreks_providers::{
    forward_pump_signals,
    pump::{PumpCreationSignal, PumpLifecycleSignal, PumpMigrationSignal},
    ProviderError, ProviderErrorKind, PumpSignalSource,
};
use tokio::sync::mpsc;

struct TwoSignalSource {
    next: usize,
}

#[async_trait]
impl PumpSignalSource for TwoSignalSource {
    async fn next_pump_signal(&mut self) -> Result<PumpLifecycleSignal, ProviderError> {
        self.next += 1;
        let signal = if self.next == 1 {
            PumpLifecycleSignal::Creation(PumpCreationSignal {
                signature: "stream-create-1".to_owned(),
                slot: 1,
            })
        } else {
            PumpLifecycleSignal::Migration(PumpMigrationSignal {
                signature: "stream-migrate-2".to_owned(),
                slot: 2,
            })
        };
        Ok(signal)
    }
}

struct FailingSource;

#[async_trait]
impl PumpSignalSource for FailingSource {
    async fn next_pump_signal(&mut self) -> Result<PumpLifecycleSignal, ProviderError> {
        Err(ProviderError::new(
            ProviderId::Helius,
            ProviderErrorKind::InvalidResponse,
            "safe fixture stream failure",
        ))
    }
}

#[tokio::test]
async fn forwarding_task_sends_creation_and_migration_and_stops_when_receiver_is_gone() {
    let source = TwoSignalSource { next: 0 };
    let (sender, mut receiver) = mpsc::channel(2);

    let forwarding = tokio::spawn(forward_pump_signals(source, sender));
    let first = receiver.recv().await.unwrap();
    let second = receiver.recv().await.unwrap();
    drop(receiver);
    forwarding.await.unwrap().unwrap();

    let PumpLifecycleSignal::Creation(first) = first else {
        panic!("first signal must be creation");
    };
    assert_eq!(first.signature, "stream-create-1");
    assert_eq!(first.slot, 1);

    let PumpLifecycleSignal::Migration(second) = second else {
        panic!("second signal must be migration");
    };
    assert_eq!(second.signature, "stream-migrate-2");
    assert_eq!(second.slot, 2);
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
