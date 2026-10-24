use cli_testing::{TestContext, cli_test};

#[cli_test]
fn dies_no_args(cx: &TestContext) {
    cx.assert_error(std::iter::empty::<&str>(), 2, "Usage");
}

#[cli_test]
fn runs(cx: &TestContext) {
    let mut cmd = cx.cmd();
    cmd.arg("Hello")
        .assert()
        .success()
        .stdout("Hello\n")
        .stderr("");
}

#[cli_test]
fn usage(cx: &TestContext) {
    cx.assert_help();
}

#[cli_test]
fn rejects_unknown_flag(cx: &TestContext) {
    cx.assert_error(["--unknown"], 2, "--unknown");
}

#[cli_test]
fn empty_arguments_keep_separators(cx: &TestContext) {
    for (args, expected) in [
        (vec![""], "\n"),
        (vec!["-n", ""], ""),
        (vec!["", "é", ""], " é \n"),
    ] {
        cx.cmd()
            .args(args)
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn end_of_options_preserves_flag_like_text(cx: &TestContext) {
    cx.cmd()
        .args(["--", "-n", "--help"])
        .assert()
        .success()
        .stdout("-n --help\n")
        .stderr("");
}

#[cli_test]
fn unicode_and_backslashes_are_literal(cx: &TestContext) {
    cx.cmd()
        .args(["-n", "世界", r"\n\t"])
        .assert()
        .success()
        .stdout("世界 \\n\\t")
        .stderr("");
}
