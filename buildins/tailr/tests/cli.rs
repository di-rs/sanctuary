use cli_testing::cargo_bin_cmd;
use predicates::prelude::*;

const EMPTY: &str = "tests/inputs/empty.txt";
const ONE: &str = "tests/inputs/one.txt";
const TWO: &str = "tests/inputs/two.txt";

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

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

fn gen_bad_file() -> String {
    "tests/file/doesnt/exist".to_owned()
}

#[test]
fn dies_no_args() {
    cargo_bin_cmd!()
        .assert()
        .failure()
        .stderr(predicate::str::contains("Usage"));
}

#[test]
fn dies_bad_bytes() {
    let bad = gen_bad_file();
    let expected = "invalid digit found in string";
    cargo_bin_cmd!()
        .args(["-c", &bad, EMPTY])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[test]
fn dies_bad_lines() {
    let bad = gen_bad_file();
    let expected = "invalid digit found in string";
    cargo_bin_cmd!()
        .args(["-n", &bad, EMPTY])
        .assert()
        .failure()
        .stderr(predicate::str::contains(expected));
}

#[test]
fn dies_bytes_and_lines() {
    let msg = "the argument '--lines <LINES>' cannot be used \
               with '--bytes <BYTES>'";

    cargo_bin_cmd!()
        .args(["-n", "1", "-c", "2"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(msg));
}

#[test]
fn skips_bad_file() -> Result<()> {
    let bad = gen_bad_file();
    let expected = format!("{bad}: .* [(]os error 2[)]");
    cargo_bin_cmd!()
        .args([ONE, &bad, TWO])
        .assert()
        .code(1)
        .stderr(predicate::str::is_match(expected)?);
    Ok(())
}

#[test]
fn rejects_unknown_flag() {
    cargo_bin_cmd!()
        .args(["--unknown", EMPTY])
        .assert()
        .failure()
        .stdout("")
        .stderr(predicate::str::contains("--unknown"));
}

#[test]
fn explicit_stdin_returns_last_line() {
    cargo_bin_cmd!()
        .args(["-n", "1", "-"])
        .write_stdin("first\né")
        .assert()
        .success()
        .stdout("é")
        .stderr("");
}

#[test]
fn stdin_line_boundaries() {
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
            cargo_bin_cmd!()
                .args([&format!("--lines={count}"), "-"])
                .write_stdin(input)
                .assert()
                .success()
                .stderr("")
                .stdout(input.iter().skip(start).copied().collect::<Vec<_>>());
        }
    }
}

#[test]
fn stdin_byte_boundaries() {
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
        cargo_bin_cmd!()
            .args([&format!("--bytes={count}"), "-"])
            .write_stdin(input)
            .assert()
            .success()
            .stderr("")
            .stdout(input.iter().skip(start).copied().collect::<Vec<_>>());
    }
}

#[test]
fn stdin_empty() {
    for flag in ["--lines", "--bytes"] {
        for count in ["0", "+0", "1", "+1", "-1"] {
            cargo_bin_cmd!()
                .args([&format!("{flag}={count}"), "-"])
                .write_stdin("")
                .assert()
                .success()
                .stdout("")
                .stderr("");
        }
    }
}

#[test]
fn stdin_crosses_read_boundaries() {
    let mut input = vec![b'x'; 32_769];
    input.extend_from_slice(b"\n\xff\0\nlast");
    for (option, expected) in [
        ("--lines=2", &b"\xff\0\nlast"[..]),
        ("--lines=+2", &b"\xff\0\nlast"[..]),
        ("--bytes=5", &b"\nlast"[..]),
        ("--bytes=+32773", &b"\nlast"[..]),
    ] {
        cargo_bin_cmd!()
            .args([option, "-"])
            .write_stdin(input.clone())
            .assert()
            .success()
            .stderr("")
            .stdout(expected);
    }
}

#[test]
fn stdin_mixed_with_files_and_repeated() {
    for quiet in [false, true] {
        let mut cmd = cargo_bin_cmd!();
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

#[test]
fn unterminated_final_line_counts_toward_line_offsets() {
    for (count, expected) in [
        ("1", "γ"),
        ("+2", "β\nγ"),
        ("+3", "γ"),
        ("+4", ""),
        ("0", ""),
    ] {
        cargo_bin_cmd!()
            .args(["-n", count, "tests/inputs/unterminated.txt"])
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[test]
fn byte_offsets_preserve_raw_utf8_fragments() {
    for (count, expected) in [
        ("1", &b"\xb3"[..]),
        ("2", &b"\xce\xb3"[..]),
        ("+2", &b"\xb1\n\xce\xb2\n\xce\xb3"[..]),
        ("+9", &b""[..]),
    ] {
        cargo_bin_cmd!()
            .args(["-c", count, "tests/inputs/unterminated.txt"])
            .assert()
            .success()
            .stdout(expected)
            .stderr("");
    }
}

#[test]
fn missing_operand_returns_failure() {
    cli_testing::cargo_bin_cmd!()
        .args(["/sanctuary-audit-missing/path"])
        .assert()
        .code(1)
        .stdout("")
        .stderr(predicates::str::contains("/sanctuary-audit-missing/path"));
}

#[test]
fn unreadable_operand_continues_to_later_files() -> Result<()> {
    let dir = assert_fs::TempDir::new()?;
    let valid = dir.path().join("valid");
    std::fs::write(&valid, "later\n")?;
    cli_testing::cargo_bin_cmd!()
        .arg("-q")
        .arg(dir.path())
        .arg(&valid)
        .assert()
        .code(1)
        .stdout("later\n")
        .stderr(predicates::str::contains("directory"));
    Ok(())
}

#[test]
fn directory_byte_operand_continues_to_later_files() -> Result<()> {
    let dir = assert_fs::TempDir::new()?;
    let valid = dir.path().join("valid");
    std::fs::write(&valid, b"later\n")?;
    for (count, expected) in [("3", "er\n"), ("+2", "ater\n"), ("0", "")] {
        cargo_bin_cmd!()
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

#[test]
#[allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify observable CLI behavior."
)]
fn broken_stdout_does_not_wait_for_later_stdin() -> Result<()> {
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
        let mut command = cli_testing::context!().std_command();
        command.args(["-q", mode, "+1"]).arg(&input).arg("-");
        let mut child = command
            .stdin(stdin)
            .stdout(writer)
            .stderr(Stdio::piped())
            .spawn()?;
        let deadline = Instant::now() + Duration::from_secs(5);
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
