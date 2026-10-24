#![cfg(unix)]
#![allow(
    clippy::panic_in_result_fn,
    reason = "Assertions verify catalog contracts; Result propagates fixture setup errors."
)]
use assert_fs::{TempDir, prelude::*};
use cli_testing::{TestContext, catalog::Suite, recording};
use std::fs;

type Result = std::result::Result<(), Box<dyn std::error::Error>>;

const RECIPE: &str = r#"schema = 1
binary = "sample"
reference = "cat"
[fixtures]
text = "data.bin"
[references.cat]
program = "/bin/cat"
platform = "PLATFORM"
[[cases]]
name = "copy"
args = [{ fixture = "text" }]
expect = { exit = 0 }
[[cases]]
name = "pipe"
args = []
stdin = { mode = "pipe", files = ["text", "text"] }
expect = { exit = 0, stdout_file = "twice.out" }
[[cases]]
name = "file"
args = []
stdin = { mode = "file", path = "text" }
expect = { exit = 0, stdout_file = "copy.out" }
"#;

fn setup(root: &TempDir, recipe: &str, inputs: &str, expected: &str) -> Result {
    root.child("Cargo.toml")
        .write_str("[package]\nname = 'sample'\n")?;
    root.child("tests/cases.toml")
        .write_str(&recipe.replace("PLATFORM", std::env::consts::OS))?;
    root.child(format!("tests/{inputs}/data.bin"))
        .write_binary(b"a\0\xff")?;
    root.child(format!("tests/{expected}/copy.out"))
        .write_binary(b"a\0\xff")?;
    root.child(format!("tests/{expected}/twice.out"))
        .write_binary(b"a\0\xffa\0\xff")?;
    Ok(())
}

#[test]
fn aliases_defaults_and_rename_preserve_execution_and_recording() -> Result {
    let root = TempDir::new()?;
    setup(&root, RECIPE, "inputs", "expected")?;
    let path = root.path().join("tests/cases.toml");
    let suite = Suite::load(&path)?;
    assert_eq!(
        suite.unreferenced_expected()?,
        Vec::<std::path::PathBuf>::new()
    );
    for case in ["copy", "pipe", "file"] {
        TestContext::new("/bin/cat", root.path())
            .case(case)?
            .check()?;
    }
    assert_eq!(
        suite.case("copy")?.inputs,
        [std::path::PathBuf::from("inputs/data.bin")]
    );
    let stage = TempDir::new()?;
    let destination = stage.path().join("capture");
    recording::record(&suite, &destination)?;
    assert_eq!(
        recording::preview(&suite, &destination)?,
        Vec::<std::path::PathBuf>::new()
    );
    fs::rename(
        root.path().join("tests/inputs/data.bin"),
        root.path().join("tests/inputs/renamed.bin"),
    )?;
    root.child("tests/cases.toml").write_str(
        &RECIPE
            .replace("data.bin", "renamed.bin")
            .replace("PLATFORM", std::env::consts::OS),
    )?;
    let renamed = Suite::load(&path)?;
    assert!(recording::preview(&renamed, &destination).is_err());
    for case in ["copy", "pipe", "file"] {
        TestContext::new("/bin/cat", root.path())
            .case(case)?
            .check()?;
    }
    Ok(())
}

#[test]
fn directory_overrides_reach_runtime_helpers_and_promotion() -> Result {
    let root = TempDir::new()?;
    let recipe = RECIPE.replace(
        "[fixtures]",
        "[paths]\ninputs = 'source'\nexpected = 'golden'\n[fixtures]",
    );
    setup(&root, &recipe, "source", "golden")?;
    let suite = Suite::load(root.path().join("tests/cases.toml"))?;
    let mut cx = TestContext::new("/bin/cat", root.path()).case("copy")?;
    assert_eq!(cx.fixtures().read_input("data.bin")?, b"a\0\xff");
    assert_eq!(cx.fixtures().read_expected("copy.out")?, b"a\0\xff");
    let copied = cx.workspace()?.copy_input("data.bin", "copied")?;
    assert_eq!(fs::read(copied)?, b"a\0\xff");
    root.child("tests/golden/copy.out").write_str("old")?;
    let suite = Suite::load(suite.path())?;
    let stage = TempDir::new()?;
    let destination = stage.path().join("capture");
    recording::record(&suite, &destination)?;
    assert_eq!(
        recording::apply(&suite, &destination)?,
        [std::path::PathBuf::from("golden/copy.out")]
    );
    assert_eq!(
        fs::read(root.path().join("tests/golden/copy.out"))?,
        b"a\0\xff"
    );
    Ok(())
}

