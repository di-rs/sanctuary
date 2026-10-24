#![allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify the generated native test contract."
)]

use cli_testing::{TestContext, cli_test};
use std::{ffi::OsStr, process::Command};

type Result<T = ()> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cli_test]
fn injects_package_defaults(cx: &TestContext) {
    let command = cx.std_command();
    assert_eq!(
        command.get_current_dir(),
        Some(std::path::Path::new(env!("CARGO_MANIFEST_DIR")))
    );
    assert!(
        command
            .get_envs()
            .any(|entry| entry == (OsStr::new("LC_ALL"), Some(OsStr::new("C"))))
    );
    cx.command().arg("--version").assert().code(0).stderr("");
}

#[cli_test]
fn workspaces_are_independent(cx: &TestContext) -> Result {
    let first = cx.workspace()?;
    let second = cx.workspace()?;
    assert_ne!(first.path(), second.path());
    std::fs::write(first.path().join("marker"), b"first")?;
    assert!(!second.path().join("marker").exists());
    let path = first.path().to_owned();
    drop(first);
    assert!(!path.exists());
    Ok(())
}

#[cli_test]
#[allow(
    clippy::unnecessary_wraps,
    reason = "Verify native Result return types without executing a command."
)]
fn library_result_without_execution(_cx: &TestContext) -> cli_testing::Result<()> {
    Ok(())
}

#[cli_test]
#[cfg(any())]
fn disabled(_cx: &TestContext) {
    does_not_exist();
}

#[cli_test]
#[ignore = "Executed explicitly by the failure propagation test"]
fn body_error(_cx: &TestContext) -> Result {
    Err("native body error".into())
}

#[cli_test]
#[ignore = "Executed explicitly by the failure propagation test"]
fn body_panic(_cx: &TestContext) {
    panic!("native body panic");
}

#[test]
fn errors_and_panics_fail_the_generated_test() -> Result {
    for (name, message) in [
        ("body_error", "native body error"),
        ("body_panic", "native body panic"),
    ] {
        let output = Command::new(std::env::current_exe()?)
            .args(["--exact", name, "--ignored", "--nocapture"])
            .output()?;
        assert_eq!(output.status.code(), Some(101));
        assert!(String::from_utf8(output.stderr)?.contains(message));
    }
    Ok(())
}
