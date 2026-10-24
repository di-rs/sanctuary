use cli_testing::{TestContext, cli_test};
use predicates::prelude::*;

#[cli_test]
fn dies_no_args(cx: &TestContext) {
    let mut cmd = cx.command();
    cmd.assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("Usage"));
}

#[cli_test]
fn runs(cx: &TestContext) {
    let mut cmd = cx.command();
    cmd.arg("Hello")
        .assert()
        .success()
        .stdout("Hello\n")
        .stderr("");
}

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

#[cli_test]
fn rejects_unknown_flag(cx: &TestContext) {
    cx.command()
        .arg("--unknown")
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("--unknown"));
}

#[cli_test]
fn empty_arguments_keep_separators(cx: &TestContext) {
    for (args, expected) in [
        (vec![""], "\n"),
        (vec!["-n", ""], ""),
        (vec!["", "é", ""], " é \n"),
    ] {
        cx.command()
            .args(args)
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn end_of_options_preserves_flag_like_text(cx: &TestContext) {
    cx.command()
        .args(["--", "-n", "--help"])
        .assert()
        .success()
        .stdout("-n --help\n")
        .stderr("");
}

#[cli_test]
fn unicode_and_backslashes_are_literal(cx: &TestContext) {
    cx.command()
        .args(["-n", "世界", r"\n\t"])
        .assert()
        .success()
        .stdout("世界 \\n\\t")
        .stderr("");
}
