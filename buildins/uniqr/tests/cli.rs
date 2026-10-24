use cli_testing::{TestContext, cli_test};
use predicates::prelude::*;
use pretty_assertions::assert_eq;
use std::{fs, os::unix::fs::PermissionsExt};
use tempfile::NamedTempFile;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

const EMPTY: &str = "empty";

const ONE: &str = "one";

const TWO: &str = "two";

const THREE: &str = "three";

const SKIP: &str = "skip";

const T1: &str = "t1";

const T2: &str = "t2";

const T3: &str = "t3";

const T4: &str = "t4";

const T5: &str = "t5";

const T6: &str = "t6";

#[cli_test]
fn usage(cx: &TestContext) {
    for flag in &["-h", "--help"] {
        cx.cmd()
            .arg(flag)
            .assert()
            .success()
            .stderr("")
            .stdout(predicate::str::contains("Usage"));
    }
}

fn gen_bad_file() -> Result<NamedTempFile> {
    let file = NamedTempFile::new()?;
    fs::set_permissions(file.path(), PermissionsExt::from_mode(0o000))?;
    Ok(file)
}

#[cli_test]
fn dies_bad_file(cx: &TestContext) -> Result<()> {
    let bad = gen_bad_file()?;
    let expected = format!("{}: .* [(]os error 13[)]", bad.path().display());
    cx.cmd()
        .arg(bad.path())
        .assert()
        .failure()
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

fn run_outfile_case(cx: &TestContext, name: &str) -> Result<()> {
    let suite = cx.suite()?;
    let case = suite.case(name)?;
    let path = case
        .expect
        .stdout_file
        .as_deref()
        .ok_or("missing output fixture")?;
    let expected = suite.read(path)?;
    let workspace = cx.workspace()?;
    let output = workspace.child("output");
    let mut case_context = cx.case(name)?;
    if case.stdin.is_some() {
        case_context.args(["-"])?;
    }
    case_context.args([output.path()])?;
    case_context.map_expected_stdout(|_| Vec::new())?;
    case_context.check()?;
    assert_eq!(fs::read(output.path())?, expected);
    Ok(())
}

fn run_outfile(cx: &TestContext, name: &str) -> Result<()> {
    run_outfile_case(cx, name)
}

fn run_outfile_count(cx: &TestContext, name: &str) -> Result<()> {
    run_outfile_case(cx, &format!("{name}_count"))
}

fn run_outfile_stdin_count(cx: &TestContext, name: &str) -> Result<()> {
    run_outfile_case(cx, &format!("{name}_stdin_count"))
}

#[cli_test]
fn rejects_unknown_flag(cx: &TestContext) {
    cx.cmd()
        .arg("--unknown")
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("--unknown"));
}

#[cli_test]
fn counts_adjacent_unicode_runs_and_unterminated_last_line(cx: &TestContext) {
    cx.cmd()
        .args(["-c", "-"])
        .write_stdin("é\né\n界\né")
        .assert()
        .success()
        .stdout("   2 é\n   1 界\n   1 é")
        .stderr("");
}

#[cli_test]
fn counts_blank_runs_without_merging_nonadjacent_runs(cx: &TestContext) {
    cx.cmd()
        .arg("-c")
        .write_stdin("\n\nx\n\n")
        .assert()
        .success()
        .stdout("   2 \n   1 x\n   1 \n")
        .stderr("");
}

#[cli_test]
fn trailing_spaces_and_tabs_distinguish_lines(cx: &TestContext) {
    cx.cmd()
        .arg("-c")
        .write_stdin("x\nx \nx\t\n")
        .assert()
        .success()
        .stdout("   1 x\n   1 x \n   1 x\t\n")
        .stderr("");
}

#[cli_test]
fn output_file_is_truncated_for_shorter_result(cx: &TestContext) -> Result<()> {
    let outfile = NamedTempFile::new()?;
    fs::write(outfile.path(), "stale data that must not survive")?;
    cx.cmd()
        .arg("-")
        .arg(outfile.path())
        .write_stdin("é\né\n")
        .assert()
        .success()
        .stdout("")
        .stderr("");
    assert_eq!(fs::read_to_string(outfile.path())?, "é\n");
    Ok(())
}

