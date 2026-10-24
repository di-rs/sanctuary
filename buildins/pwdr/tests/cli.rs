use assert_fs::prelude::*;
use cli_testing::{Command, TestContext, cli_test};
use predicates::prelude::*;
use std::path::Path;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn command(cx: &TestContext, cwd: &Path) -> Command {
    let mut cmd = cx.cmd();
    cmd.current_dir(cwd).env_remove("PWD");
    cmd
}

fn assert_path(cmd: &mut Command, expected: &Path) {
    cmd.assert()
        .success()
        .stdout(format!("{}\n", expected.display()))
        .stderr("");
}

#[cli_test]
fn prints_current_directory_in_each_mode(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    let physical = dir.path().canonicalize()?;
    for args in [&[][..], &["-L"][..], &["-P"][..]] {
        assert_path(
            command(cx, &physical).env("PWD", &physical).args(args),
            &physical,
        );
    }
    Ok(())
}

#[cli_test]
fn falls_back_when_pwd_is_unset(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    let physical = dir.path().canonicalize()?;
    for args in [&[][..], &["-L"][..]] {
        assert_path(command(cx, &physical).args(args), &physical);
    }
    Ok(())
}

#[cli_test]
fn falls_back_when_pwd_is_invalid(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("cwd").create_dir_all()?;
    dir.child("other").create_dir_all()?;
    dir.child("file").write_str("not a directory")?;
    let physical = dir.child("cwd").path().canonicalize()?;
    for pwd in [
        "".into(),
        "relative".into(),
        dir.path().join("missing"),
        dir.path().join("other"),
        dir.path().join("file"),
    ] {
        for args in [&[][..], &["-L"][..], &["-P"][..]] {
            assert_path(
                command(cx, &physical).env("PWD", &pwd).args(args),
                &physical,
            );
        }
    }
    Ok(())
}

#[cfg(unix)]
#[cli_test]
fn logical_modes_preserve_symlink_pwd(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("real").create_dir_all()?;
    let physical = dir.child("real").path().canonicalize()?;
    let logical = dir.path().canonicalize()?.join("link");
    std::os::unix::fs::symlink(&physical, &logical)?;
    for args in [&[][..], &["-L"][..]] {
        assert_path(
            command(cx, &logical).env("PWD", &logical).args(args),
            &logical,
        );
    }
    Ok(())
}

#[cfg(unix)]
#[cli_test]
fn physical_mode_resolves_symlink_pwd(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    dir.child("real").create_dir_all()?;
    let physical = dir.child("real").path().canonicalize()?;
    let logical = dir.path().canonicalize()?.join("link");
    std::os::unix::fs::symlink(&physical, &logical)?;
    assert_path(
        command(cx, &logical).env("PWD", &logical).arg("-P"),
        &physical,
    );
    Ok(())
}

#[cli_test]
fn rejects_conflicting_modes(cx: &TestContext) -> Result<()> {
    let dir = cx.workspace()?;
    for args in [["-L", "-P"], ["-P", "-L"]] {
        command(cx, dir.path())
            .args(args)
            .assert()
            .code(2)
            .stdout("")
            .stderr(predicate::str::contains("cannot be used with"));
    }
    Ok(())
}
