use assert_fs::prelude::*;
use cli_testing::{TestContext, Workspace, cli_test};
use predicates::prelude::*;
use pretty_assertions::assert_eq;
use std::{fs, os::unix::fs::PermissionsExt};

const HIDDEN: &str = "tests/inputs/.hidden";
const EMPTY: &str = "tests/inputs/empty.txt";
const BUSTLE: &str = "tests/inputs/bustle.txt";
const FOX: &str = "tests/inputs/fox.txt";

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn fixture_tree(cx: &TestContext) -> Result<Workspace> {
    let dir = cx.workspace()?;
    let nested = dir.child("tests/inputs/dir");
    nested.create_dir_all()?;
    fs::set_permissions(nested.path(), fs::Permissions::from_mode(0o755))?;
    for (source, mode) in [
        (EMPTY, 0o644),
        (BUSTLE, 0o644),
        (FOX, 0o600),
        (HIDDEN, 0o644),
        ("tests/inputs/dir/spiders.txt", 0o644),
        ("tests/inputs/dir/.gitkeep", 0o644),
    ] {
        let destination = dir.child(source);
        fs::copy(source, destination.path())?;
        fs::set_permissions(destination.path(), fs::Permissions::from_mode(mode))?;
    }
    Ok(dir)
}

#[cli_test]
fn usage(cx: &TestContext) {
    cx.assert_help();
}

fn gen_bad_file() -> String {
    "tests/file/doesnt/exist".to_owned()
}

#[cli_test]
fn bad_file(cx: &TestContext) {
    let bad = gen_bad_file();
    let expected = format!("{bad}: No such file or directory (os error 2)");
    cx.cmd()
        .arg(&bad)
        .assert()
        .code(1)
        .stderr(predicate::str::contains(expected));
}

#[cli_test]
fn no_args(cx: &TestContext) {
    cx.cmd()
        .assert()
        .success()
        .stdout(predicate::str::contains("Cargo.toml"));
}

fn run_long(cx: &TestContext, filename: &str, permissions: &str, size: &str) -> Result<()> {
    let dir = fixture_tree(cx)?;
    let cmd = dir
        .cmd()
        .args(["--long", filename])
        .assert()
        .success()
        .stderr("");
    let stdout = String::from_utf8(cmd.get_output().stdout.clone())?;
    let parts: Vec<_> = stdout.split_whitespace().collect();
    assert_eq!(parts.first().copied(), Some(permissions));
    assert_eq!(parts.get(4).copied(), Some(size));
    assert_eq!(parts.last().copied(), Some(filename));
    Ok(())
}

#[cli_test]
fn empty_long(cx: &TestContext) -> Result<()> {
    run_long(cx, EMPTY, "-rw-r--r--", "0")
}

#[cli_test]
fn bustle_long(cx: &TestContext) -> Result<()> {
    run_long(cx, BUSTLE, "-rw-r--r--", "193")
}

#[cli_test]
fn fox_long(cx: &TestContext) -> Result<()> {
    run_long(cx, FOX, "-rw-------", "45")
}

#[cli_test]
fn hidden_long(cx: &TestContext) -> Result<()> {
    run_long(cx, HIDDEN, "-rw-r--r--", "0")
}

fn dir_short(cx: &TestContext, args: &[&str], expected: &[&str]) -> Result<()> {
    let cmd = cx.cmd().args(args).assert().success();
    let stdout = String::from_utf8(cmd.get_output().stdout.clone())?;
    let lines: Vec<&str> = stdout.split('\n').filter(|s| !s.is_empty()).collect();
    assert_eq!(lines.len(), expected.len());
    for filename in expected {
        assert_eq!(true, lines.contains(filename));
    }
    Ok(())
}

#[cli_test]
fn dir1(cx: &TestContext) -> Result<()> {
    dir_short(
        cx,
        &["tests/inputs"],
        &[
            "tests/inputs/empty.txt",
            "tests/inputs/bustle.txt",
            "tests/inputs/fox.txt",
            "tests/inputs/dir",
        ],
    )
}

#[cli_test]
fn dir1_all(cx: &TestContext) -> Result<()> {
    dir_short(
        cx,
        &["tests/inputs", "--all"],
        &[
            "tests/inputs/empty.txt",
            "tests/inputs/bustle.txt",
            "tests/inputs/fox.txt",
            "tests/inputs/.hidden",
            "tests/inputs/dir",
        ],
    )
}

