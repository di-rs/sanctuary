use cli_testing::{TestContext, cli_test};
use predicates::prelude::*;

const EMPTY: &str = "tests/inputs/empty.txt";
const FILE1: &str = "tests/inputs/file1.txt";
const BLANK: &str = "tests/inputs/blank.txt";

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cli_test]
fn usage(cx: &TestContext) {
    for flag in &["-h", "--help"] {
        cx.command()
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

#[cli_test]
fn dies_no_args(cx: &TestContext) {
    cx.command()
        .assert()
        .failure()
        .stderr(predicate::str::contains("Usage"));
}

#[cli_test]
fn dies_bad_file1(cx: &TestContext) -> Result<()> {
    let bad = gen_bad_file();
    let expected = format!("{bad}: .* [(]os error 2[)]");
    cx.command()
        .args([&bad, FILE1])
        .assert()
        .failure()
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[cli_test]
fn dies_bad_file2(cx: &TestContext) -> Result<()> {
    let bad = gen_bad_file();
    let expected = format!("{bad}: .* [(]os error 2[)]");
    cx.command()
        .args([FILE1, &bad])
        .assert()
        .failure()
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[cli_test]
fn dies_both_stdin(cx: &TestContext) {
    let expected = "Error: both input files cannot be STDIN (`-`)";
    cx.command()
        .args(["-", "-"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[cli_test]
fn rejects_unknown_flag(cx: &TestContext) {
    cx.command()
        .args(["--unknown", EMPTY, EMPTY])
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("--unknown"));
}

#[cli_test]
fn stdin_on_either_side_emits_visible_columns(cx: &TestContext) {
    for (args, expected) in [
        (["-", FILE1], "\t\ta\n\tb\nbb\n\tc\n\td\nz\n"),
        ([FILE1, "-"], "\t\ta\nb\n\tbb\nc\nd\n\tz\n"),
    ] {
        cx.command()
            .args(args)
            .write_stdin("a\nbb\nz")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn custom_delimiter_handles_blank_common_line(cx: &TestContext) {
    for (delimiter, expected) in [("::", "::::\nα\n"), ("", "\nα\n")] {
        cx.command()
            .args(["-d", delimiter, "-", BLANK])
            .write_stdin("\nα")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn insensitive_stdin_matches_common_column(cx: &TestContext) {
    cx.command()
        .args(["-i", "-12", "-", FILE1])
        .write_stdin("A\nC")
        .assert()
        .success()
        .stdout("a\nc\n")
        .stderr("");
}

// insensitive

#[cli_test]
fn malformed_input_is_not_eof(cx: &TestContext) -> Result<()> {
    let dir = assert_fs::TempDir::new()?;
    let empty = dir.path().join("empty");
    std::fs::write(&empty, b"")?;
    cx.command()
        .arg("-")
        .arg(empty)
        .write_stdin(b"a\n\xff\nz\n")
        .assert()
        .code(65)
        .stdout("a\n")
        .stderr(predicates::str::contains("Error:"));
    Ok(())
}
