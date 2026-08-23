use shreks_providers::{
    pump::{
        classify_pump_migration_transaction, parse_pump_lifecycle_log_notification,
        PumpLifecycleSignal, PumpMigrationVerification, PUMP_AMM_PROGRAM_ID,
        PUMP_MIGRATE_DISCRIMINATOR, PUMP_MIGRATE_V2_DISCRIMINATOR, PUMP_PROGRAM_ID,
        WRAPPED_SOL_MINT,
    },
    ProviderErrorKind,
};

const MINT: &str = "9cRCn9rGT8V2imeM2BaKs13yhMEais3ruM3rPvTGpump";
const QUOTE: &str = "quote-mint-111111111111111111111111111111111";
const POOL: &str = "pump-swap-pool-1111111111111111111111111111111";

fn lifecycle_notification(signature: &str, slot: u64, instruction: &str) -> String {
    format!(
        r#"{{
          "jsonrpc":"2.0",
          "method":"logsNotification",
          "params":{{
            "result":{{
              "context":{{"slot":{slot}}},
              "value":{{
                "signature":"{signature}",
                "err":null,
                "logs":[
                  "Program {PUMP_PROGRAM_ID} invoke [1]",
                  "Program log: Instruction: {instruction}"
                ]
              }}
            }},
            "subscription":24040
          }}
        }}"#
    )
}

fn instruction(program_id: &str, discriminator: [u8; 8], accounts: &[&str]) -> String {
    let data = bs58::encode(discriminator).into_string();
    let accounts = accounts
        .iter()
        .map(|account| format!("\"{account}\""))
        .collect::<Vec<_>>()
        .join(",");
    format!(
        r#"{{"programId":"{program_id}","data":"{data}","accounts":[{accounts}]}}"#
    )
}

fn transaction_body(
    block_time: &str,
    outer_instructions: &[String],
    inner_instructions: &[String],
) -> String {
    let outer = outer_instructions.join(",");
    let inner = inner_instructions.join(",");
    let inner_groups = if inner_instructions.is_empty() {
        "[]".to_owned()
    } else {
        format!(r#"[{{"index":0,"instructions":[{inner}]}}]"#)
    };
    format!(
        r#"{{
          "jsonrpc":"2.0",
          "result":{{
            "slot":987654321,
            "blockTime":{block_time},
            "meta":{{"err":null,"innerInstructions":{inner_groups}}},
            "transaction":{{"message":{{"instructions":[{outer}]}}}}
          }},
          "id":"shreks-pump-migration"
        }}"#
    )
}

fn legacy_accounts() -> Vec<&'static str> {
    vec![
        "global",
        "withdraw-authority",
        MINT,
        "bonding-curve",
        "associated-bonding-curve",
        "user",
        "system-program",
        "token-program",
        PUMP_AMM_PROGRAM_ID,
        POOL,
        "pool-authority",
        "pool-base-token-account",
        "pool-quote-token-account",
        "associated-token-program",
        WRAPPED_SOL_MINT,
    ]
}

fn v2_accounts() -> Vec<&'static str> {
    vec![
        "global",
        "withdraw-authority",
        MINT,
        QUOTE,
        "bonding-curve",
        "associated-bonding-curve",
        "user",
        "system-program",
        "token-program",
        PUMP_AMM_PROGRAM_ID,
        POOL,
    ]
}

#[test]
fn official_migration_constants_are_stable() {
    assert_eq!(
        PUMP_MIGRATE_DISCRIMINATOR,
        [155, 234, 231, 146, 236, 158, 162, 30]
    );
    assert_eq!(
        PUMP_MIGRATE_V2_DISCRIMINATOR,
        [187, 203, 18, 31, 206, 237, 254, 41]
    );
    assert_eq!(WRAPPED_SOL_MINT, "So11111111111111111111111111111111111111112");
}

#[test]
fn lifecycle_log_parser_distinguishes_creation_and_migration_exactly() {
    let creation = parse_pump_lifecycle_log_notification(&lifecycle_notification(
        "create-v2",
        41,
        "CreateV2",
    ))
    .unwrap()
    .unwrap();
    match creation {
        PumpLifecycleSignal::Creation(signal) => {
            assert_eq!(signal.signature, "create-v2");
            assert_eq!(signal.slot, 41);
        }
        other => panic!("expected creation signal, got {other:?}"),
    }

    for (name, slot) in [("Migrate", 42), ("MigrateV2", 43)] {
        let migration = parse_pump_lifecycle_log_notification(&lifecycle_notification(
            "migration",
            slot,
            name,
        ))
        .unwrap()
        .unwrap();
        match migration {
            PumpLifecycleSignal::Migration(signal) => {
                assert_eq!(signal.signature, "migration");
                assert_eq!(signal.slot, slot);
            }
            other => panic!("expected migration signal, got {other:?}"),
        }
    }

    let creator_admin = lifecycle_notification(
        "not-a-graduation",
        44,
        "MigrateBondingCurveCreator",
    );
    assert!(parse_pump_lifecycle_log_notification(&creator_admin)
        .unwrap()
        .is_none());
}

#[test]
fn result_null_is_pending_instead_of_rejected() {
    let body = r#"{"jsonrpc":"2.0","result":null,"id":"shreks-pump-migration"}"#;
    assert_eq!(
        classify_pump_migration_transaction(body, "migration-signature").unwrap(),
        PumpMigrationVerification::Pending
    );
}

