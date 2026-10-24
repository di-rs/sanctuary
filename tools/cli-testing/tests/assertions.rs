#![cfg(unix)]
#![allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify test helper contracts; Result propagates setup failures."
)]

use assert_fs::TempDir;
use cli_testing::TestContext;
use std::{fs, os::unix::fs::PermissionsExt, panic::catch_unwind};

type Result<T = ()> = std::result::Result<T, Box<dyn std::error::Error>>;

fn probe(script: &str) -> Result<(TempDir, TestContext)> {
    let dir = TempDir::new()?;
    let binary = dir.path().join("probe");
    fs::write(&binary, format!("#!/bin/sh\n{script}\n"))?;
    fs::set_permissions(&binary, fs::Permissions::from_mode(0o700))?;
    let context = TestContext::new(binary, dir.path());
    Ok((dir, context))
}

#[test]
fn help_checks_both_flags_with_shared_defaults() -> Result {
    let (dir, cx) = probe(
        r#"[ "$LC_ALL:$TZ:$SANCTUARY_LOG_LEVEL" = 'C:UTC:off' ] || exit 9
printf '%s\n' "$1" >> flags
printf 'Usage: probe\n'"#,
    )?;
    cx.assert_help();
    assert_eq!(
        fs::read_to_string(dir.path().join("flags"))?,
        "-h\n--help\n"
    );
    Ok(())
}

#[test]
fn help_rejects_each_flags_status_and_stream_violations() -> Result {
    for flag in ["-h", "--help"] {
        for failure in [
            "printf Usage; exit 2",
            "printf Usage; printf unexpected >&2",
            "printf 'missing heading'",
        ] {
            let (_dir, cx) = probe(&format!(
                "if [ \"$1\" = '{flag}' ]; then {failure}; else printf Usage; fi"
            ))?;
            assert!(
                catch_unwind(|| cx.assert_help()).is_err(),
                "{flag}: {failure}"
            );
        }
    }
    Ok(())
}

#[test]
fn error_checks_status_stdout_and_diagnostic() -> Result {
    let (_dir, cx) = probe("printf 'error: invalid value' >&2; exit 65")?;
    cx.assert_error([std::ffi::OsStr::new("invalid")], 65, "invalid value");
    for (script, status, diagnostic) in [
        ("printf invalid >&2; exit 2", 65, "invalid"),
        ("printf invalid >&2", 2, "invalid"),
        (
            "printf unexpected; printf invalid >&2; exit 2",
            2,
            "invalid",
        ),
        ("printf unrelated >&2; exit 2", 2, "invalid"),
        ("exit 2", 2, "invalid"),
        ("kill -TERM $$", 2, "invalid"),
    ] {
        let (_dir, cx) = probe(script)?;
        assert!(catch_unwind(|| cx.assert_error(["arg"], status, diagnostic)).is_err());
    }
    Ok(())
}

#[test]
fn invalid_expectations_fail_before_launch() -> Result {
    let (dir, cx) = probe("touch launched")?;
    for (status, diagnostic) in [(0, "error"), (-1, "error"), (256, "error"), (2, "")] {
        assert!(catch_unwind(|| cx.assert_error(["arg"], status, diagnostic)).is_err());
        assert!(!dir.path().join("launched").exists());
    }
    Ok(())
}
