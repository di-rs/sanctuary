use cli_testing::{Command, TestContext, cli_test};
use predicates::prelude::*;

fn assert_silent_status(cmd: &mut Command, status: i32) {
    cmd.assert()
        .stdout(predicate::str::is_empty())
        .stderr(predicate::str::is_empty())
        .code(status);
}

#[cli_test]
fn true_ignores_arguments(cx: &TestContext) {
    assert_silent_status(cx.cmd().args(["--help", "ignored"]), 0);
}
