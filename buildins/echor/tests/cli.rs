use cli_testing::cargo_bin_cmd;
use predicates::prelude::*;

#[test]
fn dies_no_args() {
    let mut cmd = cargo_bin_cmd!();
    cmd.assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("Usage"));
}

#[test]
fn runs() {
    let mut cmd = cargo_bin_cmd!();
    cmd.arg("Hello")
        .assert()
        .success()
        .stdout("Hello\n")
        .stderr("");
}

#[test]
fn usage() {
    for flag in ["-h", "--help"] {
        cargo_bin_cmd!()
            .arg(flag)
            .assert()
            .success()
            .stdout(predicate::str::contains("Usage"))
            .stderr("");
    }
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
fn empty_arguments_keep_separators() {
    for (args, expected) in [
        (vec![""], "\n"),
        (vec!["-n", ""], ""),
        (vec!["", "é", ""], " é \n"),
    ] {
        cargo_bin_cmd!()
            .args(args)
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[test]
fn end_of_options_preserves_flag_like_text() {
    cargo_bin_cmd!()
        .args(["--", "-n", "--help"])
        .assert()
        .success()
        .stdout("-n --help\n")
        .stderr("");
}

#[test]
fn unicode_and_backslashes_are_literal() {
    cargo_bin_cmd!()
        .args(["-n", "世界", r"\n\t"])
        .assert()
        .success()
        .stdout("世界 \\n\\t")
        .stderr("");
}
