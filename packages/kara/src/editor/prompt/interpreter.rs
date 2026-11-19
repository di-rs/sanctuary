use std::path::Path;

use crate::editor::command::{
    EditorCommand,
    System::{Quit, QuitForce, SaveAs},
};

pub struct Interpreter {}

impl Interpreter {
    pub(crate) fn into_command(
        value: &str,
        current_file: Option<&Path>,
    ) -> Result<EditorCommand, String> {
        let (verb, operand) = value.split_once(' ').unwrap_or((value, ""));
        match verb {
            "w" => {
                let name = if operand.is_empty() {
                    current_file.and_then(|p| p.to_str())
                } else {
                    Some(operand)
                };
                name.map_or_else(
                    || Err("ERR: filename was not provided".to_owned()),
                    |name| Ok(EditorCommand::System(SaveAs(name.to_owned()))),
                )
            }
            "q" => Ok(EditorCommand::System(Quit)),
            "q!" => Ok(EditorCommand::System(QuitForce)),
            _ => Err(format!("ERR: unknown command {value}")),
        }
    }
}
