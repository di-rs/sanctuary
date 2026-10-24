use cli_testing::{TestContext, cli_test};
use predicates::prelude::*;
use rand::RngExt;
use rand::distr::Alphanumeric;
use std::fs;

const CSV: &str = "tests/inputs/movies1.csv";
const TSV: &str = "tests/inputs/movies1.tsv";

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn random_string() -> String {
    rand::rng()
        .sample_iter(&Alphanumeric)
        .take(7)
        .map(char::from)
        .collect()
}

fn gen_bad_file() -> String {
    loop {
        let filename = random_string();
        if fs::metadata(&filename).is_err() {
            return filename;
        }
    }
}

#[cli_test]
fn skips_bad_file(cx: &TestContext) -> Result<()> {
    let bad = gen_bad_file();
    let expected = format!("{bad}: .* [(]os error 2[)]");
    cx.cmd()
        .args(["-f", "1", CSV, &bad, TSV])
        .assert()
        .code(1)
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[cli_test]
fn stdin_chars_keep_requested_order_and_repetitions(cx: &TestContext) {
    cx.cmd()
        .args(["-c", "3,1-2,1,9"])
        .write_stdin("é界x\n\n猫")
        .assert()
        .success()
        .stdout("xé界é\n\n猫猫\n")
        .stderr("");
}

#[cli_test]
fn stdin_bytes_use_lossy_utf8_at_split_boundaries(cx: &TestContext) {
    for (positions, expected) in [("1", "�\n"), ("1-2", "é\n"), ("9", "\n")] {
        cx.cmd()
            .args(["-b", positions, "-"])
            .write_stdin("éx")
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn stdin_fields_parse_quoted_delimiters_and_empty_fields(cx: &TestContext) {
    cx.cmd()
        .args(["-d", ",", "-f", "2,1,3"])
        .write_stdin("\"a,b\",,c\n\"é\n界\",x,y")
        .assert()
        .success()
        .stdout(",\"a,b\",c\nx,\"é\n界\",y\n")
        .stderr("");
}

#[cli_test]
fn empty_stdin_in_each_mode(cx: &TestContext) {
    for mode in ["-f", "-b", "-c"] {
        cx.cmd()
            .args([mode, "1"])
            .write_stdin("")
            .assert()
            .success()
            .stdout("")
            .stderr("");
    }
}

#[cli_test]
fn missing_operand_returns_failure(cx: &TestContext) {
    cx.cmd()
        .args(["-b", "1", "/sanctuary-audit-missing/path"])
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicates::str::contains("/sanctuary-audit-missing/path"));
}

#[cli_testing::test_case("tsv_b1_8")]
fn tsv_b1_8(cx: &mut cli_testing::Context) -> cli_testing::Result<()> {
    // The reference emits raw bytes; cutr replaces incomplete UTF-8 sequences.
    cx.map_expected_stdout(|bytes| String::from_utf8_lossy(bytes).into_owned().into_bytes())?;
    Ok(())
}
