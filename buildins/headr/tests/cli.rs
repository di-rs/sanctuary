use assert_fs::{NamedTempFile, fixture::FileTouch};
use cli_testing::cargo_bin_cmd;
use predicates::prelude::*;
use std::{fs, os::unix::fs::PermissionsExt};

const EMPTY: &str = "./tests/inputs/empty.txt";

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[test]
fn usage() {
    for flag in &["-h", "--help"] {
        cargo_bin_cmd!()
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

#[test]
fn skip_bad_file() -> Result<()> {
    let bad = gen_bad_file()?;
    let bad = bad.path().display().to_string();
    let expected = format!("{bad}: .* [(]os error 13[)]");
    cargo_bin_cmd!()
        .args([EMPTY, &bad])
        .assert()
        .code(1)
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[test]
fn dies_bad_bytes() {
    let bad = "ddsdsasad";
    let expected = format!(
        "invalid value '{bad}' for \
        '--bytes <BYTES>': invalid digit found in string"
    );
    cargo_bin_cmd!()
        .args(["-c", bad, EMPTY])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[test]
fn dies_bad_lines() {
    let bad = "ddsdsasad";
    let expected = format!(
        "invalid value '{bad}' for \
        '--lines <LINES>': invalid digit found in string"
    );
    cargo_bin_cmd!()
        .args(["-n", bad, EMPTY])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[test]
fn dies_bytes_and_lines() {
    let expected = "the argument '--lines <LINES>' cannot be \
               used with '--bytes <BYTES>'";
    cargo_bin_cmd!()
        .args(["-n", "1", "-c", "2"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[test]
fn rejects_zero_counts_and_unknown_flag() {
    for args in [["-n", "0"], ["-c", "0"], ["--unknown", "1"]] {
        cargo_bin_cmd!()
            .args(args)
            .assert()
            .failure()
            .stdout("")
            .stderr(predicate::str::contains("error:"));
    }
}

#[test]
fn explicit_stdin_preserves_line_endings_and_unterminated_line() {
    for (count, expected) in [("1", "é\r\n"), ("2", "é\r\n世界"), ("9", "é\r\n世界")] {
        cargo_bin_cmd!()
            .args(["-n", count, "-"])
            .write_stdin("é\r\n世界")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[test]
fn stdin_byte_limit_handles_utf8_boundaries() {
    for (count, expected) in [("1", "�"), ("2", "é"), ("3", "é�"), ("99", "é界")] {
        cargo_bin_cmd!()
            .args(["-c", count])
            .write_stdin("é界")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[test]
fn empty_stdin_in_line_and_byte_modes() {
    for mode in ["-n", "-c"] {
        cargo_bin_cmd!()
            .args([mode, "1"])
            .write_stdin("")
            .assert()
            .success()
            .stdout("")
            .stderr("");
    }
}

// --------------------------------------------------

#[test]
fn missing_operand_returns_failure() {
    cli_testing::cargo_bin_cmd!()
        .args(["/sanctuary-audit-missing/path"])
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicates::str::contains("/sanctuary-audit-missing/path"));
}
