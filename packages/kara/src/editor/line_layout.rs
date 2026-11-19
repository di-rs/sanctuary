use std::range::Range;
use unicode_segmentation::UnicodeSegmentation;
use unicode_width::UnicodeWidthStr;

#[derive(Debug, Clone)]
struct TextFragment {
    grapheme: String,
    byte: usize,
    end_cell: usize,
    replacement: Option<char>,
}

#[derive(Debug, Clone)]
pub struct LineLayout {
    fragments: Vec<TextFragment>,
}

impl LineLayout {
    pub const fn len(&self) -> usize {
        self.fragments.len()
    }

    pub fn get(&self, range: Range<usize>) -> String {
        self.visible(range)
            .into_iter()
            .map(|(_, text)| text)
            .collect()
    }

    /// Visible fragments retain their source grapheme indexes after cell clipping.
    pub fn visible(&self, range: Range<usize>) -> Vec<(usize, String)> {
        if range.start >= range.end {
            return Vec::new();
        }
        let first = self
            .fragments
            .partition_point(|fragment| fragment.end_cell <= range.start);
        let mut start_cell = self.width_until(first);
        let mut result = Vec::new();
        for (index, fragment) in self.fragments.iter().enumerate().skip(first) {
            if start_cell >= range.end {
                break;
            }
            let text = if start_cell < range.start || fragment.end_cell > range.end {
                "⋯".to_owned()
            } else if let Some(replacement) = fragment.replacement {
                replacement.to_string()
            } else {
                fragment.grapheme.clone()
            };
            result.push((index, text));
            start_cell = fragment.end_cell;
        }
        result
    }

    pub fn prefix_whitespace_count(&self) -> usize {
        self.fragments
            .iter()
            .take_while(|c| c.grapheme.chars().all(char::is_whitespace))
            .count()
    }

    pub fn width_until(&self, grapheme_index: usize) -> usize {
        grapheme_index
            .min(self.len())
            .checked_sub(1)
            .and_then(|previous| self.fragments.get(previous))
            .map_or(0, |fragment| fragment.end_cell)
    }

    pub fn byte_range(&self, grapheme: usize) -> Option<std::ops::Range<usize>> {
        let fragment = self.fragments.get(grapheme)?;
        Some(fragment.byte..fragment.byte.saturating_add(fragment.grapheme.len()))
    }

    pub fn width(&self) -> usize {
        self.width_until(self.len())
    }

    pub fn new(text: &str) -> Self {
        let mut end_cell = 0_usize;
        let fragments = text
            .grapheme_indices(true)
            .map(|(byte, grapheme)| {
                let width = grapheme.width();
                let (replacement, cell_width) = match grapheme {
                    " " => (None, 1),
                    "\t" => (Some(' '), 1),
                    _ if grapheme.chars().any(char::is_control) => (Some('▯'), 1),
                    _ if width == 0 => (Some('·'), 1),
                    _ if grapheme.trim().is_empty() => (Some('␣'), 1),
                    _ => (None, width.min(2)),
                };
                end_cell = end_cell.saturating_add(cell_width);
                TextFragment {
                    grapheme: grapheme.to_string(),
                    byte,
                    end_cell,
                    replacement,
                }
            })
            .collect();
        Self { fragments }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clips_rendered_cells_and_keeps_source_positions() {
        let layout = LineLayout::new("\t\u{a0} 界\u{7}\u{301}");
        assert_eq!(layout.prefix_whitespace_count(), 3);
        for (grapheme, cells) in [0, 1, 2, 3, 5, 6, 7].into_iter().enumerate() {
            assert_eq!(layout.width_until(grapheme), cells);
        }
        assert_eq!(layout.width_until(usize::MAX), 7);
        assert_eq!(layout.byte_range(3), Some(4..7));
        assert_eq!(layout.byte_range(5), Some(8..10));
        assert_eq!(layout.get(Range::from(0..4)), " ␣ ⋯");
        assert_eq!(
            layout.visible(Range::from(4..7)),
            [
                (3, "⋯".to_owned()),
                (4, "▯".to_owned()),
                (5, "·".to_owned())
            ]
        );
        assert_eq!(layout.visible(Range::from(4..4)), []);
        assert_eq!(layout.visible(Range::from(7..8)), []);
    }
}
