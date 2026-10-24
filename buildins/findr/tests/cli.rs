use cli_testing::{TestContext, Workspace, cli_test};
use predicates::prelude::*;
use pretty_assertions::assert_eq;
use std::{borrow::Cow, fs};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cli_test]
fn usage(cx: &TestContext) {
    for flag in &["-h", "--help"] {
        cx.cmd()
            .arg(flag)
            .assert()
            .success()
            .stdout(predicate::str::contains("Usage"));
    }
}

#[cli_test]
fn dies_bad_name(cx: &TestContext) {
    cx.cmd()
        .args(["--name", "*.csv"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("error: invalid value '*.csv'"));
}

#[cli_test]
fn dies_bad_type(cx: &TestContext) {
    let expected = "error: invalid value 'x' for '--type [<TYPE>...]'";
    cx.cmd()
        .args(["--type", "x"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[cfg(windows)]
fn format_file_name(expected_file: &str) -> Cow<str> {
    // Equivalent to: Cow::Owned(format!("{}.windows", expected_file))
    format!("{}.windows", expected_file).into()
}

#[cfg(not(windows))]
fn format_file_name(expected_file: &str) -> Cow<'_, str> {
    // Equivalent to: Cow::Borrowed(expected_file)
    expected_file.into()
}

fn run(cx: &TestContext, args: &[&str], expected_file: &str) -> Result<()> {
    let file = format_file_name(expected_file);
    let contents = String::from_utf8(cx.fixtures().read_expected(file.as_ref())?)?;
    let mut expected: Vec<&str> = contents.split('\n').filter(|s| !s.is_empty()).collect();
    expected.sort_unstable();

    // Directory traversal order is unspecified, so compare the explicit line multiset.
    let cmd = cx.cmd().args(args).assert().success().stderr("");
    let out = cmd.get_output();
    let stdout = String::from_utf8(out.stdout.clone())?;
    let mut lines: Vec<&str> = stdout.split('\n').filter(|s| !s.is_empty()).collect();
    lines.sort_unstable();

    assert_eq!(lines, expected);

    Ok(())
}

#[cli_test]
fn path1(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs"], "path1.txt")
}

#[cli_test]
fn path_a(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs/a"], "path_a.txt")
}

#[cli_test]
fn path_a_b(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs/a/b"], "path_a_b.txt")
}

#[cli_test]
fn path_d(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs/d"], "path_d.txt")
}

#[cli_test]
fn path_a_b_d(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs/a/b", "tests/inputs/d"],
        "path_a_b_d.txt",
    )
}

#[cli_test]
fn type_f(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs", "-t", "f"], "type_f.txt")
}

#[cli_test]
fn type_f_path_a(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs/a", "-t", "f"], "type_f_path_a.txt")
}

#[cli_test]
fn type_f_path_a_b(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs/a/b", "--type", "f"],
        "type_f_path_a_b.txt",
    )
}

#[cli_test]
fn type_f_path_d(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs/d", "--type", "f"], "type_f_path_d.txt")
}

#[cli_test]
fn type_f_path_a_b_d(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs/a/b", "tests/inputs/d", "--type", "f"],
        "type_f_path_a_b_d.txt",
    )
}

#[cli_test]
fn type_d(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs", "-t", "d"], "type_d.txt")
}

#[cli_test]
fn type_d_path_a(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs/a", "-t", "d"], "type_d_path_a.txt")
}

#[cli_test]
fn type_d_path_a_b(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs/a/b", "--type", "d"],
        "type_d_path_a_b.txt",
    )
}

#[cli_test]
fn type_d_path_d(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs/d", "--type", "d"], "type_d_path_d.txt")
}

#[cli_test]
fn type_d_path_a_b_d(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs/a/b", "tests/inputs/d", "--type", "d"],
        "type_d_path_a_b_d.txt",
    )
}

#[cli_test]
fn type_l(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs", "-t", "l"], "type_l.txt")
}

#[cli_test]
fn type_f_l(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs", "-t", "l", "f"], "type_f_l.txt")
}

#[cli_test]
fn name_csv(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs", "-n", ".*[.]csv"], "name_csv.txt")
}

#[cli_test]
fn name_csv_mp3(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs", "-n", ".*[.]csv", "-n", ".*[.]mp3"],
        "name_csv_mp3.txt",
    )
}

#[cli_test]
fn name_txt_path_a_d(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs/a", "tests/inputs/d", "--name", ".*.txt"],
        "name_txt_path_a_d.txt",
    )
}

#[cli_test]
fn name_a(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs", "-n", "a"], "name_a.txt")
}

#[cli_test]
fn type_f_name_a(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs", "-t", "f", "-n", "a"],
        "type_f_name_a.txt",
    )
}

#[cli_test]
fn type_d_name_a(cx: &TestContext) -> Result<()> {
    run(
        cx,
        &["tests/inputs", "--type", "d", "--name", "a"],
        "type_d_name_a.txt",
    )
}

