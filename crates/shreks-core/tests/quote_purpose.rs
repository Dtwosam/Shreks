use shreks_core::QuotePurpose;

#[test]
fn quote_purpose_uses_exact_stable_persistence_vocabulary() {
    assert_eq!(QuotePurpose::Entry.as_str(), "entry");
    assert_eq!(QuotePurpose::Exit.as_str(), "exit");
    assert_ne!(QuotePurpose::Entry, QuotePurpose::Exit);
}
