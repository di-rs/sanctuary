use assert_fs::{NamedTempFile, fixture::FileTouch};
use cli_testing::{TestContext, cli_test};

use predicates::prelude::*;
use std::{fs, os::unix::fs::PermissionsExt};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cli_test]
fn usage(cx: &TestContext) {
    cx.assert_help();
}

fn gen_bad_file() -> Result<NamedTempFile> {
    let file = assert_fs::NamedTempFile::new("no-permissions")?;
    file.touch()?;
    fs::set_permissions(file.path(), PermissionsExt::from_mode(0o000))?;
    Ok(file)
}

#[cli_test]
fn skip_bad_file(cx: &TestContext) -> Result<()> {
    let bad = gen_bad_file()?;
    let expected = format!("{}: .* [(]os error 13[)]", bad.path().display());
    cx.cmd()
        .arg(bad.path())
        .assert()
        .code(1)
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[cli_test]
fn rejects_unknown_and_conflicting_flags(cx: &TestContext) {
    for args in [&["--unknown"][..], &["-n", "-b"]] {
        cx.assert_error(args, 2, "error:");
    }
}

#[cli_test]
fn default_stdin_preserves_empty_and_unterminated_unicode(cx: &TestContext) {
    for input in ["", "é\r\n世界"] {
        cx.cmd()
            .write_stdin(input)
            .assert()
            .success()
            .stdout(input)
            .stderr("");
    }
}

#[cli_test]
fn number_nonblank_keeps_whitespace_only_lines(cx: &TestContext) {
    cx.cmd()
        .arg("--number-nonblank")
        .write_stdin("\n \n\t\né")
        .assert()
        .success()
        .stdout("\n     1\t \n     2\t\t\n     3\té")
        .stderr("");
}

#[cli_test]
fn squeeze_and_number_preserve_whitespace_lines(cx: &TestContext) {
    cx.cmd()
        .args(["-s", "-n"])
        .write_stdin("\n\n \n\n\né")
        .assert()
        .success()
        .stdout("     1\t\n     2\t \n     3\t\n     4\té")
        .stderr("");
}

#[cli_test]
fn missing_operand_returns_failure(cx: &TestContext) {
    cx.cmd()
        .args(["/sanctuary-audit-missing/path"])
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicates::str::contains("/sanctuary-audit-missing/path"));
}
