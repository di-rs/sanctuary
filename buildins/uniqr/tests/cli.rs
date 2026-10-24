use cli_testing::cargo_bin_cmd;
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

fn gen_bad_file() -> Result<NamedTempFile> {
    let file = NamedTempFile::new()?;
    fs::set_permissions(file.path(), PermissionsExt::from_mode(0o000))?;
    Ok(file)
}

#[test]
fn dies_bad_file() -> Result<()> {
    let bad = gen_bad_file()?;
    let expected = format!("{}: .* [(]os error 13[)]", bad.path().display());
    cargo_bin_cmd!()
        .arg(bad.path())
        .assert()
        .failure()
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

fn run_outfile_case(name: &str) -> Result<()> {
    let context = cli_testing::context!();
    let suite = context.suite()?;
    let case = suite.case(name)?;
    let path = case
        .expect
        .stdout_file
        .as_deref()
        .ok_or("missing output fixture")?;
    let expected = suite.read(path)?;
    let workspace = context.workspace()?;
    let output = workspace.child("output");
    let mut cx = context.case(name)?;
    if case.stdin.is_some() {
        cx.args(["-"])?;
    }
    cx.args([output.path()])?;
    cx.map_expected_stdout(|_| Vec::new())?;
    cx.check()?;
    assert_eq!(fs::read(output.path())?, expected);
    Ok(())
}

fn run_outfile(name: &str) -> Result<()> {
    run_outfile_case(name)
}

fn run_outfile_count(name: &str) -> Result<()> {
    run_outfile_case(&format!("{name}_count"))
}

fn run_outfile_stdin_count(name: &str) -> Result<()> {
    run_outfile_case(&format!("{name}_stdin_count"))
}

#[test]
fn rejects_unknown_flag() {
    cargo_bin_cmd!()
        .arg("--unknown")
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("--unknown"));
}

#[test]
fn counts_adjacent_unicode_runs_and_unterminated_last_line() {
    cargo_bin_cmd!()
        .args(["-c", "-"])
        .write_stdin("é\né\n界\né")
        .assert()
        .success()
        .stdout("   2 é\n   1 界\n   1 é")
        .stderr("");
}

#[test]
fn counts_blank_runs_without_merging_nonadjacent_runs() {
    cargo_bin_cmd!()
        .arg("-c")
        .write_stdin("\n\nx\n\n")
        .assert()
        .success()
        .stdout("   2 \n   1 x\n   1 \n")
        .stderr("");
}

#[test]
fn trailing_spaces_and_tabs_distinguish_lines() {
    cargo_bin_cmd!()
        .arg("-c")
        .write_stdin("x\nx \nx\t\n")
        .assert()
        .success()
        .stdout("   1 x\n   1 x \n   1 x\t\n")
        .stderr("");
}

#[test]
fn output_file_is_truncated_for_shorter_result() -> Result<()> {
    let outfile = NamedTempFile::new()?;
    fs::write(outfile.path(), "stale data that must not survive")?;
    cargo_bin_cmd!()
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

#[test]
fn empty_outfile() -> Result<()> {
    run_outfile(EMPTY)
}

#[test]
fn empty_outfile_count() -> Result<()> {
    run_outfile_count(EMPTY)
}

#[test]
fn empty_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(EMPTY)
}

#[test]
fn one_outfile() -> Result<()> {
    run_outfile(ONE)
}

#[test]
fn one_outfile_count() -> Result<()> {
    run_outfile_count(ONE)
}

#[test]
fn one_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(ONE)
}

#[test]
fn two_outfile() -> Result<()> {
    run_outfile(TWO)
}

#[test]
fn two_outfile_count() -> Result<()> {
    run_outfile_count(TWO)
}

#[test]
fn two_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(TWO)
}

#[test]
fn three_outfile() -> Result<()> {
    run_outfile(THREE)
}

#[test]
fn three_outfile_count() -> Result<()> {
    run_outfile_count(THREE)
}

#[test]
fn three_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(THREE)
}

#[test]
fn skip_outfile() -> Result<()> {
    run_outfile(SKIP)
}

#[test]
fn skip_outfile_count() -> Result<()> {
    run_outfile_count(SKIP)
}

#[test]
fn skip_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(SKIP)
}

#[test]
fn t1_outfile() -> Result<()> {
    run_outfile(T1)
}

#[test]
fn t1_outfile_count() -> Result<()> {
    run_outfile_count(T1)
}

#[test]
fn t1_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(T1)
}

#[test]
fn t2_outfile() -> Result<()> {
    run_outfile(T2)
}

#[test]
fn t2_outfile_count() -> Result<()> {
    run_outfile_count(T2)
}

#[test]
fn t2_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(T2)
}

#[test]
fn t3_outfile() -> Result<()> {
    run_outfile(T3)
}

#[test]
fn t3_outfile_count() -> Result<()> {
    run_outfile_count(T3)
}

#[test]
fn t3_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(T3)
}

#[test]
fn t4_outfile() -> Result<()> {
    run_outfile(T4)
}

#[test]
fn t4_outfile_count() -> Result<()> {
    run_outfile_count(T4)
}

#[test]
fn t4_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(T4)
}

#[test]
fn t5_outfile() -> Result<()> {
    run_outfile(T5)
}

#[test]
fn t5_outfile_count() -> Result<()> {
    run_outfile_count(T5)
}

#[test]
fn t5_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(T5)
}

#[test]
fn t6_outfile() -> Result<()> {
    run_outfile(T6)
}

#[test]
fn t6_outfile_count() -> Result<()> {
    run_outfile_count(T6)
}

#[test]
fn t6_stdin_outfile_count() -> Result<()> {
    run_outfile_stdin_count(T6)
}

#[test]
#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify observable CLI behavior; Result propagates fixture errors."
)]
fn rejects_output_aliases_without_truncating() -> Result<()> {
    let dir = assert_fs::TempDir::new()?;
    let input = dir.path().join("input");
    let alias = dir.path().join("alias");
    std::fs::write(&input, b"a\na\n")?;
    std::fs::hard_link(&input, &alias)?;
    let symlink = dir.path().join("symlink");
    std::os::unix::fs::symlink(&input, &symlink)?;
    for output in [&input, &alias, &symlink] {
        cli_testing::cargo_bin_cmd!()
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

#[test]
fn writes_to_non_regular_outputs() {
    cli_testing::cargo_bin_cmd!()
        .args(["-", "/dev/null"])
        .write_stdin("a\na\nb\n")
        .assert()
        .code(0)
        .stdout("")
        .stderr("");
}

#[test]
#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify observable CLI behavior."
)]
fn writes_to_fifo() -> Result<()> {
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
    cli_testing::cargo_bin_cmd!()
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
