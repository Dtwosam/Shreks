use std::{error::Error, time::Duration};

use shreks_observer::ObserverError;
use tokio::task::JoinHandle;

pub async fn finish_realtime_writer_shutdown(
    writer: &mut JoinHandle<Result<usize, ObserverError>>,
    _drain_timeout: Duration,
) -> Result<Option<usize>, Box<dyn Error>> {
    let result = writer.await;
    let rows = result.map_err(boxed_error)?.map_err(boxed_error)?;
    Ok(Some(rows))
}

fn boxed_error<E>(error: E) -> Box<dyn Error>
where
    E: Error + 'static,
{
    Box::new(error)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::future::pending;

    #[tokio::test]
    async fn completed_writer_drains_normally() {
        let mut writer = tokio::spawn(async { Ok::<usize, ObserverError>(7) });

        let rows = finish_realtime_writer_shutdown(&mut writer, Duration::from_millis(50))
            .await
            .unwrap();

        assert_eq!(rows, Some(7));
    }

    #[tokio::test]
    async fn stalled_writer_is_aborted_at_the_application_deadline() {
        let mut writer = tokio::spawn(async {
            pending::<Result<usize, ObserverError>>().await
        });

        let rows = tokio::time::timeout(
            Duration::from_millis(100),
            finish_realtime_writer_shutdown(&mut writer, Duration::from_millis(10)),
        )
        .await
        .expect("writer shutdown must return before the outer test deadline")
        .unwrap();

        assert_eq!(rows, None);

        let joined = tokio::time::timeout(Duration::from_millis(100), &mut writer)
            .await
            .expect("aborted writer must finish promptly");
        assert!(joined.unwrap_err().is_cancelled());
    }
}