#[cli_test]
fn dir2(cx: &TestContext) -> Result<()> {
    dir_short(cx, &["tests/inputs/dir"], &["tests/inputs/dir/spiders.txt"])
}

#[cli_test]
fn dir2_all(cx: &TestContext) -> Result<()> {
    dir_short(
        cx,
        &["-a", "tests/inputs/dir"],
        &["tests/inputs/dir/spiders.txt", "tests/inputs/dir/.gitkeep"],
    )
}

fn dir_long(cx: &TestContext, args: &[&str], expected: &[(&str, &str, &str)]) -> Result<()> {
    let dir = fixture_tree(cx)?;
    let cmd = dir.cmd().args(args).assert().success().stderr("");
    let stdout = String::from_utf8(cmd.get_output().stdout.clone())?;
    let lines: Vec<&str> = stdout.split('\n').filter(|s| !s.is_empty()).collect();
    assert_eq!(lines.len(), expected.len());

    let mut check = vec![];
    for line in lines {
        let parts: Vec<&str> = line.split_whitespace().collect();
        let path = parts.last().copied().ok_or("missing path in listing")?;
        let permissions = parts
            .first()
            .copied()
            .ok_or("missing permissions in listing")?;
        let size = match permissions.chars().next() {
            Some('d') => "",
            _ => parts.get(4).copied().ok_or("missing size in listing")?,
        };
        check.push((path, permissions, size));
    }

    for entry in expected {
        assert_eq!(true, check.contains(entry));
    }

    Ok(())
}

#[cli_test]
fn dir1_long(cx: &TestContext) -> Result<()> {
    dir_long(
        cx,
        &["-l", "tests/inputs"],
        &[
            ("tests/inputs/empty.txt", "-rw-r--r--", "0"),
            ("tests/inputs/bustle.txt", "-rw-r--r--", "193"),
            ("tests/inputs/fox.txt", "-rw-------", "45"),
            ("tests/inputs/dir", "drwxr-xr-x", ""),
        ],
    )
}

#[cli_test]
fn dir1_long_all(cx: &TestContext) -> Result<()> {
    dir_long(
        cx,
        &["-la", "tests/inputs"],
        &[
            ("tests/inputs/empty.txt", "-rw-r--r--", "0"),
            ("tests/inputs/bustle.txt", "-rw-r--r--", "193"),
            ("tests/inputs/fox.txt", "-rw-------", "45"),
            ("tests/inputs/dir", "drwxr-xr-x", ""),
            ("tests/inputs/.hidden", "-rw-r--r--", "0"),
        ],
    )
}

#[cli_test]
fn dir2_long(cx: &TestContext) -> Result<()> {
    dir_long(
        cx,
        &["--long", "tests/inputs/dir"],
        &[("tests/inputs/dir/spiders.txt", "-rw-r--r--", "45")],
    )
}

#[cli_test]
fn dir2_long_all(cx: &TestContext) -> Result<()> {
    dir_long(
        cx,
        &["tests/inputs/dir", "--long", "--all"],
        &[
            ("tests/inputs/dir/spiders.txt", "-rw-r--r--", "45"),
            ("tests/inputs/dir/.gitkeep", "-rw-r--r--", "0"),
        ],
    )
}

fn check_listing(dir: &Workspace, args: &[&str], expected: &[&str]) -> Result<()> {
    let cmd = dir.cmd().args(args).assert().success().stderr("");
    let stdout = String::from_utf8(cmd.get_output().stdout.clone())?;
    let mut lines: Vec<_> = stdout.lines().collect();
    lines.sort_unstable();
    let mut expected = expected.to_vec();
    expected.sort_unstable();
    assert_eq!(lines, expected);
    Ok(())
}

#[cli_test]
fn empty_directory(cx: &TestContext) -> Result<()> {
    check_listing(&cx.workspace()?, &["."], &[])
}

#[cli_test]
fn default_path_hides_dotfiles(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("visible").touch()?;
    dir.child(".hidden").touch()?;
    check_listing(&dir, &[], &["./visible"])
}

#[cli_test]
fn hidden_only_directory_requires_all(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child(".hidden").touch()?;
    check_listing(&dir, &["."], &[])?;
    check_listing(&dir, &["--all", "."], &["./.hidden"])
}

