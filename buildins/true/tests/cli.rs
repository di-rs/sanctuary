use cli_testing::{Command, TestContext, cli_test};
use predicates::prelude::*;

fn assert_silent_status(cmd: &mut Command, status: i32) {
    cmd.assert()
        .stdout(predicate::str::is_empty())
        .stderr(predicate::str::is_empty())
        .code(status);
}

#[cli_test]
fn true_ignores_arguments(cx: &TestContext) {
    assert_silent_status(cx.cmd().args(["--help", "ignored"]), 0);
}

#[test]
fn exports_public_cli_schema_without_application_side_effects()
-> std::result::Result<(), Box<dyn std::error::Error>> {
    let value =
        cli_testing::assert_cli_schema(cli_testing::cargo_bin_cmd!(), env!("CARGO_PKG_NAME"))?;
    if value["command"]["args"] != serde_json::json!([])
        || value["command"]["subcommands"] != serde_json::json!([])
    {
        return Err("utility must have an empty interface".into());
    }
    cli_testing::cargo_bin_cmd!()
        .env_remove("SANCTUARY_CLI_SCHEMA")
        .arg("--help")
        .assert()
        .code(0)
        .stdout("")
        .stderr("");
    cli_testing::cargo_bin_cmd!()
        .env("SANCTUARY_CLI_SCHEMA", "1")
        .args(["--help", "ignored"])
        .assert()
        .code(0)
        .stdout("")
        .stderr("");
    Ok(())
}

cli_testing::readme_example!(0, "");
