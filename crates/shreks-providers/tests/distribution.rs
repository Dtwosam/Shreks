use shreks_core::{ProviderId, TokenDistributionRequest, TokenHolderDistribution};
use shreks_providers::{
    helius::{
        aggregate_token_account_pages, get_token_accounts_request, parse_token_accounts_page,
    },
    DistributionDataProvider, ProviderErrorKind,
};

#[test]
fn distribution_request_rejects_unbounded_or_blank_inputs() {
    let request = TokenDistributionRequest::new("Mint111", 1_000, 10)
        .expect("bounded holder scan request");
    assert_eq!(request.mint, "Mint111");
    assert_eq!(request.page_size, 1_000);
    assert_eq!(request.max_pages, 10);

    assert!(TokenDistributionRequest::new("", 1_000, 10).is_err());
    assert!(TokenDistributionRequest::new("Mint111", 0, 10).is_err());
    assert!(TokenDistributionRequest::new("Mint111", 1_001, 10).is_err());
    assert!(TokenDistributionRequest::new("Mint111", 1_000, 0).is_err());
}

#[test]
fn distribution_provider_trait_is_object_safe() {
    fn accepts_provider(_: &dyn DistributionDataProvider) {}
    let _ = accepts_provider;
}

#[test]
fn token_accounts_request_uses_exact_mint_page_limit_and_zero_balance_filter() {
    let request = TokenDistributionRequest::new("Mint111", 500, 4).unwrap();
    let body = get_token_accounts_request(&request, 3).expect("valid third page");

    assert_eq!(body["jsonrpc"], "2.0");
    assert_eq!(body["method"], "getTokenAccounts");
    assert_eq!(body["params"]["mint"], "Mint111");
    assert_eq!(body["params"]["page"], 3);
    assert_eq!(body["params"]["limit"], 500);
    assert_eq!(body["params"]["options"]["showZeroBalance"], false);

    assert!(get_token_accounts_request(&request, 0).is_err());
}

#[test]
fn parses_token_account_rows_and_response_provenance_without_ui_amounts() {
    let body = r#"{
      "jsonrpc":"2.0",
      "id":"holder-page",
      "result":{
        "last_indexed_slot":777,
        "total":3,
        "limit":1000,
        "cursor":"next-page",
        "token_accounts":[
          {"address":"TA1","mint":"Mint111","owner":"WalletA","amount":40,"delegated_amount":0,"frozen":false},
          {"address":"TA2","mint":"Mint111","owner":"WalletA","amount":30,"delegated_amount":0,"frozen":false},
          {"address":"TA3","mint":"Mint111","owner":"WalletB","amount":80,"delegated_amount":0,"frozen":false}
        ]
      }
    }"#;

    let page = parse_token_accounts_page(body, "Mint111").expect("valid token account page");
    assert_eq!(page.last_indexed_slot, 777);
    assert_eq!(page.total, 3);
    assert_eq!(page.limit, 1_000);
    assert_eq!(page.cursor.as_deref(), Some("next-page"));
    assert_eq!(page.accounts.len(), 3);
    assert_eq!(page.accounts[0].address, "TA1");
    assert_eq!(page.accounts[0].owner, "WalletA");
    assert_eq!(page.accounts[0].amount_raw, 40);
    assert_eq!(page.accounts[2].owner, "WalletB");
    assert_eq!(page.accounts[2].amount_raw, 80);
}

#[test]
fn parser_rejects_wrong_mint_malformed_amount_and_rpc_error() {
    let wrong_mint = r#"{
      "jsonrpc":"2.0","id":"x","result":{
        "last_indexed_slot":1,"total":1,"limit":100,"cursor":null,
        "token_accounts":[
          {"address":"TA1","mint":"OtherMint","owner":"WalletA","amount":1}
        ]
      }
    }"#;
    let malformed_amount = r#"{
      "jsonrpc":"2.0","id":"x","result":{
        "last_indexed_slot":1,"total":1,"limit":100,"cursor":null,
        "token_accounts":[
          {"address":"TA1","mint":"Mint111","owner":"WalletA","amount":"not-a-number"}
        ]
      }
    }"#;
    let rpc_error = r#"{
      "jsonrpc":"2.0","id":"x","error":{"code":-32602,"message":"Invalid params"}
    }"#;

    let error = parse_token_accounts_page(wrong_mint, "Mint111").expect_err("mint mismatch");
    assert_eq!(error.kind, ProviderErrorKind::InvalidResponse);
    assert!(parse_token_accounts_page(malformed_amount, "Mint111").is_err());
    assert!(parse_token_accounts_page(rpc_error, "Mint111").is_err());
}

