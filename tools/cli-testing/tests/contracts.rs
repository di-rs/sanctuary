#![cfg(unix)]
#![allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify catalog contracts; Result propagates setup failures."
)]

use assert_fs::TempDir;
use cli_testing::{TestContext, cargo_bin_cmd, catalog::Suite, recording, reference};
use predicates::prelude::*;
use std::{fs, os::unix::fs::PermissionsExt};

type Result<T = ()> = std::result::Result<T, Box<dyn std::error::Error>>;

fn package(recipe: &str, script: &str) -> Result<(TempDir, TestContext)> {
    let dir = TempDir::new()?;
    fs::create_dir(dir.path().join("tests"))?;
    fs::write(dir.path().join("Cargo.toml"), "[package]\nname = 'probe'\n")?;
    fs::write(
        dir.path().join("tests/cases.toml"),
        format!("schema = 1\nbinary = 'probe'\n{recipe}"),
    )?;
    let binary = dir.path().join("probe");
    fs::write(&binary, format!("#!/bin/sh\n{script}\n"))?;
    fs::set_permissions(&binary, fs::Permissions::from_mode(0o700))?;
    let context = TestContext::new(binary, dir.path());
    Ok((dir, context))
}

const ERROR: &str = r#"
[[cases]]
name = "rejects_invalid"
args = ["invalid"]
origin = { manual = "Only numeric values are accepted." }
[cases.expect]
exit = 65
stdout = ""
stderr_contains = "invalid value"
"#;

#[test]
fn omitted_expectations_check_success_and_both_streams() -> Result {
    for expectation in ["", "expect = {}", "expect = { exit = 0 }"] {
        let recipe = format!(
            "[[cases]]\nname = 'success'\nargs = []\norigin = {{ manual = 'Print the greeting.' }}\n{expectation}"
        );
        for (script, succeeds) in [
            ("printf 'hello\\n'", true),
            ("printf 'hello\\n'; exit 2", false),
            ("printf 'hello\\n'; printf unexpected >&2", false),
            ("printf wrong", false),
        ] {
            let (dir, cx) = package(&recipe, script)?;
            assert!(cx.suite().is_err(), "the stdout fixture must exist");
            fs::create_dir(dir.path().join("tests/expected"))?;
            fs::write(dir.path().join("tests/expected/success.out"), "hello\n")?;
            assert_eq!(cx.case("success")?.check().is_ok(), succeeds, "{script}");
        }
    }
    Ok(())
}

#[test]
fn inline_output_overrides_default_to_success() -> Result {
    let recipe = r#"
[[cases]]
name = "success"
args = []
origin = { manual = "Print the greeting." }
expect = { stdout = "hello\n" }
"#;
    let (_dir, cx) = package(recipe, "printf 'hello\\n'")?;
    cx.case("success")?.check()?;
    let (_dir, cx) = package(recipe, "printf 'hello\\n'; exit 1")?;
    assert!(cx.case("success")?.check().is_err());
    Ok(())
}

#[test]
fn help_expands_without_reference_inheritance_and_uses_shared_defaults() -> Result {
    let (dir, cx) = package(
        &format!(
            "checks = ['help']\nreference = 'unused'\n[references.unused]\nprogram = '/unavailable'\nplatform = '{}'\n",
            std::env::consts::OS
        ),
        r#"[ "$LC_ALL:$TZ:$SANCTUARY_LOG_LEVEL" = 'C:UTC:off' ] || exit 9
printf '%s\n' "$1" >> flags
printf 'Usage: probe\n'"#,
    )?;
    let suite = cx.suite()?;
    assert_eq!(
        suite
            .cases
            .iter()
            .map(|case| case.name.as_str())
            .collect::<Vec<_>>(),
        ["help_short", "help_long"]
    );
    for case in &suite.cases {
        assert!(case.origin.reference.is_none());
        cx.case(&case.name)?.check()?;
    }
    assert_eq!(
        fs::read_to_string(dir.path().join("flags"))?,
        "-h\n--help\n"
    );
    assert_eq!(
        suite.unreferenced_expected()?,
        Vec::<std::path::PathBuf>::new()
    );
    Ok(())
}

#[test]
fn help_rejects_each_flags_status_and_stream_violations() -> Result {
    for (name, flag) in [("help_short", "-h"), ("help_long", "--help")] {
        for failure in [
            "printf Usage; exit 2",
            "printf Usage; printf unexpected >&2",
            "printf 'missing heading'",
        ] {
            let (_dir, cx) = package(
                "checks = ['help']",
                &format!("if [ \"$1\" = '{flag}' ]; then {failure}; else printf Usage; fi"),
            )?;
            let error = cx
                .case(name)?
                .check()
                .err()
                .ok_or("invalid help accepted")?;
            assert!(error.to_string().contains(name));
            assert!(error.to_string().contains("help contract"));
        }
    }
    Ok(())
}

