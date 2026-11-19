use std::{path::Path, range::Range};

use unicode_segmentation::UnicodeSegmentation;

use crate::editor::{
    command::{Edit, EditorCommand},
    line_layout::LineLayout,
    prompt::interpreter::Interpreter,
};

mod interpreter;

pub struct Prompt {
    label: &'static str,
    value: String,
}

impl Prompt {
    pub fn new(label: &'static str, value: &str) -> Self {
        Self {
            label,
            value: value.to_owned(),
        }
    }

    pub fn display(&self, width: usize) -> (String, usize) {
        let layout = LineLayout::new(&self.value);
        let label_width = self.label.len();
        let value_width = layout.width();
        let available = width.saturating_sub(label_width).saturating_sub(1);
        let start = value_width.saturating_sub(available);
        let text = format!(
            "{}{}",
            self.label,
            layout.get(Range::from(start..value_width))
        );
        let caret = label_width
            .saturating_add(value_width)
            .min(width.saturating_sub(1));
        (text, caret)
    }

    pub fn value(&self) -> String {
        self.value.clone()
    }

    pub fn handle_edit(&mut self, edit_command: &Edit) {
        match edit_command {
            Edit::Insert(character) => self.value.push(*character),
            Edit::DeleteBackward => {
                let start = self
                    .value
                    .grapheme_indices(true)
                    .next_back()
                    .map_or(0, |(start, _)| start);
                self.value.truncate(start);
            }
            _ => {}
        }
    }

    pub fn produce_command(
        &mut self,
        current_file: Option<&Path>,
    ) -> Result<EditorCommand, String> {
        let command = Interpreter::into_command(&self.value, current_file);
        self.value.clear();
        command
    }
}