#[test]
fn complete_pages_aggregate_token_accounts_by_wallet_owner() {
    let request = TokenDistributionRequest::new("Mint111", 3, 4).unwrap();
    let first = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":777,"total":5,"limit":3,"cursor":"p2",
          "token_accounts":[
            {"address":"TA1","mint":"Mint111","owner":"WalletA","amount":40},
            {"address":"TA2","mint":"Mint111","owner":"WalletA","amount":30},
            {"address":"TA3","mint":"Mint111","owner":"WalletB","amount":80}
          ]
        }}"#,
        "Mint111",
    )
    .unwrap();
    let terminal = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":777,"total":5,"limit":3,"cursor":null,
          "token_accounts":[
            {"address":"TA4","mint":"Mint111","owner":"WalletC","amount":50},
            {"address":"TA5","mint":"Mint111","owner":"WalletD","amount":0}
          ]
        }}"#,
        "Mint111",
    )
    .unwrap();

    let distribution =
        aggregate_token_account_pages(&request, &[first, terminal], 1_700_000_000_000)
            .expect("complete distribution");

    assert_eq!(distribution.provider, ProviderId::Helius);
    assert_eq!(distribution.mint, "Mint111");
    assert_eq!(distribution.last_indexed_slot, 777);
    assert_eq!(distribution.observed_at_unix_ms, 1_700_000_000_000);
    assert_eq!(distribution.accounts_scanned, 5);
    assert_eq!(distribution.unique_owners, 4);
    assert_eq!(distribution.pages_scanned, 2);
    assert!(distribution.complete);
    assert_eq!(distribution.total_balance_raw, 200);
    assert_eq!(distribution.largest_owner.as_deref(), Some("WalletB"));
    assert_eq!(distribution.largest_owner_balance_raw, Some(80));
    assert_eq!(distribution.top_holder_concentration_pct, Some(40.0));
}

#[test]
fn max_page_budget_before_reported_total_is_incomplete_and_never_exposes_concentration() {
    let request = TokenDistributionRequest::new("Mint111", 2, 2).unwrap();
    let page_one = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":9,"total":6,"limit":2,"cursor":"p2",
          "token_accounts":[
            {"address":"TA1","mint":"Mint111","owner":"WalletA","amount":50},
            {"address":"TA2","mint":"Mint111","owner":"WalletB","amount":30}
          ]
        }}"#,
        "Mint111",
    )
    .unwrap();
    let page_two = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":9,"total":6,"limit":2,"cursor":"p3",
          "token_accounts":[
            {"address":"TA3","mint":"Mint111","owner":"WalletA","amount":20},
            {"address":"TA4","mint":"Mint111","owner":"WalletC","amount":10}
          ]
        }}"#,
        "Mint111",
    )
    .unwrap();

    let distribution = aggregate_token_account_pages(&request, &[page_one, page_two], 99)
        .expect("bounded partial distribution");

    assert!(!distribution.complete);
    assert_eq!(distribution.total_balance_raw, 110);
    assert_eq!(distribution.largest_owner.as_deref(), Some("WalletA"));
    assert_eq!(distribution.largest_owner_balance_raw, Some(70));
    assert_eq!(distribution.top_holder_concentration_pct, None);
}

#[test]
fn page_provenance_must_be_coherent_and_duplicate_accounts_are_deduplicated() {
    let request = TokenDistributionRequest::new("Mint111", 2, 3).unwrap();
    let first = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":44,"total":2,"limit":2,"cursor":"p2",
          "token_accounts":[
            {"address":"TA1","mint":"Mint111","owner":"WalletA","amount":60},
            {"address":"TA2","mint":"Mint111","owner":"WalletB","amount":40}
          ]
        }}"#,
        "Mint111",
    )
    .unwrap();
    let duplicate_terminal = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":44,"total":2,"limit":2,"cursor":null,
          "token_accounts":[
            {"address":"TA2","mint":"Mint111","owner":"WalletB","amount":40}
          ]
        }}"#,
        "Mint111",
    )
    .unwrap();

    let distribution = aggregate_token_account_pages(
        &request,
        &[first.clone(), duplicate_terminal],
        100,
    )
    .unwrap();
    assert!(distribution.complete);
    assert_eq!(distribution.accounts_scanned, 2);
    assert_eq!(distribution.total_balance_raw, 100);
    assert_eq!(distribution.top_holder_concentration_pct, Some(60.0));

    let changed_slot = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":45,"total":2,"limit":2,"cursor":null,
          "token_accounts":[]
        }}"#,
        "Mint111",
    )
    .unwrap();
    assert!(aggregate_token_account_pages(&request, &[first.clone(), changed_slot], 101).is_err());

    let changed_total = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":44,"total":3,"limit":2,"cursor":null,
          "token_accounts":[]
        }}"#,
        "Mint111",
    )
    .unwrap();
    assert!(aggregate_token_account_pages(&request, &[first, changed_total], 102).is_err());
}

#[test]
fn checked_add_rejects_owner_or_total_balance_overflow() {
    let request = TokenDistributionRequest::new("Mint111", 2, 2).unwrap();
    let first = parse_token_accounts_page(
        r#"{"jsonrpc":"2.0","result":{
          "last_indexed_slot":1,"total":2,"limit":2,"cursor":null,
          "token_accounts":[
            {"address":"TA1","mint":"Mint111","owner":"WalletA","amount":18446744073709551615},
            {"address":"TA2","mint":"Mint111","owner":"WalletA","amount":1}
          ]
        }}"#,
        "Mint111",
    )
    .unwrap();

    assert!(aggregate_token_account_pages(&request, &[first], 101).is_err());
}

#[test]
fn normalized_distribution_type_exists_at_the_provider_neutral_boundary() {
    fn accepts_distribution(_: TokenHolderDistribution) {}
    let _ = accepts_distribution;
}
