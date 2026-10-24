use super::{Case, Expected, Input, Origin, Suite, identifier, relative_path};
use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::PathBuf};

/// Fixture directories, relative to the package's tests directory.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct FixturePaths {
    pub inputs: PathBuf,
    pub expected: PathBuf,
}

impl Default for FixturePaths {
    fn default() -> Self {
        Self {
            inputs: "inputs".into(),
            expected: "expected".into(),
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
pub(super) enum Argument {
    Literal(String),
    Fixture(FixtureArgument),
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct FixtureArgument {
    fixture: String,
}

impl Suite<Argument> {
    pub(super) fn resolve(self) -> Result<Suite> {
        if self.schema != 1 {
            return Err(Error::new("catalog requires schema = 1"));
        }
        relative_path(&self.paths.inputs)?;
        relative_path(&self.paths.expected)?;
        if self.paths.inputs.starts_with(&self.paths.expected)
            || self.paths.expected.starts_with(&self.paths.inputs)
        {
            return Err(Error::new(
                "input and expected directories must not overlap",
            ));
        }
        let mut fixtures = BTreeMap::new();
        for (name, path) in &self.fixtures {
            if !identifier(name) {
                return Err(Error::new(format!("invalid fixture name {name:?}")));
            }
            let resolved = if path == std::path::Path::new(".") {
                self.paths.inputs.clone()
            } else {
                relative_path(path)?;
                self.paths.inputs.join(path)
            };
            fixtures.insert(name.clone(), resolved);
        }
        let mut cases = Vec::new();
        for mut case in self.cases {
            if case.origin.reference.is_none() && case.origin.manual.is_none() {
                case.origin.reference.clone_from(&self.reference);
            }
            let name = case.name.clone();
            let resolved = resolve_case(case, &self.paths, &fixtures)
                .map_err(|error| Error::caused_by(format!("invalid case {name:?}"), error))?;
            cases.push(resolved);
        }
        Ok(Suite {
            schema: self.schema,
            binary: self.binary,
            env: self.env,
            references: self.references,
            reference: self.reference,
            cases,
            fixtures,
            paths: self.paths,
            package_dir: self.package_dir,
            source: self.source,
        })
    }
}

fn resolve_case(
    case: Case<Argument>,
    paths: &FixturePaths,
    fixtures: &BTreeMap<String, PathBuf>,
) -> Result<Case> {
    let mut inputs = case.inputs;
    let mut stdin = case.stdin;
    let mut expect = case.expect;
    for path in &mut inputs {
        *path = input(path, fixtures)?;
    }
    if let Some(stdin) = &mut stdin {
        match stdin {
            Input::Pipe { files, .. } => {
                for path in files {
                    *path = input(path, fixtures)?;
                }
            }
            Input::File { path } => *path = input(path, fixtures)?,
        }
    }
    expected(&mut expect, &case.name, paths)?;
    let args = arguments(case.args, fixtures, &mut inputs)?;
    let origin_args = case
        .origin
        .args
        .map(|args| arguments(args, fixtures, &mut inputs))
        .transpose()?;
    inputs.sort();
    inputs.dedup();
    Ok(Case {
        name: case.name,
        execution: case.execution,
        args,
        inputs,
        stdin,
        env: case.env,
        adapt: case.adapt,
        expect,
        origin: Origin {
            reference: case.origin.reference,
            manual: case.origin.manual,
            args: origin_args,
            exit: case.origin.exit,
            stderr: case.origin.stderr,
            env: case.origin.env,
            reason: case.origin.reason,
        },
    })
}

fn input(name: &std::path::Path, fixtures: &BTreeMap<String, PathBuf>) -> Result<PathBuf> {
    let name = name
        .to_str()
        .ok_or_else(|| Error::new("fixture ID must be UTF-8"))?;
    fixtures
        .get(name)
        .cloned()
        .ok_or_else(|| Error::new(format!("unknown input fixture {name:?}")))
}

fn arguments(
    args: Vec<Argument>,
    fixtures: &BTreeMap<String, PathBuf>,
    inputs: &mut Vec<PathBuf>,
) -> Result<Vec<String>> {
    args.into_iter()
        .map(|arg| match arg {
            Argument::Literal(value) => Ok(value),
            Argument::Fixture(value) => {
                let path = input(std::path::Path::new(&value.fixture), fixtures)?;
                let argument = format!("tests/{}", path.to_string_lossy());
                inputs.push(path);
                Ok(argument)
            }
        })
        .collect()
}

fn expected(expect: &mut Expected, name: &str, paths: &FixturePaths) -> Result {
    if expect.stdout.is_none() && expect.stdout_file.is_none() {
        if !identifier(name) {
            return Err(Error::new(format!("invalid case name {name:?}")));
        }
        expect.stdout_file = Some(format!("{name}.out").into());
    }
    if expect.stderr.is_none() && expect.stderr_file.is_none() {
        expect.stderr = Some(String::new());
    }
    for path in [&mut expect.stdout_file, &mut expect.stderr_file]
        .into_iter()
        .flatten()
    {
        relative_path(path)?;
        *path = paths.expected.join(&*path);
    }
    Ok(())
}
