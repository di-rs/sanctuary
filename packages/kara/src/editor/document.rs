use super::{
    ScreenPosition, TextPosition, buffer::Buffer, cursor::Cursor, line_layout::LineLayout,
    persistence,
};
pub use super::{cursor::Direction, persistence::SaveOutcome};
use std::{
    fs::File,
    io,
    path::{Path, PathBuf},
    time::Instant,
};

#[derive(Default)]
pub struct Document {
    text: Buffer,
    cursor: Cursor,
    file: Option<persistence::SavedFile>,
    modified_at: Option<Instant>,
    revision: u64,
    highlights: super::highlight::HighlightCache,
}
impl Document {
    pub fn open(filename: &str) -> io::Result<Self> {
        let (text, file) = persistence::open(filename.into())?;
        Ok(Self {
            text,
            file: Some(file),
            ..Self::default()
        })
    }
    pub fn save(&mut self) -> io::Result<SaveOutcome> {
        let Some(file) = &self.file else {
            return Ok(SaveOutcome::Unchanged);
        };
        self.save_to(file.path.clone(), File::sync_all)
    }
    pub fn save_as(&mut self, filename: &str) -> io::Result<SaveOutcome> {
        self.save_to(filename.into(), File::sync_all)
    }
    fn save_to(
        &mut self,
        path: PathBuf,
        sync_directory: impl FnOnce(&File) -> io::Result<()>,
    ) -> io::Result<SaveOutcome> {
        let same_path = self.filename() == Some(path.as_path());
        if same_path && !self.is_modified() {
            return Ok(SaveOutcome::Unchanged);
        }
        let destination = persistence::resolve_destination(&path).map_err(|error| {
            if same_path && error.kind() == io::ErrorKind::NotFound {
                persistence::save_conflict()
            } else {
                error
            }
        })?;
        let expected = self
            .file
            .as_ref()
            .filter(|file| same_path || file.matches_destination(&destination));
        if expected.is_some() && !self.is_modified() {
            return Ok(SaveOutcome::Unchanged);
        }
        let (file, outcome) =
            persistence::save(&self.text, path, destination, expected, sync_directory)?;
        self.file = Some(file);
        self.modified_at = None;
        Ok(outcome)
    }
    pub fn file_type(&self) -> super::file_type::FileType {
        super::file_type::FileType::detect(self.filename())
    }
    pub fn filename(&self) -> Option<&Path> {
        self.file.as_ref().map(|file| file.path.as_path())
    }
    pub const fn has_file(&self) -> bool {
        self.file.is_some()
    }
    pub fn insert_char(&mut self, character: char) {
        let old_height = self.height();
        let edited_line = self.cursor.position.line;
        let old_len = self.current_line_width();
        self.text.insert_char(character, self.cursor.position);
        if self.current_line_width() > old_len {
            self.move_caret(Direction::Right(1));
        }
        self.mark_modified(edited_line, old_height);
    }
    pub fn insert_newline(&mut self) {
        let old_height = self.height();
        let edited_line = self.cursor.position.line;
        self.text.insert_newline(self.cursor.position);
        self.cursor.set_position(
            &self.text,
            TextPosition {
                line: self.cursor.position.line.saturating_add(1),
                grapheme: 0,
            },
        );
        self.mark_modified(edited_line, old_height);
    }
    pub fn delete_backward(&mut self) {
        if self.cursor.position == TextPosition::default() {
            return;
        }
        self.move_caret(Direction::Left(1));
        self.delete();
    }
    pub fn delete(&mut self) {
        let old_height = self.height();
        let edited_line = self.cursor.position.line;
        if self.text.delete(self.cursor.position) {
            self.mark_modified(edited_line, old_height);
            self.cursor.clamp_after_edit(&self.text);
        }
    }
    pub fn refresh_highlights(&mut self) {
        if self.file_type() == super::file_type::FileType::Rust {
            self.highlights.refresh(&self.text);
        }
    }
    pub fn syntax_at(
        &self,
        line: usize,
        bytes: std::ops::Range<usize>,
    ) -> Option<super::highlight::Kind> {
        if self.file_type() == super::file_type::FileType::Rust {
            self.highlights.kind_overlapping(line, bytes)
        } else {
            None
        }
    }
    pub fn cursor(&self) -> super::cursor::Cursor {
        self.cursor.clone()
    }
    pub const fn restore_cursor(&mut self, cursor: super::cursor::Cursor) {
        self.cursor = cursor;
    }
    pub fn set_position(&mut self, position: TextPosition) {
        self.cursor.set_position(&self.text, position);
    }
    pub fn move_caret(&mut self, direction: Direction) {
        self.cursor.move_caret(&self.text, direction);
    }
    pub fn caret_location(&self) -> ScreenPosition {
        ScreenPosition {
            y: self.cursor.position.line,
            x: self
                .text
                .get_line(self.cursor.position.line)
                .map_or(0, |line| line.width_until(self.cursor.position.grapheme)),
        }
    }
    pub fn is_empty(&self) -> bool {
        self.text.is_empty()
    }
    pub fn line_text(&self, index: usize) -> Option<String> {
        self.text.line_text(index)
    }
    pub fn get_line(&self, index: usize) -> Option<LineLayout> {
        self.text.get_line(index)
    }
    fn current_line_width(&self) -> usize {
        self.text
            .get_line(self.cursor.position.line)
            .map_or(0, |line| line.len())
    }
    pub const fn revision(&self) -> u64 {
        self.revision
    }
    fn mark_modified(&mut self, edited_line: usize, old_height: usize) {
        self.highlights
            .invalidate(edited_line, old_height, self.height());
        self.revision = self.revision.wrapping_add(1);
        self.modified_at = Some(Instant::now());
    }
    pub const fn is_modified(&self) -> bool {
        self.modified_at.is_some()
    }
    pub fn height(&self) -> usize {
        self.text.height()
    }
}

