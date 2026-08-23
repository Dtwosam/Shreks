from shreks_brain import runtime


def test_parses_every_supported_runtime_mode():
    cases = {
        "observe": "observe",
        "paper": "paper",
        "shadow": "shadow",
        "live": "live",
        "halted": "halted",
    }

    for raw, expected in cases.items():
        assert runtime.parse_runtime_mode(raw).value == expected


def test_none_defaults_to_observe():
    assert runtime.parse_runtime_mode(None).value == "observe"


def test_unknown_mode_is_rejected():
    try:
        runtime.parse_runtime_mode("YOLO")
    except ValueError as exc:
        assert "YOLO" in str(exc)
    else:
        raise AssertionError("invalid runtime mode must raise ValueError")