#[cli_test]
fn explicit_hidden_file_does_not_require_all(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child(".hidden").touch()?;
    check_listing(&dir, &[".hidden"], &[".hidden"])
}

#[cli_test]
fn multiple_files_and_directory_are_not_recursive(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("folder/nested").create_dir_all()?;
    dir.child("folder/nested/not-listed").touch()?;
    dir.child("folder/child").touch()?;
    dir.child("first").touch()?;
    dir.child("last").touch()?;
    check_listing(
        &dir,
        &["first", "folder", "last"],
        &["first", "folder/child", "folder/nested", "last"],
    )
}

#[cli_test]
fn filename_with_spaces_is_preserved(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    let file = dir.child("two words.txt");
    file.write_str("hello")?;
    fs::set_permissions(file.path(), fs::Permissions::from_mode(0o640))?;
    check_listing(&dir, &["two words.txt"], &["two words.txt"])?;
    cx.cmd()
        .current_dir(dir.path())
        .args(["-l", "two words.txt"])
        .assert()
        .success()
        .stderr("")
        .stdout(predicate::str::starts_with("-rw-r-----"))
        .stdout(predicate::str::ends_with(" two words.txt\n\n"));
    Ok(())
}

#[cli_test]
fn missing_path_does_not_hide_valid_files(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("present").touch()?;
    cx.cmd()
        .current_dir(dir.path())
        .args(["missing", "present"])
        .assert()
        .code(1)
        .stdout("present\n")
        .stderr(predicate::str::contains(
            "missing: No such file or directory",
        ));
    Ok(())
}

// These regressions catch missing persistence without changing terminal contracts.
#[cli_test]
fn handled_file_error_is_persisted_with_failure_completion(cx: &TestContext) -> Result<()> {
    let logs = cx.workspace()?;
    cx.cmd()
        .env("SANCTUARY_LOG_DIR", logs.path())
        .env("SANCTUARY_LOG_LEVEL", "info")
        .env("SANCTUARY_LOG_STDERR", "off")
        .arg("missing-log-test-input")
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicate::str::contains("missing-log-test-input:"));
    let records = read_log_records(&logs)?;
    if !(records.iter().any(|record| {
        record["level"] == "ERROR"
            && record["text"]
                .as_str()
                .is_some_and(|message| message.contains("missing-log-test-input"))
    })) {
        return Err("missing logged input error".into());
    }
    if !(records.iter().any(|record| {
        record["kv"]["event"] == "command_finished" && record["kv"]["exit_code"] == 1
    })) {
        return Err("missing failure completion".into());
    }
    Ok(())
}

#[cli_test]
fn invalid_argument_is_persisted_with_clap_status(cx: &TestContext) -> Result<()> {
    let logs = cx.workspace()?;
    cx.cmd()
        .env("SANCTUARY_LOG_DIR", logs.path())
        .env("SANCTUARY_LOG_LEVEL", "info")
        .env("SANCTUARY_LOG_STDERR", "off")
        .arg("--unknown")
        .assert()
        .code(2)
        .stdout("")
        .stderr(predicate::str::contains("--unknown"));
    let records = read_log_records(&logs)?;
    if !(records.iter().any(|record| {
        record["kv"]["event"] == "argument_error"
            && record["text"]
                .as_str()
                .is_some_and(|message| message.contains("--unknown"))
    })) {
        return Err("missing logged argument error".into());
    }
    if !(records.iter().any(|record| {
        record["kv"]["event"] == "command_finished" && record["kv"]["exit_code"] == 2
    })) {
        return Err("missing Clap failure completion".into());
    }
    Ok(())
}

fn read_log_records(logs: &Workspace) -> Result<Vec<serde_json::Value>> {
    let mut records = Vec::new();
    for entry in fs::read_dir(logs.path())? {
        let path = entry?.path();
        if path
            .file_name()
            .is_some_and(|name| name.to_string_lossy().starts_with("lsr_"))
            && path
                .extension()
                .is_some_and(|extension| extension == "jsonl")
        {
            for line in fs::read_to_string(path)?.lines() {
                records.push(serde_json::from_str(line)?);
            }
        }
    }
    Ok(records)
}

#[cli_test]
fn missing_operand_returns_failure(cx: &TestContext) {
    cx.cmd()
        .args(["/sanctuary-audit-missing/path"])
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicates::str::contains("/sanctuary-audit-missing/path"));
}
