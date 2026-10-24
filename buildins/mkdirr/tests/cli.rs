use assert_fs::prelude::*;
use cli_testing::{Context, TestContext, cli_test, test_case};
use predicates::prelude::*;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cli_test]
fn usage(cx: &TestContext) {
    for flag in ["-h", "--help"] {
        cx.command()
            .arg(flag)
            .assert()
            .success()
            .stdout(predicate::str::contains("Usage"))
            .stderr("");
    }
}

#[test_case("creates_single_directory")]
fn creates_single_directory(cx: &mut Context) -> cli_testing::Result<()> {
    cx.workspace()?;
    cx.run()?;
    cx.workspace()?
        .child("new")
        .assert(predicate::path::is_dir());
    Ok(())
}

#[cli_test]
fn creates_multiple_directories(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.command()
        .args(["one", "two", "three"])
        .assert()
        .success()
        .stdout("")
        .stderr("");
    for name in ["one", "two", "three"] {
        dir.child(name).assert(predicate::path::is_dir());
    }
    Ok(())
}

#[cli_test]
fn creates_nested_directories_by_default(cx: &TestContext) -> Result<()> {
    // mkdirr currently defaults parent creation to true, unlike standard mkdir.
    let dir = cx.workspace()?;
    dir.command()
        .arg("one/two/three")
        .assert()
        .success()
        .stdout("")
        .stderr("");
    dir.child("one/two/three").assert(predicate::path::is_dir());
    Ok(())
}

#[cli_test]
fn creates_nested_directories_with_p(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.command()
        .args(["-p", "one/two/three"])
        .assert()
        .success()
        .stdout("")
        .stderr("");
    dir.child("one/two/three").assert(predicate::path::is_dir());
    Ok(())
}

#[cli_test]
fn p_accepts_existing_directory(cx: &TestContext) -> Result<()> {
    // Regression: parent creation should tolerate a directory already present.
    let dir = cx.workspace()?;
    dir.child("existing").create_dir_all()?;
    dir.child("existing/contents").write_str("keep me")?;
    dir.command()
        .args(["-p", "existing"])
        .assert()
        .success()
        .stdout("")
        .stderr("");
    dir.child("existing/contents").assert("keep me");
    Ok(())
}

#[cli_test]
fn rejects_existing_file(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("existing").write_str("keep me")?;
    dir.command()
        .arg("existing")
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("existing"));
    dir.child("existing").assert("keep me");
    Ok(())
}

#[cli_test]
fn rejects_file_as_parent(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("file").write_str("keep me")?;
    dir.command()
        .arg("file/child")
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("file/child"));
    dir.child("file").assert("keep me");
    Ok(())
}

#[cli_test]
fn requires_directory_operand(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.command()
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::is_empty().not());
    Ok(())
}

#[cli_test]
fn rich_error_is_persisted_with_failing_completion(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    let logs = cx.workspace()?;
    dir.child("parent-file").write_str("keep me")?;
    dir.command()
        .env("SANCTUARY_LOG_DIR", logs.path())
        .env("SANCTUARY_LOG_LEVEL", "info")
        .env("SANCTUARY_LOG_STDERR", "off")
        .arg("parent-file/child")
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicate::str::contains("parent-file/child"));
    let mut records: Vec<serde_json::Value> = Vec::new();
    for entry in std::fs::read_dir(logs.path())? {
        let path = entry?.path();
        if path
            .file_name()
            .is_some_and(|name| name.to_string_lossy().starts_with("mkdirr_"))
            && path
                .extension()
                .is_some_and(|extension| extension == "jsonl")
        {
            for line in std::fs::read_to_string(path)?.lines() {
                records.push(serde_json::from_str(line)?);
            }
        }
    }
    if !(records.iter().any(|record| {
        record["kv"]["event"] == "error"
            && record["text"]
                .as_str()
                .is_some_and(|message| message.contains("parent-file/child"))
    })) {
        return Err("missing rich error record".into());
    }
    if !(records.iter().any(|record| {
        record["kv"]["event"] == "command_finished" && record["kv"]["exit_code"] == 1
    })) {
        return Err("missing failing completion".into());
    }
    Ok(())
}
