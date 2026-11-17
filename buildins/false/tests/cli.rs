use cli_testing::{TestContext, cli_test};
#[cli_test]
fn intentional_false_status_is_persisted_without_error(
    cx: &TestContext,
) -> Result<(), Box<dyn std::error::Error>> {
    let logs = assert_fs::TempDir::new()?;
    cx.cmd()
        .env("SANCTUARY_LOG_DIR", logs.path())
        .env("SANCTUARY_LOG_LEVEL", "info")
        .env("SANCTUARY_LOG_STDERR", "off")
        .assert()
        .code(1)
        .stdout("")
        .stderr("");
    let mut records: Vec<serde_json::Value> = Vec::new();
    for entry in std::fs::read_dir(logs.path())? {
        let path = entry?.path();
        if path
            .file_name()
            .is_some_and(|name| name.to_string_lossy().starts_with("false_"))
            && path
                .extension()
                .is_some_and(|extension| extension == "jsonl")
        {
            for line in std::fs::read_to_string(path)?.lines() {
                records.push(serde_json::from_str(line)?);
            }
        }
    }
    if !(records
        .iter()
        .any(|record| record["kv"]["event"] == "command_started"))
    {
        return Err("missing startup record".into());
    }
    if !(records.iter().any(|record| {
        record["kv"]["event"] == "command_finished" && record["kv"]["exit_code"] == 1
    })) {
        return Err("missing intentional status completion".into());
    }
    if records.iter().any(|record| record["level"] == "ERROR") {
        return Err("unexpected error event for intentional false status".into());
    }
    Ok(())
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
        .code(1)
        .stdout("")
        .stderr("");
    cli_testing::cargo_bin_cmd!()
        .env("SANCTUARY_CLI_SCHEMA", "1")
        .args(["--help", "ignored"])
        .assert()
        .code(1)
        .stdout("")
        .stderr("");
    Ok(())
}