#[cli_test]
fn path_g(cx: &TestContext) -> Result<()> {
    run(cx, &["tests/inputs/g.csv"], "path_g.txt")
}

#[cli_test]
#[cfg(not(windows))]
#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions fail the test; Result propagates fixture I/O errors."
)]
fn unreadable_dir(cx: &TestContext) -> Result<()> {
    use std::os::unix::fs::PermissionsExt;

    let dir = cx.workspace()?;
    let unreadable = dir.path().join("cant-touch-this");
    fs::create_dir(&unreadable)?;
    fs::set_permissions(&unreadable, fs::Permissions::from_mode(0o000))?;

    let cmd = cx.cmd().arg(dir.path()).assert();
    fs::set_permissions(&unreadable, fs::Permissions::from_mode(0o700))?;
    let cmd = cmd.code(1);

    let out = cmd.get_output();
    let stdout = String::from_utf8(out.stdout.clone())?;

    assert_eq!(stdout.lines().count(), 2);

    let stderr = String::from_utf8(out.stderr.clone())?;
    assert!(stderr.contains("cant-touch-this: Permission denied"));
    Ok(())
}

fn filter_tree(cx: &TestContext) -> Result<Workspace> {
    let dir = cx.workspace()?;
    fs::create_dir(dir.path().join("reports.txt"))?;
    fs::write(dir.path().join("reports.txt/inside.csv"), "")?;
    fs::write(dir.path().join("alpha.txt"), "")?;
    fs::write(dir.path().join("beta.csv"), "")?;
    fs::write(dir.path().join(".hidden.txt"), "")?;
    Ok(dir)
}

fn run_tree(dir: &Workspace, args: &[&str], expected: &[&str]) -> Result<()> {
    let cmd = dir.cmd().args(args).assert().code(0).stderr("");
    let stdout = String::from_utf8(cmd.get_output().stdout.clone())?;
    let mut lines: Vec<_> = stdout.lines().collect();
    lines.sort_unstable();
    let mut expected: Vec<_> = expected
        .iter()
        .map(|path| path.replace('/', std::path::MAIN_SEPARATOR_STR))
        .collect();
    expected.sort_unstable();
    assert_eq!(lines, expected);
    Ok(())
}

#[cli_test]
fn default_path_in_empty_directory(cx: &TestContext) -> Result<()> {
    run_tree(&cx.workspace()?, &[], &["."])
}

#[cli_test]
fn name_and_type_filters_intersect(cx: &TestContext) -> Result<()> {
    run_tree(
        &filter_tree(cx)?,
        &[".", "-t", "f", "-n", "[.]txt$"],
        &["./alpha.txt", "./.hidden.txt"],
    )
}

#[cli_test]
fn name_filter_does_not_prune_directories(cx: &TestContext) -> Result<()> {
    run_tree(
        &filter_tree(cx)?,
        &[".", "-n", "^inside[.]csv$"],
        &["./reports.txt/inside.csv"],
    )
}

#[cli_test]
fn name_matches_basename_not_parent_path(cx: &TestContext) -> Result<()> {
    run_tree(
        &filter_tree(cx)?,
        &["reports.txt", "-t", "f", "-n", "reports"],
        &[],
    )
}

#[cli_test]
fn empty_regex_matches_all_entry_names(cx: &TestContext) -> Result<()> {
    run_tree(
        &filter_tree(cx)?,
        &[".", "-n", ""],
        &[
            ".",
            "./reports.txt",
            "./reports.txt/inside.csv",
            "./alpha.txt",
            "./beta.csv",
            "./.hidden.txt",
        ],
    )
}

#[cli_test]
fn unmatched_name_produces_no_output(cx: &TestContext) -> Result<()> {
    run_tree(&filter_tree(cx)?, &[".", "-n", "^absent$"], &[])
}

#[cli_test]
fn multiple_roots_apply_the_same_filter(cx: &TestContext) -> Result<()> {
    run_tree(
        &filter_tree(cx)?,
        &["alpha.txt", "reports.txt", "-t", "f", "-n", "[.]csv$"],
        &["reports.txt/inside.csv"],
    )
}

#[cli_test]
fn invalid_regex_among_valid_names_is_rejected(cx: &TestContext) {
    cx.cmd()
        .args(["-n", "valid", "-n", "["])
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("invalid value '['"));
}

#[cli_test]
#[cfg(unix)]
fn symlink_filter_does_not_follow_directory_targets(cx: &TestContext) -> Result<()> {
    let dir = filter_tree(cx)?;
    std::os::unix::fs::symlink("reports.txt", dir.path().join("linked"))?;
    run_tree(&dir, &[".", "-t", "l"], &["./linked"])?;
    run_tree(
        &dir,
        &[".", "-t", "f", "-n", "^inside[.]csv$"],
        &["./reports.txt/inside.csv"],
    )
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