#[test]
fn invalid_aliases_defaults_and_paths_fail_before_execution() -> Result {
    for recipe in [
        RECIPE.replace("fixture = \"text\"", "fixture = \"absent\""),
        RECIPE.replace("data.bin", "missing.bin"),
        RECIPE.replace("data.bin", "../data.bin"),
        RECIPE.replace("data.bin", "/tmp/data.bin"),
        RECIPE.replace("fixture = \"text\"", "fixture = \"text\", typo = true"),
        RECIPE.replace(
            "[fixtures]",
            "[paths]\ninputs = 'same'\nexpected = 'same'\n[fixtures]",
        ),
        RECIPE.replace("reference = \"cat\"", "reference = \"unknown\""),
        RECIPE.replace("name = \"copy\"", "name = \"missing\""),
        RECIPE.replace(
            "stdout_file = \"copy.out\"",
            "stdout_file = \"../copy.out\"",
        ),
        RECIPE.replace("schema = 1", "schema = 2"),
    ] {
        let root = TempDir::new()?;
        setup(&root, &recipe, "inputs", "expected")?;
        assert!(
            Suite::load(root.path().join("tests/cases.toml")).is_err(),
            "accepted {recipe}"
        );
    }
    Ok(())
}

#[test]
fn manual_origins_and_case_references_override_the_suite_default() -> Result {
    let root = TempDir::new()?;
    let recipe = RECIPE
        .replace(
            "[references.cat]",
            "[references.other]\nprogram = '/bin/cat'\nplatform = 'PLATFORM'\n[references.cat]",
        )
        .replace(
            "name = \"copy\"",
            "name = 'copy'\norigin = { reference = 'other' }",
        )
        .replace(
            "name = \"pipe\"",
            "name = 'pipe'\norigin = { manual = 'Concatenating two identical byte sequences.' }",
        );
    setup(&root, &recipe, "inputs", "expected")?;
    let suite = Suite::load(root.path().join("tests/cases.toml"))?;
    assert_eq!(
        suite.case("copy")?.origin.reference.as_deref(),
        Some("other")
    );
    assert!(suite.case("pipe")?.origin.reference.is_none());
    assert_eq!(suite.case("file")?.origin.reference.as_deref(), Some("cat"));
    Ok(())
}

#[test]
fn reference_only_operands_are_hashed_and_directory_aliases_are_supported() -> Result {
    let root = TempDir::new()?;
    let recipe = RECIPE.replace("text = \"data.bin\"", "text = 'data.bin'\nall = '.'")
        .replace("args = [{ fixture = \"text\" }]", "args = []\ninputs = ['all']\norigin = { args = [{ fixture = 'text' }], reason = 'Read the reference operand explicitly.' }");
    setup(&root, &recipe, "inputs", "expected")?;
    let suite = Suite::load(root.path().join("tests/cases.toml"))?;
    assert_eq!(
        suite.case("copy")?.inputs,
        [
            std::path::PathBuf::from("inputs"),
            std::path::PathBuf::from("inputs/data.bin")
        ]
    );
    let stage = TempDir::new()?;
    let destination = stage.path().join("capture");
    recording::record(&suite, &destination)?;
    root.child("tests/inputs/new.bin")
        .write_str("new dependency")?;
    assert!(recording::apply(&suite, &destination).is_err());
    assert_eq!(
        fs::read(root.path().join("tests/expected/copy.out"))?,
        b"a\0\xff"
    );
    Ok(())
}
