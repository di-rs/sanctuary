use assert_fs::{NamedTempFile, fixture::FileTouch};
use cli_testing::{TestContext, cli_test};

use predicates::prelude::*;
use std::{fs, os::unix::fs::PermissionsExt};

const EMPTY: &str = "tests/inputs/empty.txt";

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
    let expected = format!("{}: .* [(]os error 13[)]", bad.display());
    cx.cmd()
        .arg(bad.path())
        .assert()
        .code(1)
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[cli_test]
fn dies_chars_and_bytes(cx: &TestContext) {
    cx.assert_error(
        ["-m", "-c"],
        2,
        "the argument '--chars' cannot be used with '--bytes'",
    );
}

#[cli_test]
fn rejects_unknown_flag(cx: &TestContext) {
    cx.assert_error(["--unknown"], 2, "--unknown");
}

#[cli_test]
fn empty_stdin_has_zero_default_counts(cx: &TestContext) {
    cx.cmd()
        .write_stdin("")
        .assert()
        .success()
        .stdout("       0       0       0\n")
        .stderr("");
}

#[cli_test]
fn unicode_whitespace_separates_words_and_bytes_differ_from_chars(cx: &TestContext) {
    for (flag, expected) in [
        ("-c", "      12\n"),
        ("-m", "       6\n"),
        ("-w", "       3\n"),
        ("-lwm", "       1       3       6\n"),
    ] {
        cx.cmd()
            .args([flag, "-"])
            .write_stdin("é\u{2003}猫\tβ\n")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn unterminated_stdin_counts_final_record(cx: &TestContext) {
    cx.cmd()
        .write_stdin("é x")
        .assert()
        .success()
        .stdout("       1       2       4\n")
        .stderr("");
}

#[cli_test]
fn mixed_stdin_and_file_totals_use_selected_counts(cx: &TestContext) {
    cx.cmd()
        .args(["-wm", "-", EMPTY])
        .write_stdin("é x")
        .assert()
        .success()
        .stdout(format!(
            "       2       3\n       0       0 {EMPTY}\n       2       3 total\n"
        ))
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
