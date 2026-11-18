//! Staged raw reference captures and explicit, preflighted promotion.

use crate::{
    Error, Result,
    catalog::{Case, Suite, checked_path},
    reference::{self, Identity, hash},
};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Recording {
    schema: u32,
    complete: bool,
    catalog: PathBuf,
    catalog_sha256: String,
    files: BTreeMap<PathBuf, String>,
    cases: Vec<RecordedCase>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct RecordedCase {
    name: String,
    identity: Identity,
    args: Vec<String>,
    env: BTreeMap<String, String>,
    exit: i32,
    stdout: Artifact,
    stderr: Artifact,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Artifact {
    file: PathBuf,
    sha256: String,
}

/// Record every reference recipe, including Rust-owned cases, into a new directory.
///
/// Only a successful, consistent run receives a completed `recording.json`.
/// Existing fixtures are never written here. Manual expectations are not recorded.
/// # Errors
/// Rejects existing output directories, failed references and changing inputs.
pub fn record(suite: &Suite, output: &Path) -> Result<usize> {
    let catalog_sha256 = catalog_hash(suite)?;
    let files = snapshot(suite)?;
    let output = new_recording_directory(suite, output)?;
    let mut cases = Vec::new();
    for case in suite
        .cases
        .iter()
        .filter(|case| case.origin.reference.is_some())
    {
        let captured = reference::run(suite, case)?;
        let stdout = save_artifact(
            &output,
            &format!("{}.stdout", case.name),
            &captured.output.stdout,
        )?;
        let stderr = save_artifact(
            &output,
            &format!("{}.stderr", case.name),
            &captured.output.stderr,
        )?;
        cases.push(RecordedCase {
            name: case.name.clone(),
            identity: captured.identity,
            args: captured.args,
            env: captured.env,
            exit: captured
                .output
                .status
                .code()
                .ok_or_else(|| Error::new("reference terminated by signal"))?,
            stdout,
            stderr,
        });
    }
    if cases.is_empty() {
        return Err(Error::new(
            "catalog contains no independent reference recipes",
        ));
    }
    if files != snapshot(suite)? || catalog_sha256 != hash(&fs::read(suite.path())?) {
        return Err(Error::new(
            "catalog or fixtures changed during recording; capture is incomplete",
        ));
    }
    let recording = Recording {
        schema: 1,
        complete: true,
        catalog: suite.path(),
        catalog_sha256,
        files,
        cases,
    };
    replacements(suite, &output, &recording)?;
    let bytes = serde_json::to_vec_pretty(&recording)
        .map_err(|error| Error::caused_by("cannot serialize recording", error))?;
    fs::write(output.join("recording.json"), bytes)?;
    Ok(recording.cases.len())
}

fn new_recording_directory(suite: &Suite, output: &Path) -> Result<PathBuf> {
    let parent = output
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let name = output
        .file_name()
        .ok_or_else(|| Error::new("output must name a new directory"))?;
    let output = parent.canonicalize()?.join(name);
    if output.starts_with(suite.package_dir().join("tests")) {
        return Err(Error::new(
            "recordings must be outside the package's tests directory",
        ));
    }
    fs::create_dir(&output).map_err(|error| {
        Error::caused_by(
            format!(
                "recording needs a new output directory: {}",
                output.display()
            ),
            error,
        )
    })?;
    Ok(output)
}

/// Promote a reviewed recording to the catalog's declared expected files.
/// All hashes, recipes, destinations and shared-file conflicts are checked first.
/// # Errors
/// Rejects incomplete, stale, tampered or conflicting recordings before writes.
/// An I/O failure during promotion reports which writes already completed.
pub fn apply(suite: &Suite, directory: &Path) -> Result<Vec<PathBuf>> {
    promote(suite, prepare_apply(suite, directory)?)
}

fn promote(suite: &Suite, replacements: BTreeMap<PathBuf, Vec<u8>>) -> Result<Vec<PathBuf>> {
    let mut written = Vec::new();
    for (relative, bytes) in replacements {
        if replace_fixture(suite, &relative, &bytes).map_err(|error| {
            let destination = suite.package_dir().join("tests").join(&relative);
            Error::caused_by(
                format!(
                    "cannot promote {}; already wrote {written:?}",
                    destination.display()
                ),
                error,
            )
        })? {
            written.push(relative);
        }
    }
    Ok(written)
}

fn replace_fixture(suite: &Suite, relative: &Path, bytes: &[u8]) -> Result<bool> {
    let path = suite.fixture_path(relative)?;
    let current =
        fs::read(&path).map_err(|error| Error::caused_by("cannot read destination", error))?;
    if current == bytes {
        return Ok(false);
    }
    fs::write(&path, bytes).map_err(|error| Error::caused_by("cannot write destination", error))?;
    Ok(true)
}

/// Preflight a recording and list fixtures whose bytes would change.
/// No expected files are written; configured reference version probes may run.
/// # Errors
/// Rejects the same incomplete, stale or conflicting recordings as [`apply`].
pub fn preview(suite: &Suite, directory: &Path) -> Result<Vec<PathBuf>> {
    let replacements = prepare_apply(suite, directory)?;
    let mut changed = Vec::new();
    for (path, bytes) in replacements {
        if suite.read(&path)? != bytes {
            changed.push(path);
        }
    }
    Ok(changed)
}

fn prepare_apply(suite: &Suite, directory: &Path) -> Result<BTreeMap<PathBuf, Vec<u8>>> {
    let manifest = checked_path(directory, Path::new("recording.json")).map_err(|error| {
        Error::caused_by(
            "recording is incomplete: no readable completion manifest",
            error,
        )
    })?;
    let recording: Recording = serde_json::from_slice(&fs::read(manifest)?)
        .map_err(|error| Error::caused_by("invalid recording manifest", error))?;
    if recording.schema != 1 || !recording.complete || recording.catalog != suite.path() {
        return Err(Error::new(
            "incomplete recording or recording belongs to a different catalog",
        ));
    }
    if recording.catalog_sha256 != catalog_hash(suite)? || recording.files != snapshot(suite)? {
        return Err(Error::new(
            "stale recording: catalog, inputs, or expected fixtures changed",
        ));
    }
    let expected: Vec<_> = suite
        .cases
        .iter()
        .filter(|case| case.origin.reference.is_some())
        .map(|case| &case.name)
        .collect();
    if expected
        != recording
            .cases
            .iter()
            .map(|case| &case.name)
            .collect::<Vec<_>>()
    {
        return Err(Error::new(
            "incomplete recording: reference case set differs from catalog",
        ));
    }
    for recorded in &recording.cases {
        verify_identity(suite, recorded)?;
    }
    replacements(suite, directory, &recording)
}

fn catalog_hash(suite: &Suite) -> Result<String> {
    let bytes = fs::read(suite.path())?;
    if bytes != suite.source.as_bytes() {
        return Err(Error::new(
            "stale catalog: cases.toml changed since loading; reload it before recording or applying",
        ));
    }
    Ok(hash(&bytes))
}

fn save_artifact(directory: &Path, name: &str, bytes: &[u8]) -> Result<Artifact> {
    fs::write(directory.join(name), bytes)?;
    Ok(Artifact {
        file: PathBuf::from(name),
        sha256: hash(bytes),
    })
}

fn read_artifact(directory: &Path, artifact: &Artifact, expected_name: &str) -> Result<Vec<u8>> {
    if artifact.file != Path::new(expected_name) {
        return Err(Error::new(
            "recording artifact path does not match its case",
        ));
    }
    let bytes = fs::read(checked_path(directory, &artifact.file)?)?;
    if hash(&bytes) != artifact.sha256 {
        return Err(Error::new(format!(
            "recording artifact hash mismatch: {}",
            artifact.file.display()
        )));
    }
    Ok(bytes)
}

fn snapshot(suite: &Suite) -> Result<BTreeMap<PathBuf, String>> {
    let mut result = BTreeMap::new();
    for case in &suite.cases {
        for relative in case
            .inputs
            .iter()
            .chain(case.stdin.iter().flat_map(crate::catalog::Input::paths))
            .chain(case.expect.paths())
        {
            snapshot_path(suite, relative, &mut result)?;
        }
    }
    Ok(result)
}

fn snapshot_path(suite: &Suite, relative: &Path, result: &mut BTreeMap<PathBuf, String>) -> Result {
    if result.contains_key(relative) {
        return Ok(());
    }
    let path = suite.fixture_path(relative)?;
    if path.is_dir() {
        result.insert(relative.to_path_buf(), "directory".to_owned());
        for entry in fs::read_dir(path)? {
            snapshot_path(suite, &relative.join(entry?.file_name()), result)?;
        }
    } else {
        result.insert(relative.to_path_buf(), hash(&suite.read(relative)?));
    }
    Ok(())
}

fn verify_identity(suite: &Suite, recorded: &RecordedCase) -> Result {
    let case = suite.case(&recorded.name)?;
    let name = case
        .origin
        .reference
        .as_ref()
        .ok_or_else(|| Error::new("manual case cannot be recorded"))?;
    let reference = suite
        .references
        .get(name)
        .ok_or_else(|| Error::new("unknown reference"))?;
    let identity =
        reference::identity(&reference.program.canonicalize()?, &reference.version_args)?;
    let mut env = crate::default_environment();
    env.extend(suite.env.clone());
    env.extend(case.env.clone());
    env.extend(reference.env.clone());
    env.extend(case.origin.env.clone());
    let args = case.origin.args.as_ref().unwrap_or(&case.args);
    if identity != recorded.identity || args != &recorded.args || env != recorded.env {
        return Err(Error::new(format!(
            "stale reference identity or invocation for {:?}",
            case.name
        )));
    }
    Ok(())
}

fn replacements(
    suite: &Suite,
    directory: &Path,
    recording: &Recording,
) -> Result<BTreeMap<PathBuf, Vec<u8>>> {
    let mut writes = BTreeMap::new();
    for recorded in &recording.cases {
        let case = suite.case(&recorded.name)?;
        if recorded.exit != case.origin.exit.unwrap_or(case.expect.exit) {
            return Err(Error::new(format!(
                "invalid recorded status for {:?}",
                case.name
            )));
        }
        let stdout = read_artifact(
            directory,
            &recorded.stdout,
            &format!("{}.stdout", case.name),
        )?;
        let stderr = read_artifact(
            directory,
            &recorded.stderr,
            &format!("{}.stderr", case.name),
        )?;
        let (expected_stdout, expected_stderr) = case.expect.bytes(suite)?;
        let ref_stderr = case
            .origin
            .stderr
            .as_ref()
            .map_or_else(|| expected_stderr.clone(), |text| text.as_bytes().to_vec());
        crate::context::check_bytes(
            &case.name,
            "recorded reference stderr",
            &stderr,
            &ref_stderr,
        )?;
        let stdout = if let Some(adapt) = &case.adapt
            && case.expect.stdout_file.is_none()
        {
            adapt.expected_stdout.apply(&stdout)
        } else {
            stdout
        };
        promote_stream(
            &mut writes,
            case.expect.stdout_file.as_ref(),
            stdout,
            &expected_stdout,
            case,
        )?;
        // A declared stderr difference must never replace the candidate expectation.
        if case.origin.stderr.is_none() {
            promote_stream(
                &mut writes,
                case.expect.stderr_file.as_ref(),
                stderr,
                &expected_stderr,
                case,
            )?;
        }
    }
    // Preserve every expectation that is not supplied by this recording, even
    // when another stream or case records into the same fixture.
    for case in &suite.cases {
        let stdout = case
            .expect
            .stdout_file
            .as_ref()
            .filter(|_| case.origin.reference.is_none());
        let stderr = case
            .expect
            .stderr_file
            .as_ref()
            .filter(|_| case.origin.reference.is_none() || case.origin.stderr.is_some());
        for path in stdout.into_iter().chain(stderr) {
            if let Some(bytes) = writes.get(path)
                && suite.read(path)? != *bytes
            {
                return Err(Error::new(format!(
                    "recording conflicts with preserved expectation of case {:?} in {}",
                    case.name,
                    path.display()
                )));
            }
        }
    }
    Ok(writes)
}

fn promote_stream(
    writes: &mut BTreeMap<PathBuf, Vec<u8>>,
    path: Option<&PathBuf>,
    bytes: Vec<u8>,
    inline: &[u8],
    case: &Case,
) -> Result {
    if let Some(path) = path {
        if writes.get(path).is_some_and(|previous| previous != &bytes) {
            return Err(Error::new(format!(
                "conflicting reference writes to shared fixture {} (case {:?})",
                path.display(),
                case.name
            )));
        }
        writes.insert(path.clone(), bytes);
    } else {
        crate::context::check_bytes(
            &case.name,
            "recording vs inline expectation",
            &bytes,
            inline,
        )?;
    }
    Ok(())
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    #[allow(
        clippy::panic_in_result_fn,
        reason = "Assertions verify the error and disk state; Result propagates setup failures."
    )]
    fn promotion_reports_completed_writes_on_lookup_and_read_failure() -> Result {
        use std::error::Error as _;

        for (replace_with_directory, operation) in
            [(false, "cannot inspect"), (true, "cannot read destination")]
        {
            let package = assert_fs::TempDir::new()
                .map_err(|error| Error::caused_by("cannot create test package", error))?;
            let root = package.path();
            fs::create_dir_all(root.join("tests/expected"))?;
            fs::write(root.join("Cargo.toml"), "[package]\nname = 'probe'\n")?;
            let catalog = root.join("tests/cases.toml");
            fs::write(
                &catalog,
                r#"
schema = 1
binary = "probe"
[[cases]]
name = "probe"
args = []
origin = { manual = "Fixed test bytes." }
expect = { exit = 0, stdout_file = "first.out", stderr_file = "second.out" }
"#,
            )?;
            let first = PathBuf::from("expected/first.out");
            let second = PathBuf::from("expected/second.out");
            let first_path = root.join("tests").join(&first);
            let second_path = root.join("tests").join(&second);
            fs::write(&first_path, b"old")?;
            fs::write(&second_path, b"old")?;
            let suite = Suite::load(&catalog)?;

            // Change the second destination after loading, before the write phase.
            fs::remove_file(&second_path)?;
            if replace_with_directory {
                fs::create_dir(&second_path)?;
            }
            let replacements =
                BTreeMap::from([(first, b"first".to_vec()), (second, b"second".to_vec())]);
            let Err(error) = promote(&suite, replacements) else {
                return Err(Error::new("promotion unexpectedly succeeded"));
            };
            let message = error.to_string();
            assert!(message.contains("tests/expected/second.out"), "{error}");
            assert!(
                message.contains(r#"already wrote ["expected/first.out"]"#),
                "{error}"
            );
            assert!(
                error
                    .source()
                    .is_some_and(|source| source.to_string().contains(operation))
            );
            assert_eq!(fs::read(&first_path)?, b"first");
        }
        Ok(())
    }
}
