use cli_testing::cargo_bin_cmd;
use predicates::prelude::*;

const EMPTY: &str = "tests/inputs/empty.txt";
const FILE1: &str = "tests/inputs/file1.txt";
const BLANK: &str = "tests/inputs/blank.txt";

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

fn gen_bad_file() -> String {
    "tests/file/doesnt/exist".to_owned()
}

#[test]
fn dies_no_args() {
    cargo_bin_cmd!()
        .assert()
        .failure()
        .stderr(predicate::str::contains("Usage"));
}

#[test]
fn dies_bad_file1() -> Result<()> {
    let bad = gen_bad_file();
    let expected = format!("{bad}: .* [(]os error 2[)]");
    cargo_bin_cmd!()
        .args([&bad, FILE1])
        .assert()
        .failure()
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[test]
fn dies_bad_file2() -> Result<()> {
    let bad = gen_bad_file();
    let expected = format!("{bad}: .* [(]os error 2[)]");
    cargo_bin_cmd!()
        .args([FILE1, &bad])
        .assert()
        .failure()
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[test]
fn dies_both_stdin() {
    let expected = "Error: both input files cannot be STDIN (`-`)";
    cargo_bin_cmd!()
        .args(["-", "-"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[test]
fn rejects_unknown_flag() {
    cargo_bin_cmd!()
        .args(["--unknown", EMPTY, EMPTY])
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("--unknown"));
}

#[test]
fn stdin_on_either_side_emits_visible_columns() {
    for (args, expected) in [
        (["-", FILE1], "\t\ta\n\tb\nbb\n\tc\n\td\nz\n"),
        ([FILE1, "-"], "\t\ta\nb\n\tbb\nc\nd\n\tz\n"),
    ] {
        cargo_bin_cmd!()
            .args(args)
            .write_stdin("a\nbb\nz")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[test]
fn custom_delimiter_handles_blank_common_line() {
    for (delimiter, expected) in [("::", "::::\nα\n"), ("", "\nα\n")] {
        cargo_bin_cmd!()
            .args(["-d", delimiter, "-", BLANK])
            .write_stdin("\nα")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[test]
fn insensitive_stdin_matches_common_column() {
    cargo_bin_cmd!()
        .args(["-i", "-12", "-", FILE1])
        .write_stdin("A\nC")
        .assert()
        .success()
        .stdout("a\nc\n")
        .stderr("");
}

// insensitive

#[test]
fn malformed_input_is_not_eof() -> Result<()> {
    let dir = assert_fs::TempDir::new()?;
    let empty = dir.path().join("empty");
    std::fs::write(&empty, b"")?;
    cli_testing::cargo_bin_cmd!()
        .arg("-")
        .arg(empty)
        .write_stdin(b"a\n\xff\nz\n")
        .assert()
        .code(65)
        .stdout("a\n")
        .stderr(predicates::str::contains("Error:"));
    Ok(())
}
