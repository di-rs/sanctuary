use cli_testing::{Command, cargo_bin_cmd};
use predicates::prelude::*;

fn assert_silent_status(cmd: &mut Command, status: i32) {
    cmd.assert()
        .stdout(predicate::str::is_empty())
        .stderr(predicate::str::is_empty())
        .code(status);
}

#[test]
fn true_ignores_arguments() {
    assert_silent_status(cargo_bin_cmd!("true").args(["--help", "ignored"]), 0);
}