#[test]
fn legacy_migrate_extracts_wsol_quote_pool_and_block_time() {
    let body = transaction_body(
        "1770000000",
        &[instruction(
            PUMP_PROGRAM_ID,
            PUMP_MIGRATE_DISCRIMINATOR,
            &legacy_accounts(),
        )],
        &[],
    );
    let outcome = classify_pump_migration_transaction(&body, "legacy-migration").unwrap();
    let PumpMigrationVerification::Verified(evidence) = outcome else {
        panic!("expected verified legacy migration, got {outcome:?}");
    };
    assert_eq!(evidence.len(), 1);
    assert_eq!(evidence[0].mint, MINT);
    assert_eq!(evidence[0].quote_mint, WRAPPED_SOL_MINT);
    assert_eq!(evidence[0].pool_address, POOL);
    assert_eq!(evidence[0].occurred_at_unix_ms, Some(1_770_000_000_000));
}

#[test]
fn migrate_v2_extracts_base_quote_pool_and_allows_null_block_time() {
    let body = transaction_body(
        "null",
        &[instruction(
            PUMP_PROGRAM_ID,
            PUMP_MIGRATE_V2_DISCRIMINATOR,
            &v2_accounts(),
        )],
        &[],
    );
    let outcome = classify_pump_migration_transaction(&body, "v2-migration").unwrap();
    let PumpMigrationVerification::Verified(evidence) = outcome else {
        panic!("expected verified migrate_v2, got {outcome:?}");
    };
    assert_eq!(evidence.len(), 1);
    assert_eq!(evidence[0].mint, MINT);
    assert_eq!(evidence[0].quote_mint, QUOTE);
    assert_eq!(evidence[0].pool_address, POOL);
    assert_eq!(evidence[0].occurred_at_unix_ms, None);
}

#[test]
fn valid_inner_migration_is_supported_and_duplicate_evidence_is_deduplicated() {
    let migration = instruction(
        PUMP_PROGRAM_ID,
        PUMP_MIGRATE_V2_DISCRIMINATOR,
        &v2_accounts(),
    );
    let body = transaction_body("1770000001", &[migration.clone()], &[migration]);
    let outcome = classify_pump_migration_transaction(&body, "inner-and-outer").unwrap();
    let PumpMigrationVerification::Verified(evidence) = outcome else {
        panic!("expected verified migration, got {outcome:?}");
    };
    assert_eq!(evidence.len(), 1);
    assert_eq!(evidence[0].mint, MINT);
    assert_eq!(evidence[0].quote_mint, QUOTE);
    assert_eq!(evidence[0].pool_address, POOL);
}

#[test]
fn identity_and_minimum_account_checks_fail_closed() {
    let mut bad_legacy = legacy_accounts();
    bad_legacy[8] = "spoofed-pumpswap-program";
    let wrong_pumpswap = transaction_body(
        "1770000000",
        &[instruction(
            PUMP_PROGRAM_ID,
            PUMP_MIGRATE_DISCRIMINATOR,
            &bad_legacy,
        )],
        &[],
    );
    assert!(matches!(
        classify_pump_migration_transaction(&wrong_pumpswap, "wrong-pumpswap").unwrap(),
        PumpMigrationVerification::Rejected(_)
    ));

    let mut wrong_wsol = legacy_accounts();
    wrong_wsol[14] = QUOTE;
    let wrong_quote = transaction_body(
        "1770000000",
        &[instruction(
            PUMP_PROGRAM_ID,
            PUMP_MIGRATE_DISCRIMINATOR,
            &wrong_wsol,
        )],
        &[],
    );
    assert!(matches!(
        classify_pump_migration_transaction(&wrong_quote, "wrong-wsol").unwrap(),
        PumpMigrationVerification::Rejected(_)
    ));

    let short_v2 = transaction_body(
        "1770000000",
        &[instruction(
            PUMP_PROGRAM_ID,
            PUMP_MIGRATE_V2_DISCRIMINATOR,
            &v2_accounts()[..10],
        )],
        &[],
    );
    assert!(matches!(
        classify_pump_migration_transaction(&short_v2, "short-v2").unwrap(),
        PumpMigrationVerification::Rejected(_)
    ));

    let wrong_program = transaction_body(
        "1770000000",
        &[instruction(
            PUMP_AMM_PROGRAM_ID,
            PUMP_MIGRATE_V2_DISCRIMINATOR,
            &v2_accounts(),
        )],
        &[],
    );
    assert!(matches!(
        classify_pump_migration_transaction(&wrong_program, "wrong-program").unwrap(),
        PumpMigrationVerification::Rejected(_)
    ));
}

#[test]
fn invalid_block_time_is_provider_error_not_false_chain_evidence() {
    for invalid in ["-1", "9223372036854776", "\"not-a-number\""] {
        let body = transaction_body(
            invalid,
            &[instruction(
                PUMP_PROGRAM_ID,
                PUMP_MIGRATE_V2_DISCRIMINATOR,
                &v2_accounts(),
            )],
            &[],
        );
        let error = classify_pump_migration_transaction(&body, "bad-time").unwrap_err();
        assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
    }
}
