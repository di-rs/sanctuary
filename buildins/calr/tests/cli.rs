use cli_testing::{TestContext, cli_test};
use predicates::prelude::*;
use pretty_assertions::assert_eq;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cli_test]
fn month_num(cx: &TestContext) {
    let expected = &[
        ("1", "January"),
        ("2", "February"),
        ("3", "March"),
        ("4", "April"),
        ("5", "May"),
        ("6", "June"),
        ("7", "July"),
        ("8", "August"),
        ("9", "September"),
        ("10", "October"),
        ("11", "November"),
        ("12", "December"),
    ];

    for (num, month) in expected {
        cx.cmd()
            .args(["-m", num])
            .assert()
            .success()
            .stdout(predicates::str::contains(month.to_string()));
    }
}

#[cli_test]
fn partial_month(cx: &TestContext) {
    let expected = &[
        ("ja", "January"),
        ("f", "February"),
        ("mar", "March"),
        ("ap", "April"),
        ("may", "May"),
        ("jun", "June"),
        ("jul", "July"),
        ("au", "August"),
        ("s", "September"),
        ("n", "November"),
        ("d", "December"),
    ];

    for (arg, month) in expected {
        cx.cmd()
            .args(["-m", arg])
            .assert()
            .success()
            .stdout(predicates::str::contains(month.to_string()));
    }
}

#[cli_test]
fn default_one_month(cx: &TestContext) -> Result<()> {
    let cmd = cx.cmd().assert().success();
    let out = cmd.get_output();
    let stdout = String::from_utf8(out.stdout.clone())?;
    let lines: Vec<_> = stdout.split('\n').collect();
    assert_eq!(lines.len(), 9);
    assert_eq!(lines.first().map(|line| line.len()), Some(22));
    Ok(())
}

#[cli_test]
fn year(cx: &TestContext) -> Result<()> {
    let cmd = cx.cmd().arg("-y").assert().success();
    let stdout = String::from_utf8(cmd.get_output().stdout.clone())?;
    let lines = stdout.split('\n');
    assert_eq!(lines.count(), 37);
    Ok(())
}

#[cli_test]
fn redirected_calendar_has_no_ansi(cx: &TestContext) {
    cx.cmd()
        .assert()
        .code(0)
        .stderr("")
        .stdout(predicate::str::contains("\u{1b}").not());
}
