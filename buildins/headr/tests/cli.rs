use assert_fs::{NamedTempFile, fixture::FileTouch};
use cli_testing::{TestContext, cli_test};

use predicates::prelude::*;
use std::{fs, os::unix::fs::PermissionsExt};

const EMPTY: &str = "./tests/inputs/empty.txt";

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

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

#[test]
fn exports_public_cli_schema_without_application_side_effects()
-> std::result::Result<(), Box<dyn std::error::Error>> {
    let value =
        cli_testing::assert_cli_schema(cli_testing::cargo_bin_cmd!(), env!("CARGO_PKG_NAME"))?;
    let args = value["command"]["args"]
        .as_array()
        .ok_or("missing arguments")?;
    let lines = args
        .iter()
        .find(|arg| arg["long"] == "lines")
        .ok_or("missing lines flag")?;
    if lines["short"] != "n"
        || lines["default_values"] != serde_json::json!(["10"])
        || lines["num_args"] != serde_json::json!({"min":1,"max":1})
    {
        return Err("incorrect lines metadata".into());
    }
    cli_testing::cargo_bin_cmd!()
        .env("SANCTUARY_CLI_SCHEMA", "1")
        .args(["-n", "1"])
        .write_stdin("one\ntwo\n")
        .assert()
        .code(0)
        .stdout("one\n")
        .stderr("");
    Ok(())
}
