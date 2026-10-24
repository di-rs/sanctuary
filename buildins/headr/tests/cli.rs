use assert_fs::{NamedTempFile, fixture::FileTouch};
use cli_testing::{TestContext, cli_test};

use predicates::prelude::*;
use std::{fs, os::unix::fs::PermissionsExt};

const EMPTY: &str = "./tests/inputs/empty.txt";

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cli_test]
fn usage(cx: &TestContext) {
    for flag in &["-h", "--help"] {
        cx.cmd()
            .arg(flag)
            .assert()
            .success()
            .stderr("")
            .stdout(predicate::str::contains("Usage"));
    }
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
    let bad = bad.path().display().to_string();
    let expected = format!("{bad}: .* [(]os error 13[)]");
    cx.cmd()
        .args([EMPTY, &bad])
        .assert()
        .code(1)
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[cli_test]
fn dies_bad_bytes(cx: &TestContext) {
    let bad = "ddsdsasad";
    let expected = format!(
        "invalid value '{bad}' for \
        '--bytes <BYTES>': invalid digit found in string"
    );
    cx.cmd()
        .args(["-c", bad, EMPTY])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[cli_test]
fn dies_bad_lines(cx: &TestContext) {
    let bad = "ddsdsasad";
    let expected = format!(
        "invalid value '{bad}' for \
        '--lines <LINES>': invalid digit found in string"
    );
    cx.cmd()
        .args(["-n", bad, EMPTY])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[cli_test]
fn dies_bytes_and_lines(cx: &TestContext) {
    let expected = "the argument '--lines <LINES>' cannot be \
               used with '--bytes <BYTES>'";
    cx.cmd()
        .args(["-n", "1", "-c", "2"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[cli_test]
fn rejects_zero_counts_and_unknown_flag(cx: &TestContext) {
    for args in [["-n", "0"], ["-c", "0"], ["--unknown", "1"]] {
        cx.cmd()
            .args(args)
            .assert()
            .failure()
            .stdout("")
            .stderr(predicate::str::contains("error:"));
    }
}

#[cli_test]
fn explicit_stdin_preserves_line_endings_and_unterminated_line(cx: &TestContext) {
    for (count, expected) in [("1", "é\r\n"), ("2", "é\r\n世界"), ("9", "é\r\n世界")] {
        cx.cmd()
            .args(["-n", count, "-"])
            .write_stdin("é\r\n世界")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn stdin_byte_limit_handles_utf8_boundaries(cx: &TestContext) {
    for (count, expected) in [("1", "�"), ("2", "é"), ("3", "é�"), ("99", "é界")] {
        cx.cmd()
            .args(["-c", count])
            .write_stdin("é界")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn empty_stdin_in_line_and_byte_modes(cx: &TestContext) {
    for mode in ["-n", "-c"] {
        cx.cmd()
            .args([mode, "1"])
            .write_stdin("")
            .assert()
            .success()
            .stdout("")
            .stderr("");
    }
}

// --------------------------------------------------

#[cli_test]
fn missing_operand_returns_failure(cx: &TestContext) {
    cx.cmd()
        .args(["/sanctuary-audit-missing/path"])
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicates::str::contains("/sanctuary-audit-missing/path"));
}
