use assert_fs::prelude::*;
use cli_testing::{Context, TestContext, cli_test, test_case};
use predicates::prelude::*;
use std::{
    fs,
    path::Path,
    time::{Duration, UNIX_EPOCH},
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions fail the test; Result propagates fixture I/O errors."
)]
fn assert_modified(path: &Path, seconds: u64) -> Result<()> {
    assert_eq!(
        fs::metadata(path)?.modified()?.duration_since(UNIX_EPOCH)?,
        Duration::from_secs(seconds)
    );
    Ok(())
}

#[cli_test]
fn usage(cx: &TestContext) {
    cx.assert_help();
}

#[test_case("creates_single_file")]
fn creates_single_file(cx: &mut Context) -> cli_testing::Result<()> {
    cx.workspace()?;
    cx.run()?;
    cx.workspace()?
        .child("new")
        .assert(predicate::path::is_file());
    cx.workspace()?.child("new").assert("");
    Ok(())
}

#[cli_test]
#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions fail the test; Result propagates fixture I/O errors."
)]
fn preserves_contents_and_updates_existing_file(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    let file = dir.child("existing");
    file.write_str("keep these contents\n")?;
    fs::File::open(file.path())?.set_modified(UNIX_EPOCH)?;
    dir.cmd()
        .arg("existing")
        .assert()
        .success()
        .stdout("")
        .stderr("");
    file.assert("keep these contents\n");
    assert!(fs::metadata(file.path())?.modified()? > UNIX_EPOCH);
    Ok(())
}

#[cli_test]
fn sets_supported_numeric_timestamps_on_multiple_files(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    for (timestamp, seconds) in [
        ("200001010000", 946_684_800),
        ("20000101000007", 946_684_807),
    ] {
        dir.child("existing").write_str("preserve me")?;
        let new = dir.child(format!("new-{timestamp}"));
        dir.cmd()
            .args(["-t", timestamp, "existing"])
            .arg(new.path())
            .assert()
            .success()
            .stdout("")
            .stderr("");
        dir.child("existing").assert("preserve me");
        new.assert("");
        assert_modified(dir.child("existing").path(), seconds)?;
        assert_modified(new.path(), seconds)?;
    }
    Ok(())
}

#[cli_test]
fn c_does_not_create_missing_files(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.cmd()
        .args(["-c", "missing", "also-missing"])
        .assert()
        .success()
        .stdout("")
        .stderr("");
    for name in ["missing", "also-missing"] {
        dir.child(name).assert(predicate::path::missing());
    }
    Ok(())
}

#[cli_test]
fn c_still_updates_existing_files(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("existing").write_str("keep me")?;
    dir.cmd()
        .args(["-c", "-t", "20000101000007", "missing", "existing"])
        .assert()
        .success()
        .stdout("")
        .stderr("");
    dir.child("missing").assert(predicate::path::missing());
    dir.child("existing").assert("keep me");
    assert_modified(dir.child("existing").path(), 946_684_807)
}

#[cli_test]
fn rejects_invalid_timestamps_without_creating_files(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    for timestamp in ["bad", "202413010000", "202402300000"] {
        dir.cmd()
            .args(["-t", timestamp, "new"])
            .assert()
            .code(2)
            .stdout("")
            .stderr(predicate::str::contains("Invalid timestamp format"));
        dir.child("new").assert(predicate::path::missing());
    }
    Ok(())
}

#[cli_test]
fn reports_creation_path_errors(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("file").write_str("keep me")?;
    for path in ["missing/child", "file/child"] {
        dir.cmd()
            .arg(path)
            .assert()
            .failure()
            .stdout("")
            .stderr(predicate::str::contains(format!(
                "failed to create file {path}"
            )));
    }
    dir.child("file").assert("keep me");
    dir.child("missing").assert(predicate::path::missing());
    Ok(())
}

#[cli_test]
fn requires_file_operand(cx: &TestContext) {
    cx.assert_error(
        std::iter::empty::<&str>(),
        2,
        "required arguments were not provided",
    );
}

#[cfg(unix)]
#[cli_test]
fn follows_symlinks_without_erasing_contents(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("target").write_str("preserve target")?;
    std::os::unix::fs::symlink("target", dir.child("link").path())?;
    dir.cmd()
        .args(["-t", "20000101000007", "link"])
        .assert()
        .code(0)
        .stdout("")
        .stderr("");
    dir.child("target").assert("preserve target");
    assert_modified(dir.child("target").path(), 946_684_807)
}