#[test]
fn manual_contains_checks_status_and_streams_without_decoding_bytes() -> Result {
    let (_dir, cx) = package(ERROR, "printf 'prefix: invalid value\\377' >&2; exit 65")?;
    cx.case("rejects_invalid")?.check()?;
    for script in [
        "printf 'invalid value' >&2; exit 2",
        "printf 'invalid value' >&2",
        "printf unexpected; printf 'invalid value' >&2; exit 65",
        "printf unrelated >&2; exit 65",
        "exit 65",
        "kill -TERM $$",
    ] {
        let (_dir, cx) = package(ERROR, script)?;
        let error = cx
            .case("rejects_invalid")?
            .check()
            .err()
            .ok_or("invalid result accepted")?;
        assert!(
            error
                .to_string()
                .contains("Only numeric values are accepted.")
        );
    }
    Ok(())
}

#[test]
fn invalid_contracts_fail_before_launch() -> Result {
    for recipe in [
        ERROR.replace(
            "stderr_contains = \"invalid value\"",
            "stderr_contains = ''",
        ),
        ERROR.replace("stderr_contains", "stderr = ''\nstderr_contains"),
        ERROR.replace("stdout = \"\"", "stdout = ''\nstdout_contains = 'text'"),
        ERROR.replace(
            "stdout = \"\"",
            "stdout_file = 'missing.out'\nstdout_contains = 'text'",
        ),
        ERROR.replace("exit = 65", "exit = 256"),
        ERROR.replace("exit = 65", "exit = -1"),
        "checks = ['unknown']".into(),
        "checks = ['help', 'help']".into(),
        format!(
            "checks = ['help']\n{}",
            ERROR.replace("rejects_invalid", "help_short")
        ),
        ERROR.replace(
            "origin = { manual = \"Only numeric values are accepted.\" }",
            "",
        ),
        format!(
            "reference = 'shell'\n[references.shell]\nprogram = '/bin/sh'\nplatform = 'macos'\n{}",
            ERROR.replace(
                "origin = { manual = \"Only numeric values are accepted.\" }",
                ""
            )
        ),
    ] {
        let (dir, cx) = package(&recipe, "touch launched")?;
        assert!(cx.suite().is_err(), "{recipe}");
        assert!(!dir.path().join("launched").exists());
    }
    Ok(())
}

#[test]
fn substring_expectations_do_not_change_exact_defaults_or_customization() -> Result {
    let (_dir, cx) = package(ERROR, "printf 'invalid value extra' >&2; exit 65")?;
    let mut case = cx.case("rejects_invalid")?;
    case.expect_stderr(b"invalid value".to_vec())?;
    assert!(case.check().is_err());
    let (_dir, cx) = package("checks = ['help']", "printf Usage")?;
    assert!(
        cx.case("help_short")?
            .map_expected_stdout(<[u8]>::to_vec)
            .is_err()
    );
    let (_dir, cx) = package(&ERROR.replace("stdout = \"\"", ""), "exit 65")?;
    assert!(
        cx.suite().is_err(),
        "omitted stdout must still require the named fixture"
    );
    Ok(())
}

#[test]
fn inspection_and_comparison_show_expanded_contracts() -> Result {
    let (dir, cx) = package(&format!("checks = ['help']\n{ERROR}"), "printf Usage")?;
    let suite = dir.path().join("tests/cases.toml");
    for command in ["list", "explain"] {
        let mut cmd = cargo_bin_cmd!();
        cmd.arg("--suite").arg(&suite).arg(command);
        if command == "explain" {
            cmd.arg("help_long");
        }
        cmd.assert().code(0).stderr("").stdout(
            predicate::str::contains("contains \"Usage\"")
                .and(predicate::str::contains("help_long")),
        );
    }
    cargo_bin_cmd!()
        .arg("--suite")
        .arg(&suite)
        .args(["explain", "rejects_invalid"])
        .assert()
        .code(0)
        .stderr("")
        .stdout(
            predicate::str::contains("Only numeric values are accepted.")
                .and(predicate::str::contains("contains \"invalid value\"")),
        );
    reference::compare(
        &cx.suite()?,
        cx.suite()?.case("help_short")?,
        &dir.path().join("probe"),
    )?;
    Ok(())
}

#[test]
fn recording_and_apply_only_touch_exact_reference_cases() -> Result {
    let recipe = format!(
        r#"checks = ["help"]
reference = "shell"
[references.shell]
program = "/bin/sh"
platform = "{}"
[[cases]]
name = "exact"
args = ["-c", "printf expected"]
expect = {{ exit = 0 }}
{ERROR}
"#,
        std::env::consts::OS
    );
    let (dir, cx) = package(&recipe, "exit 1")?;
    fs::create_dir(dir.path().join("tests/expected"))?;
    let expected = dir.path().join("tests/expected/exact.out");
    fs::write(&expected, "previous")?;
    let suite = cx.suite()?;
    let recording_dir = dir.path().join("recording");
    assert_eq!(recording::record(&suite, &recording_dir)?, 1);
    assert!(!recording_dir.join("help_short.stdout").exists());
    assert!(!recording_dir.join("rejects_invalid.stderr").exists());
    assert_eq!(recording::preview(&suite, &recording_dir)?.len(), 1);
    assert_eq!(recording::apply(&suite, &recording_dir)?.len(), 1);
    assert_eq!(fs::read(&expected)?, b"expected");
    assert_eq!(
        Suite::load(suite.path())?.unreferenced_expected()?,
        Vec::<std::path::PathBuf>::new()
    );
    Ok(())
}
