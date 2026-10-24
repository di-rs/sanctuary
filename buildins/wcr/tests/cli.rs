use assert_fs::{NamedTempFile, fixture::FileTouch};
use cli_testing::cargo_bin_cmd;
use predicates::prelude::*;
use std::{fs, os::unix::fs::PermissionsExt};

const EMPTY: &str = "tests/inputs/empty.txt";

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
    let expected = format!("{}: .* [(]os error 13[)]", bad.display());
    cargo_bin_cmd!()
        .arg(bad.path())
        .assert()
        .code(1)
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[test]
fn dies_chars_and_bytes() {
    cargo_bin_cmd!()
        .args(["-m", "-c"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "the argument '--chars' cannot be used with '--bytes'",
        ));
}

#[test]
fn rejects_unknown_flag() {
    cargo_bin_cmd!()
        .arg("--unknown")
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("--unknown"));
}

#[test]
fn empty_stdin_has_zero_default_counts() {
    cargo_bin_cmd!()
        .write_stdin("")
        .assert()
        .success()
        .stdout("       0       0       0\n")
        .stderr("");
}

#[test]
fn unicode_whitespace_separates_words_and_bytes_differ_from_chars() {
    for (flag, expected) in [
        ("-c", "      12\n"),
        ("-m", "       6\n"),
        ("-w", "       3\n"),
        ("-lwm", "       1       3       6\n"),
    ] {
        cargo_bin_cmd!()
            .args([flag, "-"])
            .write_stdin("é\u{2003}猫\tβ\n")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[test]
fn unterminated_stdin_counts_final_record() {
    cargo_bin_cmd!()
        .write_stdin("é x")
        .assert()
        .success()
        .stdout("       1       2       4\n")
        .stderr("");
}

#[test]
fn mixed_stdin_and_file_totals_use_selected_counts() {
    cargo_bin_cmd!()
        .args(["-wm", "-", EMPTY])
        .write_stdin("é x")
        .assert()
        .success()
        .stdout(format!(
            "       2       3\n       0       0 {EMPTY}\n       2       3 total\n"
        ))
        .stderr("");
}

#[test]
fn missing_operand_returns_failure() {
    cli_testing::cargo_bin_cmd!()
        .args(["/sanctuary-audit-missing/path"])
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicates::str::contains("/sanctuary-audit-missing/path"));
}