#[cli_test]
fn empty_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, EMPTY)
}

#[cli_test]
fn empty_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, EMPTY)
}

#[cli_test]
fn empty_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, EMPTY)
}

#[cli_test]
fn one_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, ONE)
}

#[cli_test]
fn one_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, ONE)
}

#[cli_test]
fn one_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, ONE)
}

#[cli_test]
fn two_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, TWO)
}

#[cli_test]
fn two_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, TWO)
}

#[cli_test]
fn two_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, TWO)
}

#[cli_test]
fn three_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, THREE)
}

#[cli_test]
fn three_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, THREE)
}

#[cli_test]
fn three_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, THREE)
}

#[cli_test]
fn skip_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, SKIP)
}

#[cli_test]
fn skip_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, SKIP)
}

#[cli_test]
fn skip_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, SKIP)
}

#[cli_test]
fn t1_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, T1)
}

#[cli_test]
fn t1_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, T1)
}

#[cli_test]
fn t1_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, T1)
}

#[cli_test]
fn t2_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, T2)
}

#[cli_test]
fn t2_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, T2)
}

#[cli_test]
fn t2_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, T2)
}

#[cli_test]
fn t3_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, T3)
}

#[cli_test]
fn t3_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, T3)
}

#[cli_test]
fn t3_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, T3)
}

#[cli_test]
fn t4_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, T4)
}

#[cli_test]
fn t4_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, T4)
}

#[cli_test]
fn t4_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, T4)
}

#[cli_test]
fn t5_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, T5)
}

#[cli_test]
fn t5_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, T5)
}

#[cli_test]
fn t5_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, T5)
}

#[cli_test]
fn t6_outfile(cx: &TestContext) -> Result<()> {
    run_outfile(cx, T6)
}

#[cli_test]
fn t6_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_count(cx, T6)
}

#[cli_test]
fn t6_stdin_outfile_count(cx: &TestContext) -> Result<()> {
    run_outfile_stdin_count(cx, T6)
}

#[cli_test]
#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify observable CLI behavior; Result propagates fixture errors."
)]
fn rejects_output_aliases_without_truncating(cx: &TestContext) -> Result<()> {
    let dir = assert_fs::TempDir::new()?;
    let input = dir.path().join("input");
    let alias = dir.path().join("alias");
    std::fs::write(&input, b"a\na\n")?;
    std::fs::hard_link(&input, &alias)?;
    let symlink = dir.path().join("symlink");
    std::os::unix::fs::symlink(&input, &symlink)?;
    for output in [&input, &alias, &symlink] {
        cx.cmd()
            .arg(&input)
            .arg(output)
            .assert()
            .code(65)
            .stdout("")
            .stderr(predicates::str::contains("same file"));
        assert_eq!(std::fs::read(&input)?, b"a\na\n");
    }
    Ok(())
}

#[cli_test]
fn writes_to_non_regular_outputs(cx: &TestContext) {
    cx.cmd()
        .args(["-", "/dev/null"])
        .write_stdin("a\na\nb\n")
        .assert()
        .code(0)
        .stdout("")
        .stderr("");
}

#[cli_test]
#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify observable CLI behavior."
)]
fn writes_to_fifo(cx: &TestContext) -> Result<()> {
    use std::io::Read;
    let dir = assert_fs::TempDir::new()?;
    let path = dir.path().join("output.fifo");
    let status = std::process::Command::new("mkfifo").arg(&path).status()?;
    assert!(status.success());
    // Hold both ends open so the small write never waits for a separate reader.
    let mut fifo = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open(&path)?;
    cx.cmd()
        .arg("-")
        .arg(&path)
        .write_stdin("a\na\nb\n")
        .assert()
        .code(0)
        .stdout("")
        .stderr("");
    let mut output = [0; 4];
    fifo.read_exact(&mut output)?;
    assert_eq!(&output, b"a\nb\n");
    Ok(())
}