#[cfg(test)]
mod save_tests {
    use super::{Document, SaveOutcome};
    use std::{fs, io};

    #[test]
    #[allow(
        clippy::panic_in_result_fn,
        reason = "Assertions verify the save commit boundary."
    )]
    fn directory_sync_failure_keeps_committed_identity() -> Result<(), Box<dyn std::error::Error>> {
        let dir = assert_fs::TempDir::new()?;
        let original = dir.path().join("original");
        let destination = dir.path().join("saved.rs");
        fs::write(&original, b"original\n")?;
        let mut buffer = Document::open(original.to_str().ok_or("non-UTF-8 fixture")?)?;
        assert_eq!(
            buffer.file_type(),
            super::super::file_type::FileType::PlainText
        );
        buffer.insert_char('X');
        let result = buffer.save_to(destination.clone(), |_| {
            Err(io::Error::other("injected directory sync failure"))
        })?;
        assert!(matches!(result, SaveOutcome::DurabilityWarning(_)));
        assert_eq!(buffer.filename(), Some(destination.as_path()));
        assert!(!buffer.is_modified());
        assert_eq!(buffer.file_type(), super::super::file_type::FileType::Rust);
        assert_eq!(fs::read(&destination)?, b"Xoriginal\n");
        buffer.insert_char('Y');
        assert!(matches!(buffer.save()?, SaveOutcome::Saved));
        assert_eq!(fs::read(&destination)?, b"XYoriginal\n");
        assert_eq!(fs::read(&original)?, b"original\n");
        Ok(())
    }
    #[test]
    #[allow(
        clippy::panic_in_result_fn,
        reason = "Assertions verify failed saves retain file type and identity."
    )]
    fn failed_save_keeps_original_file_type() -> Result<(), Box<dyn std::error::Error>> {
        let dir = assert_fs::TempDir::new()?;
        let original = dir.path().join("original.txt");
        fs::write(&original, b"12")?;
        let mut document = Document::open(original.to_str().ok_or("invalid path")?)?;
        document.insert_char('3');
        let failed = document.save_as(
            dir.path()
                .join("missing/failed.rs")
                .to_str()
                .ok_or("invalid path")?,
        );
        assert!(failed.is_err());
        assert_eq!(document.filename(), Some(original.as_path()));
        assert_eq!(
            document.file_type(),
            super::super::file_type::FileType::PlainText
        );
        assert!(document.is_modified());
        assert_eq!(
            super::super::file_type::FileType::detect(Some(std::path::Path::new("upper.RS"))),
            super::super::file_type::FileType::Rust
        );
        Ok(())
    }
}
