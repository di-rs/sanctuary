use cli_testing::{TestContext, cli_test};
use predicates::prelude::*;

const EMPTY: &str = "tests/inputs/empty.txt";
const ONE: &str = "tests/inputs/one.txt";
const TWO: &str = "tests/inputs/two.txt";

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

fn gen_bad_file() -> String {
    "tests/file/doesnt/exist".to_owned()
}

#[cli_test]
fn skips_bad_file(cx: &TestContext) -> Result<()> {
    let bad = gen_bad_file();
    let expected = format!("{bad}: .* [(]os error 2[)]");
    cx.cmd()
        .args([ONE, &bad, TWO])
        .assert()
        .code(1)
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[cli_test]
fn explicit_stdin_returns_last_line(cx: &TestContext) {
    cx.cmd()
        .args(["-n", "1", "-"])
        .write_stdin("first\né")
        .assert()
        .success()
        .stdout("é")
        .stderr("");
}

#[cli_test]
fn stdin_line_boundaries(cx: &TestContext) {
    for input in [&b"a\n\xff\n\nz"[..], &b"a\n\xff\n\nz\n"[..]] {
        for (count, start) in [
            ("1", 5),
            ("-1", 5),
            ("2", 4),
            ("+3", 4),
            ("+4", 5),
            ("+5", input.len()),
            ("0", input.len()),
            ("-0", input.len()),
            ("+0", 0),
            ("+1", 0),
            ("99", 0),
            ("-9223372036854775808", 0),
        ] {
            cx.cmd()
                .args([&format!("--lines={count}"), "-"])
                .write_stdin(input)
                .assert()
                .success()
                .stderr("")
                .stdout(input.iter().skip(start).copied().collect::<Vec<_>>());
        }
    }
}

#[cli_test]
fn stdin_byte_boundaries(cx: &TestContext) {
    let input = &b"a\n\xc3\xa9\0\xff"[..];
    for (count, start) in [
        ("1", 5),
        ("-1", 5),
        ("3", 3),
        ("+4", 3),
        ("+6", 5),
        ("+7", 6),
        ("0", 6),
        ("-0", 6),
        ("+0", 0),
        ("+1", 0),
        ("99", 0),
        ("-9223372036854775808", 0),
    ] {
        cx.cmd()
            .args([&format!("--bytes={count}"), "-"])
            .write_stdin(input)
            .assert()
            .success()
            .stderr("")
            .stdout(input.iter().skip(start).copied().collect::<Vec<_>>());
    }
}

#[cli_test]
fn stdin_empty(cx: &TestContext) {
    for flag in ["--lines", "--bytes"] {
        for count in ["0", "+0", "1", "+1", "-1"] {
            cx.cmd()
                .args([&format!("{flag}={count}"), "-"])
                .write_stdin("")
                .assert()
                .success()
                .stdout("")
                .stderr("");
        }
    }
}

#[cli_test]
fn stdin_crosses_read_boundaries(cx: &TestContext) {
    let mut input = vec![b'x'; 32_769];
    input.extend_from_slice(b"\n\xff\0\nlast");
    for (option, expected) in [
        ("--lines=2", &b"\xff\0\nlast"[..]),
        ("--lines=+2", &b"\xff\0\nlast"[..]),
        ("--bytes=5", &b"\nlast"[..]),
        ("--bytes=+32773", &b"\nlast"[..]),
    ] {
        cx.cmd()
            .args([option, "-"])
            .write_stdin(input.clone())
            .assert()
            .success()
            .stderr("")
            .stdout(expected);
    }
}

#[cli_test]
fn stdin_mixed_with_files_and_repeated(cx: &TestContext) {
    for quiet in [false, true] {
        let mut cmd = cx.cmd();
        cmd.args(["-n", "1", EMPTY, "-", EMPTY, "-"]);
        if quiet {
            cmd.arg("-q");
        }
        let expected = if quiet {
            "last\n".to_owned()
        } else {
            format!("==> {EMPTY} <==\n\n==> - <==\nlast\n\n==> {EMPTY} <==\n\n==> - <==\n")
        };
        cmd.write_stdin("first\nlast\n")
            .assert()
            .success()
            .stderr("")
            .stdout(expected);
    }
}

#[cli_test]
fn unterminated_final_line_counts_toward_line_offsets(cx: &TestContext) {
    for (count, expected) in [
        ("1", "γ"),
        ("+2", "β\nγ"),
        ("+3", "γ"),
        ("+4", ""),
        ("0", ""),
    ] {
        cx.cmd()
            .args(["-n", count, "tests/inputs/unterminated.txt"])
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn byte_offsets_preserve_raw_utf8_fragments(cx: &TestContext) {
    for (count, expected) in [
        ("1", &b"\xb3"[..]),
        ("2", &b"\xce\xb3"[..]),
        ("+2", &b"\xb1\n\xce\xb2\n\xce\xb3"[..]),
        ("+9", &b""[..]),
    ] {
        cx.cmd()
            .args(["-c", count, "tests/inputs/unterminated.txt"])
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[cli_test]
fn missing_operand_returns_failure(cx: &TestContext) {
    cx.cmd()
        .args(["/sanctuary-audit-missing/path"])
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicates::str::contains("/sanctuary-audit-missing/path"));
}

#[cli_test]
fn unreadable_operand_continues_to_later_files(cx: &TestContext) -> Result<()> {
    let dir = assert_fs::TempDir::new()?;
    let valid = dir.path().join("valid");
    std::fs::write(&valid, "later\n")?;
    cx.cmd()
        .arg("-q")
        .arg(dir.path())
        .arg(&valid)
        .assert()
        .code(1)
        .stdout("later\n")
        .stderr(predicates::str::contains("directory"));
    Ok(())
}

#[cli_test]
fn directory_byte_operand_continues_to_later_files(cx: &TestContext) -> Result<()> {
    let dir = assert_fs::TempDir::new()?;
    let valid = dir.path().join("valid");
    std::fs::write(&valid, b"later\n")?;
    for (count, expected) in [("3", "er\n"), ("+2", "ater\n"), ("0", "")] {
        cx.cmd()
            .args(["-q", "-c", count])
            .arg(dir.path())
            .arg(&valid)
            .assert()
            .code(1)
            .stdout(expected)
            .stderr(predicate::str::contains("directory"));
    }
    Ok(())
}

#[cli_test]
#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify observable CLI behavior."
)]
fn broken_stdout_does_not_wait_for_later_stdin(cx: &TestContext) -> Result<()> {
    use std::{
        io,
        process::Stdio,
        time::{Duration, Instant},
    };
    let dir = assert_fs::TempDir::new()?;
    let input = dir.path().join("large");
    std::fs::write(&input, vec![b'x'; 65536])?;
    for mode in ["-n", "-c"] {
        let (reader, writer) = io::pipe()?;
        drop(reader);
        let (stdin, pending_input) = io::pipe()?;
        // A standard Command preserves the deliberately closed stdout pipe.
        let mut command = cx.std_command();
        command.args(["-q", mode, "+1"]).arg(&input).arg("-");
        let mut child = command
            .stdin(stdin)
            .stdout(writer)
            .stderr(Stdio::piped())
            .spawn()?;
        let deadline = Instant::now()
            .checked_add(Duration::from_secs(5))
            .ok_or("deadline overflow")?;
        while child.try_wait()?.is_none() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        let exited = child.try_wait()?.is_some();
        if !exited {
            child.kill()?;
        }
        let output = child.wait_with_output()?;
        drop(pending_input);
        assert!(exited, "tailr waited for stdin after stdout failed");
        assert_eq!(output.status.code(), Some(65));
        assert_eq!(output.stdout, b"");
        assert!(String::from_utf8(output.stderr)?.contains("Broken pipe"));
    }
    Ok(())
}
