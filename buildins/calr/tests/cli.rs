use cli_testing::{TestContext, cli_test};
use predicates::prelude::*;
use pretty_assertions::assert_eq;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[cli_test]
fn dies_year_0(cx: &TestContext) {
    cx.command()
        .arg("0")
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "error: invalid value '0' for '[YEAR]': 0 is not in 1..=9999",
        ));
}

#[cli_test]
fn dies_year_10000(cx: &TestContext) {
    cx.command()
        .arg("10000")
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "error: invalid value \'10000\' \
                for \'[YEAR]\': 10000 is not in 1..=9999",
        ));
}

#[cli_test]
fn dies_invalid_year(cx: &TestContext) {
    cx.command()
        .arg("foo")
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "error: invalid value \'foo\' for \'[YEAR]\': \
                invalid digit found in string",
        ));
}

#[cli_test]
fn dies_month_0(cx: &TestContext) {
    cx.command()
        .args(["-m", "0"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "invalid value '0' for '-m <MONTH>': not in the range 1 through 12",
        ));
}

#[cli_test]
fn dies_month_13(cx: &TestContext) {
    cx.command()
        .args(["-m", "13"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "invalid value '13' for '-m <MONTH>': not in the range 1 through 12",
        ));
}

#[cli_test]
fn dies_invalid_month(cx: &TestContext) {
    cx.command()
        .args(["-m", "foo"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "invalid value 'foo' for '-m <MONTH>'",
        ));
}

#[cli_test]
fn dies_y_and_month(cx: &TestContext) {
    let expected = "the argument '-m <MONTH>' cannot be used with '--year'";
    cx.command()
        .args(["-m", "1", "-y"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[cli_test]
fn dies_y_and_year(cx: &TestContext) {
    let expected = "the argument '--year' cannot be used with '[YEAR]'";
    cx.command()
        .args(["-y", "2000"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

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
        cx.command()
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
        cx.command()
            .args(["-m", arg])
            .assert()
            .success()
            .stdout(predicates::str::contains(month.to_string()));
    }
}

#[cli_test]
fn default_one_month(cx: &TestContext) -> Result<()> {
    let cmd = cx.command().assert().success();
    let out = cmd.get_output();
    let stdout = String::from_utf8(out.stdout.clone())?;
    let lines: Vec<_> = stdout.split('\n').collect();
    assert_eq!(lines.len(), 9);
    assert_eq!(lines.first().map(|line| line.len()), Some(22));
    Ok(())
}

#[cli_test]
fn year(cx: &TestContext) -> Result<()> {
    let cmd = cx.command().arg("-y").assert().success();
    let stdout = String::from_utf8(cmd.get_output().stdout.clone())?;
    let lines = stdout.split('\n');
    assert_eq!(lines.count(), 37);
    Ok(())
}

#[cli_test]
fn usage(cx: &TestContext) {
    for flag in ["-h", "--help"] {
        cx.command()
            .arg(flag)
            .assert()
            .success()
            .stdout(predicate::str::contains("Usage"));
    }
}

#[cli_test]
fn dies_ambiguous_or_empty_month(cx: &TestContext) {
    for month in ["", "m", "j", "a"] {
        cx.command()
            .args(["2020", "-m", month])
            .assert()
            .failure()
            .stdout("")
            .stderr(predicate::str::contains("invalid value"));
    }
}

#[cli_test]
fn dies_long_year_and_month_in_either_order(cx: &TestContext) {
    for args in [["--year", "-m", "December"], ["-m", "December", "--year"]] {
        cx.command()
            .args(args)
            .assert()
            .failure()
            .stdout("")
            .stderr(predicate::str::contains("cannot be used with"));
    }
}

#[cli_test]
fn dies_long_year_and_explicit_year_in_either_order(cx: &TestContext) {
    for args in [["--year", "2000"], ["2000", "--year"]] {
        cx.command()
            .args(args)
            .assert()
            .failure()
            .stdout("")
            .stderr(predicate::str::contains("cannot be used with"));
    }
}

#[cli_test]
fn redirected_calendar_has_no_ansi(cx: &TestContext) {
    cx.command()
        .assert()
        .code(0)
        .stderr("")
        .stdout(predicate::str::contains("\u{1b}").not());
}
