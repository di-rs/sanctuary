use crate::{Error, Result};
use std::{fs, path::Path};

const MARKER: &str = "<!-- cli-example -->";

/// Keep shell setup and argument quoting from the published example. Substitute
/// Cargo's built binary for the final invocation so tests never rebuild via Cargo.
pub fn script(readme: &Path, binary: &Path) -> Result<String> {
    let bad_example = |message: &str| Error::new(format!("{}: {message}", readme.display()));
    let source = fs::read_to_string(readme)
        .map_err(|error| Error::caused_by(format!("cannot read {}", readme.display()), error))?;
    let mut lines = source.lines();
    if !lines.any(|line| line == MARKER)
        || lines.find(|line| !line.trim().is_empty()) != Some("```sh")
    {
        return Err(bad_example(
            "mark the introductory sh fence with <!-- cli-example -->",
        ));
    }
    let mut closed = false;
    let mut block: Vec<_> = lines
        .take_while(|line| {
            closed = *line == "```";
            !closed
        })
        .collect();
    if !closed {
        return Err(bad_example(
            "missing closing fence for the introductory example",
        ));
    }
    let name = binary
        .file_stem()
        .and_then(|name| name.to_str())
        .ok_or_else(|| bad_example("cannot identify the built CLI"))?;
    let cargo = format!("cargo run -q -p {name} --");
    let invocation = block
        .pop()
        .ok_or_else(|| bad_example("the introductory example is empty"))?;
    let (setup, arguments) = invocation
        .strip_prefix(&cargo)
        .map(|args| ("", args))
        .or_else(|| {
            invocation
                .rsplit_once(&format!(" | {cargo}"))
                .filter(|(producer, _)| producer.starts_with("printf "))
        })
        .filter(|(_, args)| args.is_empty() || args.starts_with(' '))
        .ok_or_else(|| bad_example(&format!("end the introductory example with `{cargo}`")))?;
    let command = if setup.is_empty() {
        format!("exec \"$1\"{arguments}")
    } else {
        format!("{setup} | exec \"$1\"{arguments}")
    };
    block.push(&command);
    Ok(block.join("\n"))
}
